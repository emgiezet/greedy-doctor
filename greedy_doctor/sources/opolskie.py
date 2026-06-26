"""Adapter zrodla: Sejmik Wojewodztwa Opolskiego (kadencja VII, 2024-2029).

BIP Urzedu Marszalkowskiego (bip.opolskie.pl) to WordPress. Oswiadczenia to zwykle wpisy
(post) z datowanym permalinkiem; nie ma publicznego custom-post-type/taksonomii, wiec listujemy
przez WP REST: /wp-json/wp/v2/posts?search=... (zwraca id, date, link, title). PDF wisi na
stronie wpisu pod /wp-content/uploads/{RRRR}/{MM}/{Nazwisko}-{Imie}-...pdf (nazwy plikow NIE da
sie wyprowadzic — czytamy href ze strony; pomijamy duplikaty z /uploads/revisions/).

KLUCZOWE: rok w TYTULE/slugu to rok ZLOZENIA, nie rok fiskalny. Roczne oswiadczenie 'za 2024'
jest opublikowane w 2025 (post /2025/.., plik '...-za-2024-r.pdf'); '30 dni od slubowania'
(post /2024/.., plik '...-zlozone-30-dni.pdf') to SNAPSHOT na poczatek kadencji -> pomijamy.
Dlatego rok fiskalny i typ bierzemy z NAZWY PLIKU PDF ('za <rok> r' = roczne), nie z tytulu.

Pulapki obsluzone:
- szum w wynikach search: wpis 'HARMONOGRAM ... Radnych Wojewodztwa Opolskiego' ma w linku
  'radnych-wojewodztwa-opolskiego' (l.mn.) — filtr po 'radny-/radna-wojewodztwa-opolskiego'
  (l.poj.) go odrzuca.
- /uploads/revisions/<id>/ to wersje robocze tego samego PDF — bierzemy tylko kanoniczny
  /uploads/{RRRR}/{MM}/.
- dedup per (name, rok); imie w tytule to 'Imie Nazwisko' -> odwracamy do 'Nazwisko Imie'.

PDF-y to skany -> OCR robi extract.py. Parsowanie czyste (dane wejsciowe: JSON listy + HTML
wpisu), bez sieci; sciaganie robi crawl.py. ponytail: zapytanie search jako jedyna konfiguracja;
per_page=100 miesci cala kadencje na 1 stronie (gdyby przekroczyc 100 — dodac paginacje).
"""

import re

CITY = "Sejmik Województwa Opolskiego"
BASE = "https://bip.opolskie.pl"
SEARCH_URL = (
    f"{BASE}/wp-json/wp/v2/posts"
    "?search=Radny+Wojew%C3%B3dztwa+Opolskiego+kadencja+VII+2024-2029"
    "&per_page=100&_fields=id,date,link,title"
)
MIN_YEAR = 2024

# Imie+nazwisko z tytulu: 'Oswiadczenie majatkowe – <rok>, <Imie Nazwisko>, Radny ...'.
_TITLE_NAME = re.compile(r"[–-]\s*\d{4}\s*,\s*([^,]+?)\s*,\s*Rad", re.I)
# Kanoniczny PDF wpisu (z pominieciem /uploads/revisions/).
_PDF = re.compile(rf'{re.escape(BASE)}/wp-content/uploads/20\d\d/\d\d/[^"\']+?\.pdf', re.I)
# Rok fiskalny rocznego oswiadczenia z nazwy pliku ('...za-2024-r...').
_ANNUAL = re.compile(r"za[-_ ]?(20\d\d)[-_ ]?r", re.I)


def is_councilor_post(post: dict) -> bool:
    """True dla wpisu-oswiadczenia radnego (link z 'radny-/radna-wojewodztwa-opolskiego')."""
    link = (post.get("link") or "").lower()
    return "radny-wojewodztwa-opolskiego" in link or "radna-wojewodztwa-opolskiego" in link


def parse_name(title: str):
    """Tytul wpisu -> 'Nazwisko Imie' (tytul ma 'Imie Nazwisko'), albo None."""
    m = _TITLE_NAME.search(title or "")
    if not m:
        return None
    parts = m.group(1).split()
    if len(parts) < 2:
        return None
    given, *surname = parts
    return " ".join([*surname, given])


def parse_pdf_url(page_html: str):
    """Strona wpisu -> kanoniczny URL PDF (/uploads/RRRR/MM/...), albo None."""
    m = _PDF.search(page_html)
    return m.group(0) if m else None


def annual_year(pdf_url: str):
    """Rok fiskalny rocznego oswiadczenia z nazwy pliku ('za <rok> r'); None gdy snapshot/30-dni."""
    m = _ANNUAL.search(pdf_url or "")
    return int(m.group(1)) if m else None


def iter_declarations(client):
    """(name, year, pdf_url) per roczne oswiadczenie radnego; snapshoty '30 dni' pominiete.

    WP REST -> lista wpisow; per radny GET strony wpisu -> kanoniczny PDF -> rok z nazwy pliku.
    """
    posts = client.get(SEARCH_URL).json()
    seen = set()
    for post in posts:
        if not is_councilor_post(post):
            continue
        name = parse_name((post.get("title") or {}).get("rendered", ""))
        if not name:
            continue
        page = client.get(post["link"]).text
        pdf_url = parse_pdf_url(page)
        if not pdf_url:
            continue
        year = annual_year(pdf_url)
        if year is None or year < MIN_YEAR or (name, year) in seen:
            continue
        seen.add((name, year))
        yield name, year, pdf_url
