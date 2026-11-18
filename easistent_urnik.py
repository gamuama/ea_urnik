#!/usr/bin/env python3
import argparse, html, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE = 'https://urniki.easistent.com/urniki'
UA = 'easistent-urnik-scraper/0.1 (+public timetable reader)'


def fetch(url):
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,*/*'})
    with urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def extract_var(text, name):
    m = re.search(r"var\s+" + re.escape(name) + r"\s*=\s*['\"]([^'\"]*)['\"]", text)
    return m.group(1) if m else None


def ajax_payload_to_html(text):
    # eAsistent AJAX response: fields separated by ASCII unit separator (31), HTML is field 4 (index 3).
    parts = text.split(chr(31))
    return parts[3] if len(parts) >= 5 else text


def clean(s):
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def extract_cells(page):
    # Capture every timetable TD and its inner HTML. DOTALL is intentional: server markup spans lines.
    pat = re.compile(r'<td\b[^>]*id="ednevnik-seznam_ur_teden-td-(\d+)-(\d{4}-\d{2}-\d{2})"[^>]*>(.*?)</td>', re.S | re.I)
    return [(int(h), d, body) for h, d, body in pat.findall(page)]


def extract_times(page):
    out = {}
    pat = re.compile(r'id="urnik-ura-(\d+)".*?<div class="potek-ure">(.*?)</div>', re.S | re.I)
    for h, val in pat.findall(page):
        out[int(h)] = clean(val)
    return out


def parse_sr(text):
    """Best-effort structured fields from eAsistent accessibility text; raw text is retained too."""
    x = clean(text)
    if not x or 'brez vsebine' in x.lower():
        return []

    # Remove the spoken day/date/hour prefix before splitting into multiple timetable blocks.
    # Doing this first is important for entries such as:
    # "Torek ... predura ... sklop 1: ... sklop 2: ...".
    prefix = re.compile(
        r'^(?:Ponedeljek|Torek|Sreda|Četrtek|Petek)\s+.*?\.\s*'
        r'(?:(?:predura|prva ura|druga ura|tretja ura|četrta ura|peta ura|šesta ura|sedma ura|osma ura|deveta ura)\s+od\s+.*?\.\s*)?',
        re.I,
    )
    x = prefix.sub('', x).strip(' .')

    # Split multiple alternatives/blocks after the common prefix has been removed.
    blocks = re.split(r'\s*sklop\s+\d+:\s*', x, flags=re.I)
    blocks = [b.strip(' .') for b in blocks if b.strip(' .')]
    items = []

    for b in blocks:
        # Labels used by accessibility text are not part of the subject.
        b = re.sub(r'^(?:interesna dejavnost|dogodek)\.\s*', '', b, flags=re.I)

        item = {'raw': b}
        teacher = re.search(r'(?:profesor)\s+(.+?)(?=\.\s+učilnica|,\s+učilnica|\.\s+skupine|\.\s+čas|$)', b, re.I)
        # Room may legitimately contain a dot, e.g. "3.c". Stop at known following labels/end.
        room = re.search(r'učilnica\s+(.+?)(?=\.\s+(?:skupine|čas)|$)', b, re.I)
        group = re.search(r'skupine\s+(.+?)(?=\.\s+čas|$)', b, re.I)
        tm = re.search(r'čas\s+([0-9:]+\s*-\s*[0-9:]+)', b, re.I)

        subj = re.split(r'\.\s+profesor\s+|,\s+profesor\s+', b, maxsplit=1, flags=re.I)[0].strip(' .,')
        # Extended stay is often encoded as "PB. Podaljšano bivanje. 12:41 - 16:20" without teacher/room.
        pb = re.match(r'PB\.\s*Podaljšano bivanje(?:\.\s*([0-9:]+\s*-\s*[0-9:]+))?$', b, re.I)
        if pb:
            item['code'] = 'PB'
            item['subject'] = 'Podaljšano bivanje'
            if pb.group(1):
                item['item_time'] = pb.group(1)
            items.append(item)
            continue

        if subj:
            item['subject'] = subj
        if teacher:
            item['teacher'] = teacher.group(1).strip(' .,')
        if room:
            item['room'] = room.group(1).strip(' .,')
        if group:
            item['group'] = group.group(1).strip(' .,')
        if tm:
            item['item_time'] = tm.group(1).strip()
        items.append(item)
    return items


def parse_week(page):
    times = extract_times(page)
    days = {}
    for hour, date, body in extract_cells(page):
        sr = re.search(r'<span\b[^>]*class="[^"]*public-urnik-sr-only[^"]*"[^>]*>(.*?)</span>', body, re.S | re.I)
        sr_text = clean(sr.group(1)) if sr else ''
        if not sr_text or 'brez vsebine' in sr_text.lower():
            continue

        code_match = re.search(r'<td\b[^>]*class="[^"]*ednevnik-title[^"]*"[^>]*>.*?<span>(.*?)</span>', body, re.S | re.I)
        if not code_match:
            code_match = re.search(r'<div\b[^>]*class="[^"]*ednevnik-title[^"]*"[^>]*>(.*?)</div>', body, re.S | re.I)
        code = clean(code_match.group(1)) if code_match else None
        items = parse_sr(sr_text)
        if code and len(items) == 1:
            items[0]['code'] = code

        days.setdefault(date, []).append({
            'hour': hour,
            'time': times.get(hour),
            'items': items,
            'raw': sr_text
        })

    for entries in days.values():
        entries.sort(key=lambda z: z['hour'])
    return dict(sorted(days.items()))


def student_url(s):
    return f"{BASE}/{s['school_id']}/razredi/{s['class_id']}/dijak/{s['student_id']}"


def ajax_url(s, week, qversion=1):
    return f"{BASE}/ajax_urnik/{s['school_id']}/{s['class_id']}/0/{s['student_id']}/0/{week}/0/{qversion}"


def safe_name(name):
    x = re.sub(r'[^a-zA-Z0-9_-]+', '_', name.strip().lower()).strip('_')
    return x or 'student'


def process_student(s, cfg):
    base_html = fetch(student_url(s))
    server_class = extract_var(base_html, 'id_razred')
    server_student = extract_var(base_html, 'id_dijak')
    week = extract_var(base_html, 'teden')
    if not week or not week.isdigit():
        raise RuntimeError('Na osnovni strani ni mogoče določiti trenutnega tedna.')
    if server_class and server_class != str(s['class_id']):
        raise RuntimeError(f"class_id mismatch: config={s['class_id']} page={server_class}")
    if server_student and server_student != str(s['student_id']):
        raise RuntimeError(f"student_id mismatch: config={s['student_id']} page={server_student}")

    result = {
        'name': s['name'],
        'school_id': str(s['school_id']),
        'class_id': str(s['class_id']),
        'student_id': str(s['student_id']),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'current_week_number': int(week),
        'weeks': {}
    }
    if cfg['output'].get('current_week', True):
        result['weeks']['current'] = {'week_number': int(week), 'days': parse_week(base_html)}
    if cfg['output'].get('next_week', True):
        nxt = int(week) + 1
        payload = fetch(ajax_url(s, nxt, 1))
        result['weeks']['next'] = {'week_number': nxt, 'days': parse_week(ajax_payload_to_html(payload))}
    return result


def main():
    ap = argparse.ArgumentParser(description='Scrape public eAsistent timetables into JSON.')
    ap.add_argument('-c', '--config', default='config.json')
    args = ap.parse_args()
    cfg_path = Path(args.config)
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    output = cfg.setdefault('output', {})
    output.setdefault('directory', 'data')
    output.setdefault('current_week', True)
    output.setdefault('next_week', True)
    outdir = (cfg_path.parent / output['directory']).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for s in cfg.get('students', []):
        if not s.get('enabled', True):
            continue
        try:
            data = process_student(s, cfg)
            path = outdir / f"urnik_{safe_name(s['name'])}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f"OK  {s['name']}: {path}")
        except (KeyError, ValueError, RuntimeError, HTTPError, URLError) as e:
            failures += 1
            print(f"ERR {s.get('name','?')}: {e}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
