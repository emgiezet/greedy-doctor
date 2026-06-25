"""Adapter zrodla: Sejmik Wojewodztwa Dolnoslaskiego. Zrodlo API-owe (REST JSON, httpx).

Organizacja per ROK: wezel 'za YYYY' -> /api/menu/{id}/articles -> /api/articles/{id}
-> attachments[] (PDF). Czesc PDF to skany bez warstwy tekstowej -> extract robi fallback
OCR. Sejmik traktujemy jak 'miasto' (pole city). ponytail: wezly roczne zahardcodowane
(zweryfikowane); nowe lata dodac, albo chodzic po /api/menu.
"""

import re
import time

CITY = "Sejmik Dolnośląski"
BASE = "https://bip.dolnyslask.pl"
YEAR_NODES = {2024: 2782, 2025: 2847}


def parse_name(title: str) -> str:
    """'Mirosław Lubiński - radny...' -> 'Lubiński Mirosław' (nazwisko = ostatni token)."""
    head = title.split(" - ")[0].strip()
    toks = head.split()
    return " ".join([toks[-1], *toks[:-1]]) if toks else ""


def is_annual(title: str) -> bool:
    """Roczne 'oswiadczenie za YYYY'; pomijamy korekty i 'na rozpoczecie kadencji'."""
    t = title.lower()
    return (
        "korekt" not in t
        and "rozpocz" not in t
        and re.search(r"za\s+20\d\d", t) is not None
    )


def iter_declarations(client):
    """(name, year, pdf_url) dla rocznych oswiadczen radnych sejmiku; dedup per (nazwisko, rok)."""
    for year, node in YEAR_NODES.items():
        arts = client.get(f"{BASE}/api/menu/{node}/articles?limit=200").json()[
            "articles"
        ]
        seen = set()
        for a in arts:
            time.sleep(0.2)
            art = client.get(f"{BASE}/api/articles/{a['id']}").json()
            title = art.get("title") or ""
            if not is_annual(title):
                continue
            name = parse_name(title)
            if not name or name in seen:
                continue
            seen.add(name)
            for att in art.get("attachments", []):
                yield name, year, f"{BASE}/{att['link']}"
                break  # jeden plik per oswiadczenie
