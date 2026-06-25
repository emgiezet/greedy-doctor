"""Adapter zrodla: Kielce (statyczny BIP, PDF z warstwa tekstowa).

Parsowanie jest czyste (HTML -> dane), bez sieci — testowalne na fixture.
Sciaganie robi crawl.py. ponytail: httpx + html.unescape zamiast crawl4ai/playwright —
strona jest statyczna, silnik przegladarki to tu czysty narzut. crawl4ai wejdzie przy
miastach renderowanych JS (Warszawa).
"""

import html
import re

CITY = "Kielce"
BASE = "https://bipum.kielce.eu"
LISTING_URL = (
    BASE + "/rada-miasta-kielce/oswiadczenia-majatkowe/"
    "oswiadczenia-majatkowe-radnych-kadencji-20242029/"
)

# strona radnego: .../kadencji-<cyfry>/<slug>.html (slug = nazwisko-imie, lowercase)
_RADNY_HREF = re.compile(r'href="([^"]*kadencji-\d+/[a-z0-9-]+\.html)"')
# link do PDF zalacznika + tekst kotwicy (z ktorego bierzemy rok)
_PDF_ANCHOR = re.compile(
    r'<a[^>]+href="([^"]*resource[^"]*\.pdf)"[^>]*>(.*?)</a>', re.S | re.I
)
_YEAR = re.compile(r"za\s+(\d{4})\s+rok", re.I)
_TITLE = re.compile(r"<title>(.*?)\s*-\s*Witryna", re.S | re.I)


def _abs(href):
    return href if href.startswith("http") else BASE + href


def parse_listing(page_html):
    """HTML listingu kadencji -> posortowane, unikalne URL-e stron radnych."""
    src = html.unescape(page_html)
    return sorted({_abs(h) for h in _RADNY_HREF.findall(src)})


def parse_person(page_html):
    """HTML strony radnego -> (imie_nazwisko, [(rok, url_pdf), ...]).

    Bierzemy tylko roczne oswiadczenia 'za YYYY rok' (maja dochod, rubryka VIII);
    snapshoty 'na rozpoczecie kadencji' pomijamy (brak roku -> brak kolizji UNIQUE).
    """
    src = html.unescape(page_html)
    m = _TITLE.search(src)
    name = m.group(1).strip() if m else None
    docs = set()
    for href, anchor in _PDF_ANCHOR.findall(src):
        text = re.sub(r"<[^>]+>", "", anchor)
        ym = _YEAR.search(text)
        if ym:
            docs.add((int(ym.group(1)), _abs(href)))
    return name, sorted(docs)


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per oswiadczenie."""
    import time

    for purl in parse_listing(client.get(LISTING_URL).text):
        time.sleep(0.3)
        name, docs = parse_person(client.get(purl).text)
        if not name:
            continue
        for year, pdf_url in docs:
            yield name, year, pdf_url
