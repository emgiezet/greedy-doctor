"""Worker crawl: pobiera oswiadczenia z danego zrodla do DB (status 'downloaded').

Niezalezny od GPU — czyste I/O. Idempotentny: nie pobiera ponownie tego, co juz mamy.
Kazde zrodlo (sources/<x>.py) wystawia jednolite `iter_declarations(client) -> (name, year,
pdf_url)`; HTML-owe (Kielce/Poznan) parsuja strony, API-owe (dolnoslaskie) wolaja REST.
Sklejka sieciowa walidowana e2e; logika parsowania per-zrodlo jest przetestowana osobno.
"""

import argparse
import time

import httpx

from greedy_doctor import db
from greedy_doctor.sources import (
    dolnoslaskie,
    gdansk,
    gdynia,
    kielce,
    nowytomysl,
    pomorskie,
    poznan,
    sopot,
    wielkopolskie,
)

SOURCES = {
    "kielce": kielce,
    "poznan": poznan,
    "dolnoslaskie": dolnoslaskie,
    "nowytomysl": nowytomysl,
    "pomorskie": pomorskie,
    "wielkopolskie": wielkopolskie,
    "gdansk": gdansk,
    "sopot": sopot,
    "gdynia": gdynia,
}
HEADERS = {"User-Agent": "greedy-doctor/0.1 (badania danych publicznych BIP)"}


def _upsert_radny(conn, city, name):
    cur = conn.execute(
        "INSERT INTO radny (city, name) VALUES (%s, %s) "
        "ON CONFLICT (city, name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (city, name),
    )
    return cur.fetchone()[0]


def crawl(source_name, delay=0.3):
    src = SOURCES[source_name]
    new = 0
    with httpx.Client(timeout=60, follow_redirects=True, headers=HEADERS) as client:
        with db.connect() as conn:
            for name, year, pdf_url in src.iter_declarations(client):
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
                    "INSERT INTO declaration (radny_id, year, source_url, pdf_data, status) "
                    "VALUES (%s, %s, %s, %s, 'downloaded')",
                    (rid, year, pdf_url, pdf),
                )
                new += 1
            conn.commit()
    return new


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="kielce")
    args = p.parse_args()
    db.init_schema()
    print(f"pobrano nowych oswiadczen: {crawl(args.source)}")
