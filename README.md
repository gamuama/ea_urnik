# eAsistent public timetable scraper

Majhen Python scraper, ki javni eAsistent urnik pretvori v JSON. Namenjen je uporabi brez prijave na javno dostopnih urnikih, katerih URL vsebuje `school_id`, `class_id` in `student_id`.

## Lastnosti

- ena skripta za poljubno število otrok;
- vsak otrok je lahko na drugi šoli;
- trenutni teden se prebere iz osnovne eAsistent strani, zato ga ni treba ročno nastavljati;
- po želji prenese tudi naslednji teden;
- prazne ure izpusti;
- ohrani kratko oznako predmeta, polni opis, učitelja, učilnico, skupino in surovi accessibility opis, kadar so podatki na voljo;
- podpira več sklopov znotraj iste ure;
- uporablja samo Python standardno knjižnico, zato `requirements.txt` ni potreben.

## Zahteve

- Python 3.9+ priporočeno
- omrežni dostop do `https://urniki.easistent.com`
- javni eAsistent urnik posameznega učenca

## Namestitev

```bash
cp config.example.json config.json
```

Nato uredi `config.json`.

## Konfiguracija

```json
{
  "students": [
    {
      "name": "Otrok",
      "school_id": "YOUR_SCHOOL_ID",
      "class_id": "YOUR_CLASS_ID",
      "student_id": "YOUR_STUDENT_ID",
      "enabled": true
    }
  ],
  "output": {
    "directory": "data",
    "current_week": true,
    "next_week": true
  }
}
```

Za več otrok samo dodaj nove vnose v `students`. `school_id` je namenoma pri vsakem otroku posebej, zato lahko ena konfiguracija vsebuje otroke iz različnih šol.

Primer URL-ja, iz katerega se prepoznajo ID-ji:

```text
https://urniki.easistent.com/urniki/SCHOOL_ID/razredi/CLASS_ID/dijak/STUDENT_ID
```

## Zagon

```bash
python3 easistent_urnik.py
```

ali z drugo konfiguracijo:

```bash
python3 easistent_urnik.py --config moja-konfiguracija.json
```

Rezultat je privzeto zapisan v:

```text
data/urnik_otrok.json
```

## JSON rezultat

Vsaka neprazna ura vsebuje številko ure, čas in enega ali več `items`. Kadar eAsistent ponudi oba podatka, se shrani kratka oznaka (`code`) in polno ime (`subject`).

Primer:

```json
{
  "hour": 7,
  "time": "13:35 - 14:20",
  "items": [
    {
      "code": "MAT",
      "subject": "MATEMATIKA",
      "teacher": "Ucitelj",
      "room": "GE"
    }
  ]
}
```

## Priporočeni `.gitignore`

Dejanskega `config.json` ne objavljaj, če vsebuje imena ali identifikatorje otrok.

```gitignore
config.json
data/
__pycache__/
*.pyc
```

V javnem repozitoriju objavi `config.example.json`, ne svoje produkcijske konfiguracije.

## Omejitve prve verzije

Scraper je vezan na trenutno HTML strukturo javnega eAsistent urnika. eAsistent ni API tega projekta in lahko HTML ali AJAX format spremeni. Polje `raw` je zato namenoma ohranjeno kot pomoč pri diagnostiki in prihodnjih prilagoditvah parserja.

Projekt naj dostopa samo do urnikov, za katere ima uporabnik ustrezno dovoljenje oziroma so mu legitimno namenjeni.
