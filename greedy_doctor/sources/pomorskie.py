"""Adapter zrodla: Sejmik Wojewodztwa Pomorskiego. CMS Madkom (REST API jak dolnoslaskie),
ale radni per OSOBA: jeden artykul/radny, zalaczniki = wszystkie oswiadczenia danej osoby
przez lata. Drzewo: /api/menu/119 -> dziecko id 652 'Kadencja 2024-2029'
-> /api/menu/652/articles (~33 radnych) -> /api/articles/{id} (title='Nazwisko Imie',
attachments[] = PDF-y). Rok kodowany w NAZWIE zalacznika jako data stanu:
'...31 grudnia 2024 roku' lub '...31.12.2024 r.'. PDF-y to SKANY (brak warstwy tekstowej)
-> extract robi OCR (tesseract). Sejmik traktujemy jak 'miasto' (pole city).

PUlapki obsluzone:
- czlonkowie Zarzadu (np. Bonna, Mielewczyk) maja dwa oswiadczenia za ten sam rok
  (jako Radny + jako Wicemarszalek/Zarzad) -> dedup per (nazwisko, rok).
- pomijamy korekty oraz oswiadczenia 'na dzien powolania/wyboru/rezygnacji/zakonczenia
  kadencji' i 'na dwa miesiace przed uplywem kadencji' (data != 31 grudnia).
- artykul kumuluje historie VI kadencji (2020-2023) -> bierzemy tylko MIN_YEAR+ (bieząca).
ponytail: id wezla kadencji (652) zahardcodowany (zweryfikowany); nowa kadencja -> nowy id.
"""

import re
import time

CITY = "Sejmik Pomorski"
BASE = "https://www.bip.pomorskie.eu"
KADENCJA_NODE = 652
MIN_YEAR = 2024  # node 652 = kadencja 2024-2029; pomijamy stara historie VI kadencji


def parse_name(title: str) -> str:
    """Title artykulu to juz 'Nazwisko Imie' (np. 'Bonna Leszek'). Normalizujemy biale znaki."""
    return " ".join((title or "").split())


def annual_year(att_name: str):
    """Rok rocznego oswiadczenia z nazwy zalacznika, albo None gdy to nie jest roczne.

    Akceptujemy tylko stan na koniec roku ('31 grudnia YYYY' / '31.12.YYYY').
    Odrzucamy korekty oraz daty inne niz 31.12 (powolanie/wybor/rezygnacja/kadencja).
    """
    name = (att_name or "").lower()
    if "korekt" in name:
        return None
    # '31 grudnia 2024' (slownie)
    m = re.search(r"31\s+grudnia\s+(20\d\d)", name)
    if m:
        return int(m.group(1))
    # '31.12.2024' (z kropkami, ewentualne spacje)
    m = re.search(r"31\s*\.\s*12\s*\.\s*(20\d\d)", name)
    if m:
        return int(m.group(1))
    return None


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
