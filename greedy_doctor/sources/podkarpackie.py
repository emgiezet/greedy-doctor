"""Adapter zrodla: Sejmik Wojewodztwa Podkarpackiego (kadencja VII, 2024-2029).

BIP Urzedu Marszalkowskiego (bip.podkarpackie.pl) to Joomla + komponent `com_govarticle`.
Brak uzytecznego API JSON; oswiadczenia radnych leza w kategoriach PER ROK, a sam rok jest
w SCIEZCE kategorii (nie w nazwie zalacznika):
  2024 -> /oswiadczenia-majatkowe/2024/radni-wojewodztwa-vii-kadencja-2024
  2025 -> /oswiadczenia-majatkowe/2025/radni-wojewodztwa
Snapshoty/stare kadencje maja WLASNE kategorie (poczatek-vii-kadencji, koniec-vi-kadencji,
vi-kandencja-do-30-04-2024 [literowka zrodla]) i tu nie wchodza — pomijamy je przez sam dobor
slugu w YEAR_CATEGORIES.

Kazdy radny to wiersz tabeli z linkiem komponentu:
  <a href="/component/govarticle?task=article.downloadAttachment&amp;id={ID}&amp;version={VER}"
     title="Pobierz zalacznik: NAZWISKO IMIE"> ...
Pulapki obsluzone:
- PARAMETR `version` JEST OBOWIAZKOWY: bez niego endpoint zwraca HTTP 500. Wyciagamy id ORAZ
  version z href (w zrodle '&' jest jako '&amp;' -> html.unescape).
- NAZWA = atrybut title ('NAZWISKO IMIE', nazwisko-pierwsze, WERSALIKI). Rok 2025 ze spacja
  ('BARAN BRONISLAW'), rok 2024 z podkresleniem ('BARAN_BRONISLAW') -> normalizujemy '_'/biale
  znaki. Kolejnosc juz nazwisko-pierwsze; werslaiki zostawiamy (klasyfikator dopasowuje po PDF,
  DB kluczuje po (city, name)).
- ten sam link bywa w wierszu dwa razy (ikona + tekst) -> dedup per nazwa.

PDF-y to SKANY -> OCR robi extract.py. Parsowanie czyste (HTML -> dane), bez sieci; sciaganie
robi crawl.py. ponytail: slugi kategorii rocznych zahardcodowane (zweryfikowane na zywym BIP);
nowy rok -> dodac (rok, slug) do YEAR_CATEGORIES.
"""

import html
import re
import time

CITY = "Sejmik Województwa Podkarpackiego"
BASE = "https://bip.podkarpackie.pl"
# ponytail: BIP ma niepelny lancuch TLS (brak posredniego CA) — crawl.py czyta VERIFY i buduje
# klienta z verify=VERIFY. Gdy BIP naprawi cert -> True.
VERIFY = False
# Kategoria roczna radnych per ROK (rok w sciezce). Snapshoty/stare kadencje swiadomie pominiete.
YEAR_CATEGORIES = {
    2024: "oswiadczenia-majatkowe/2024/radni-wojewodztwa-vii-kadencja-2024",
    2025: "oswiadczenia-majatkowe/2025/radni-wojewodztwa",
}

# Link pobrania zalacznika + nazwa radnego w atrybucie title.
_ANCHOR = re.compile(
    r'<a href="(/component/govarticle\?task=article\.downloadAttachment[^"]*)"'
    r'[^>]*title="Pobierz załącznik:\s*([^"]*)"',
    re.I,
)
_IDV = re.compile(r"id=(\d+).*?version=(\d+)")


def normalize_name(title_name: str) -> str:
    """'NAZWISKO IMIE' / 'NAZWISKO_IMIE' -> 'NAZWISKO IMIE' (nazwisko-pierwsze, WERSALIKI)."""
    return " ".join(html.unescape(title_name).replace("_", " ").split())


def parse_pdf_url(href_raw: str):
    """href komponentu (z '&amp;') -> absolutny URL z OBOWIAZKOWYM id+version, albo None."""
    href = html.unescape(href_raw)
    if not _IDV.search(href):
        return None
    return BASE + href


def parse_listing(page_html: str, year: int):
    """HTML kategorii rocznej -> [(name, year, pdf_url), ...], dedup per nazwa.

    Bierze id ORAZ version z kazdego linku (version obowiazkowy). Ten sam radny linkowany
    dwa razy (ikona+tekst) scala sie po nazwie.
    """
    out, seen = [], set()
    for href_raw, title_name in _ANCHOR.findall(page_html):
        name = normalize_name(title_name)
        pdf_url = parse_pdf_url(href_raw)
        if not name or not pdf_url or name in seen:
            continue
        seen.add(name)
        out.append((name, year, pdf_url))
    return out


def iter_declarations(client):
    """(name, year, pdf_url) per roczne oswiadczenie radnego; dedup per (name, year)."""
    seen = set()
    for year, slug in YEAR_CATEGORIES.items():
        time.sleep(0.3)
        try:
            page = client.get(f"{BASE}/{slug}").text
        except Exception:  # noqa: BLE001 — rocznik moze nie byc jeszcze opublikowany -> pomijamy
            continue
        for name, yr, pdf_url in parse_listing(page, year):
            if (name, yr) in seen:
                continue
            seen.add((name, yr))
            yield name, yr, pdf_url
