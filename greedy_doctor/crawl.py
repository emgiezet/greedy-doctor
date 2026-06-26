"""Worker crawl: pobiera oswiadczenia z danego zrodla do DB (status 'downloaded').

Niezalezny od GPU — czyste I/O. Idempotentny: nie pobiera ponownie tego, co juz mamy.
Kazde zrodlo (sources/<x>.py) wystawia jednolite `iter_declarations(client) -> (name, year,
pdf_url)`; HTML-owe (Kielce/Poznan) parsuja strony, API-owe (dolnoslaskie) wolaja REST.
Sklejka sieciowa walidowana e2e; logika parsowania per-zrodlo jest przetestowana osobno.
"""

import argparse
import importlib
import pkgutil
import time

import httpx

from greedy_doctor import db
from greedy_doctor import sources as _sources_pkg


def _discover_sources():
    """Auto-rejestracja zrodel: kazdy sources/<name>.py z CITY + iter_declarations
    laduje pod kluczem <name>. ponytail: pkgutil zamiast recznej listy importow —
    nowe zrodlo rejestruje sie samo (rownolegli agenci nie koliduja na wspolnym dict).
    try/except izoluje zepsute WIP-zrodlo, by nie wywalic calego CLI."""
    found = {}
    for mod in pkgutil.iter_modules(_sources_pkg.__path__):
        try:
            m = importlib.import_module(f"greedy_doctor.sources.{mod.name}")
        except Exception as e:  # noqa: BLE001 — izolacja zepsutego zrodla
            print(f"[crawl] pomijam zrodlo {mod.name}: {e}")
            continue
        if hasattr(m, "CITY") and hasattr(m, "iter_declarations"):
            found[mod.name] = m
    return found


SOURCES = _discover_sources()
HEADERS = {"User-Agent": "greedy-doctor/0.1 (badania danych publicznych BIP)"}


def _upsert_radny(conn, city, name):
    cur = conn.execute(
        "INSERT INTO radny (city, name) VALUES (%s, %s) "
        "ON CONFLICT (city, name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (city, name),
    )
    return cur.fetchone()[0]


def _records(src, client):
    """Normalizuje wpisy zrodla do (name, year, pdf_url, landing_url).

    Zrodla ze strona radnego na BIP zwracaja 4-tuple z landing_url; zrodla 'tylko PDF'
    zwracaja 3-tuple (landing_url=None). ponytail: dwa ksztalty to realny podzial zrodel
    (6 ma strone radnego, 7 nie — patrz sources/*.py), nie spekulacja.
    """
    for rec in src.iter_declarations(client):
        name, year, pdf_url = rec[:3]
        landing_url = rec[3] if len(rec) > 3 else None
        yield name, year, pdf_url, landing_url


def crawl(source_name, delay=0.3):
    src = SOURCES[source_name]
    new = 0
    verify = getattr(src, "VERIFY", True)
    with httpx.Client(timeout=60, follow_redirects=True, headers=HEADERS, verify=verify) as client:
        with db.connect() as conn:
            for name, year, pdf_url, landing_url in _records(src, client):
                rid = _upsert_radny(conn, src.CITY, name)
                have = conn.execute(
                    "SELECT 1 FROM declaration WHERE radny_id=%s AND year=%s",
                    (rid, year),
                ).fetchone()
                if have:
                    continue
                time.sleep(delay)
                pdf = client.get(pdf_url).content
                conn.execute(
                    "INSERT INTO declaration "
                    "(radny_id, year, source_url, landing_url, pdf_data, status) "
                    "VALUES (%s, %s, %s, %s, %s, 'downloaded')",
                    (rid, year, pdf_url, landing_url, pdf),
                )
                new += 1
            conn.commit()
    return new


def backfill_landing(source_name):
    """Komplementarny crawl: dociaga landing_url (strone radnego na BIP) do ISTNIEJACYCH
    wierszy — bez ponownego pobierania PDF. Re-uzywa parsowania zrodla (te same name/year),
    matchuje po (city, name, year). Idempotentny: rusza tylko wiersze z landing_url IS NULL.
    """
    src = SOURCES[source_name]
    filled = 0
    verify = getattr(src, "VERIFY", True)
    with httpx.Client(timeout=60, follow_redirects=True, headers=HEADERS, verify=verify) as client:
        with db.connect() as conn:
            for name, year, _pdf, landing_url in _records(src, client):
                if not landing_url:
                    continue
                cur = conn.execute(
                    "UPDATE declaration SET landing_url=%s "
                    "WHERE year=%s AND landing_url IS NULL AND radny_id="
                    "(SELECT id FROM radny WHERE city=%s AND name=%s)",
                    (landing_url, year, src.CITY, name),
                )
                filled += cur.rowcount
            conn.commit()
    return filled


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="kielce")
    p.add_argument(
        "--backfill",
        action="store_true",
        help="dociagnij landing_url do istniejacych wierszy (bez pobierania PDF)",
    )
    args = p.parse_args()
    db.init_schema()
    if args.backfill:
        print(f"uzupelniono landing_url: {backfill_landing(args.source)}")
    else:
        print(f"pobrano nowych oswiadczen: {crawl(args.source)}")
