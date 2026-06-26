"""Adapter zrodla: Poznan. Statyczny BIP, ale oswiadczenia to SKANY -> wymagaja OCR.

Parsowanie czyste (HTML -> dane), bez sieci. Sciaganie: crawl.py (httpx, link lz_id
zwraca PDF wprost). Ekstrakcja: extract.py kieruje skany do olmocr.
"""

import html
import re

CITY = "Poznań"
BASE = "https://bip.poznan.pl"
LISTING_URL = BASE + "/bip/radni/"

_PROFILE = re.compile(r'href="(/bip/radni/[a-z0-9-]+,\d+/?)"')
_ATTACH = re.compile(r'href="([^"]*zalaczniki[^"]*lz_id=\d+)"')
# nazwisko z alt zdjecia profilowego (alt="Imie Nazwisko" width=...)
_ALT_NAME = re.compile(r'alt="([A-ZŁŚŻŹĆŃÓ][^"\s]*(?: [A-ZŁŚŻŹĆŃÓ][^"\s]*)+)"\s+width=')
_YEAR = re.compile(r"za\s+(?:rok\s+)?(\d{4})", re.I)


def _abs(href):
    return href if href.startswith("http") else BASE + href


def _surname_first(full):
    """'Grzegorz Ganowicz' -> 'Ganowicz Grzegorz' (nazwisko = ostatni token)."""
    toks = full.split()
    return " ".join([toks[-1], *toks[:-1]])


def parse_listing(page_html):
    src = html.unescape(page_html)
    return sorted(
        {_abs(h if h.endswith("/") else h + "/") for h in _PROFILE.findall(src)}
    )


def parse_person(page_html):
    """HTML profilu -> ('Nazwisko Imie', [(rok, url_pdf), ...]).
    Tylko roczne 'za YYYY'; snapshot 'Pierwsze oswiadczenie w kadencji' pomijamy.
    Etykieta roku stoi PRZED linkiem -> bierzemy ostatnie 'za YYYY' z okna przed nim."""
    src = html.unescape(page_html)
    m = _ALT_NAME.search(src)
    name = _surname_first(m.group(1)) if m else None
    docs = set()
    for am in _ATTACH.finditer(src):
        label = re.sub(r"<[^>]+>", " ", src[max(0, am.start() - 260) : am.start()])
        years = _YEAR.findall(label)
        if years:
            docs.add((int(years[-1]), _abs(am.group(1))))
    return name, sorted(docs)


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url, landing_url) per oswiadczenie."""
    import time

    for purl in parse_listing(client.get(LISTING_URL).text):
        time.sleep(0.3)
        name, docs = parse_person(client.get(purl).text)
        if not name:
            continue
        for year, pdf_url in docs:
            yield name, year, pdf_url, purl
