"""Adapter zrodla: Sejmik Wojewodztwa Malopolskiego. CMS Madkom (REST API jak dolnoslaskie/
pomorskie/sopot — front to AngularJS SPA, dane leca z /api/menu i /api/articles).

Organizacja per OSOBA (jak pomorskie): wezel menu 'Oswiadczenia majatkowe -> Radni
Wojewodztwa -> 2024-2029' (id 439367) ma ~39 artykulow, jeden na radnego. Title artykulu
to juz 'Nazwisko Imie' (czysty unicode z /api/articles/{id}; w listingu bywa z encjami HTML).
Zalaczniki artykulu = wszystkie oswiadczenia danej osoby (skany PDF), rok kodowany w NAZWIE
zalacznika jako 'za YYYY rok'. PDF-y to SKANY (pdfplumber -> 0 znakow, sam BIP pisze
'zamieszczone jako skany dokumentow') -> extract robi fallback OCR. Sejmik traktujemy jak
'miasto' (pole city).

Pulapki obsluzone:
- pomijamy snapshot 'na poczatek kadencji 2024_2029' (brak 'za YYYY') i wszystkie korekty.
  UWAGA: korekta tez ma w nazwie 'za 2024 rok' (a literowka 'korektoa' nadal zaczyna sie
  od 'korekt') -> filtr korekty MUSI isc przed wyciaganiem roku.
- 'za2024' bez spacji (radny Duda) -> regex dopuszcza brak biale znaku po 'za'.
- dwoch roznych radnych 'Duda' ma rozne title ('Duda Jan' vs 'Duda Jan Tadeusz') -> nie zlewamy.
- dedup per (nazwisko, rok) na wypadek dwoch zalacznikow za ten sam rok.
ponytail: id wezla kadencji (439367) zahardcodowany (zweryfikowany); ukladu per-osoba nie
trzeba rozbijac per rok — nowe lata (2025+) doloza sie same jako kolejne zalaczniki, gdy
sejmik je opublikuje. Nowa kadencja -> nowy id wezla.

Stan na 2026-06: opublikowane sa tylko oswiadczenia 'za 2024' (39 radnych) + snapshoty
poczatkowe; 'za 2025' jeszcze nie ma w BIP.
"""

import re
import time

CITY = "Sejmik Małopolski"
BASE = "https://bip.malopolska.pl"
# Wezel 'Radni Wojewodztwa -> 2024-2029' pod 'Oswiadczenia majatkowe'. type=N, listuje artykuly per radny.
KADENCJA_NODE = 439367
MIN_YEAR = 2024  # biezaca kadencja; gdyby w artykule wisialy starsze oswiadczenia, pomijamy je


def parse_name(title: str) -> str:
    """Title artykulu to juz 'Nazwisko Imie' (np. 'Arkit Tadeusz'). Normalizujemy biale znaki."""
    return " ".join((title or "").split())


def annual_year(att_name: str):
    """Rok rocznego oswiadczenia z nazwy zalacznika, albo None gdy to nie roczne.

    Akceptujemy 'za YYYY' (z dowolnym/zerowym odstepem po 'za', np. 'za2024').
    Odrzucamy korekty (slowo 'korekt...', tez literowka 'korektoa') ORAZ snapshot
    'na poczatek kadencji' (nie ma w nazwie 'za YYYY', wiec wypadnie sam).
    """
    name = (att_name or "").lower()
    if "korekt" in name:
        return None
    m = re.search(r"\bza\s*(20\d\d)\b", name)
    return int(m.group(1)) if m else None


def iter_declarations(client):
    """(name, year, pdf_url) dla rocznych oswiadczen radnych sejmiku; dedup per (nazwisko, rok)."""
    arts = client.get(f"{BASE}/api/menu/{KADENCJA_NODE}/articles?limit=200").json()[
        "articles"
    ]
    for a in arts:
        time.sleep(0.2)
        art = client.get(f"{BASE}/api/articles/{a['id']}").json()
        name = parse_name(art.get("title") or "")
        if not name:
            continue
        seen = set()
        for att in art.get("attachments", []):
            if att.get("deleted"):
                continue
            year = annual_year(att.get("name", ""))
            if year is None or year < MIN_YEAR or year in seen:
                continue
            link = att.get("link")
            if not link:
                continue
            seen.add(year)
            yield name, year, f"{BASE}/{link}"
