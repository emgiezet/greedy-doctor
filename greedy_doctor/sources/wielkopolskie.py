"""Adapter zrodla: Sejmik Wojewodztwa Wielkopolskiego. BIP na CMS HSI (NIE Madkom — brak /api/).

Organizacja per ROK: podstrona roczna 'za YYYY rok' linkuje do podstron PER RADNY
(blok 'czytaj wiecej', href 7---k_62---k_63---k_<NNN>---<slug>); nazwisko bierzemy z atrybutu
title="Imie Nazwisko - czytaj wiecej". Na podstronie radnego jest bezposredni link PDF
(../artykuly/<id>/pliki/<plik>.pdf, rozwiazywany urljoin). PDF to SKANY bez warstwy tekstowej
(pdfplumber -> 0 znakow) -> extract robi fallback OCR. Sejmik traktujemy jak 'miasto' (pole city).

Parsowanie czyste (HTML -> dane), bez sieci — testowalne na fixture. Sciaganie robi crawl.py.
ponytail: httpx + html.unescape (strona statyczna, encje jak w Kielcach/Poznaniu). Podstrony
roczne zahardcodowane (zweryfikowane); kategoria w linkach radnych zmienia sie per rok
(2024: k_368, 2025: k_379), wiec matchujemy ja wzorcem, nie na sztywno.
"""

import html
import re
from urllib.parse import urljoin

CITY = "Sejmik Wielkopolski"
BASE = "https://bip.umww.pl"
# Aktualna kadencja (VII, 2024-2029). Index listuje tez lata 2018-2023 — pomijamy.
YEAR_PAGES = {
    2024: BASE
    + "/7---k_62---k_63---k_radni-wojewodztwa--oswiadczenia-majatkowe-za-2024-rok",
    2025: BASE
    + "/7---k_62---k_63---k_radni-wojewodztwa--oswiadczenia-majatkowe-za-2025-rok",
}

# Link do podstrony radnego: blok 'czytaj wiecej'. Kategoria (k_368/k_379) zmienna per rok,
# wiec dopuszczamy dowolne k_<NNN>; nazwisko z atrybutu title (ma polskie znaki, w odroznieniu od sluga).
_RADNY = re.compile(
    r'<a[^>]+href="(7---k_62---k_63---k_\d+---[a-z0-9-]+)"[^>]*title="([^"]+?)\s*-\s*czytaj',
    re.I,
)
# Bezposredni link PDF na podstronie radnego (zalacznik artykulu).
_PDF = re.compile(r'href="([^"]*pliki/[^"]+\.pdf)"', re.I)


def _surname_first(full):
    """'Leszek Bierla' -> 'Bierla Leszek' (nazwisko = ostatni token; myslnik w nazwisku OK)."""
    toks = full.split()
    return " ".join([toks[-1], *toks[:-1]]) if toks else ""


def parse_year_page(page_html):
    """HTML podstrony rocznej -> [('Nazwisko Imie', url_radnego), ...] (unikalne, posortowane)."""
    src = html.unescape(page_html)
    out = {}
    for href, name in _RADNY.findall(src):
        out[urljoin(BASE + "/", href)] = _surname_first(name.strip())
    return sorted((name, url) for url, name in out.items())


def parse_radny_page(page_html, page_url):
    """HTML podstrony radnego -> pelny URL pierwszego PDF (oswiadczenie), albo None.

    Jeden plik per oswiadczenie roczne; te same href powtarza sie (ikona + link tekstowy) -> dedup.
    """
    src = html.unescape(page_html)
    m = _PDF.search(src)
    return urljoin(page_url, m.group(1)) if m else None


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url, landing_url) per oswiadczenie radnego sejmiku."""
    import time

    for year, year_url in YEAR_PAGES.items():
        for name, radny_url in parse_year_page(client.get(year_url).text):
            time.sleep(0.3)
            pdf_url = parse_radny_page(client.get(radny_url).text, radny_url)
            if pdf_url:
                yield name, year, pdf_url, radny_url
