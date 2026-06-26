"""Adapter zrodla: Sejmik Województwa Kujawsko-Pomorskiego (kadencja VII, 2024-2029).

BIP Urzedu Marszalkowskiego (bip.kujawsko-pomorskie.pl) stoi na RBIP v4. Oswiadczenia
wszystkich osob z urzedu leza w jednym wykazie pod /4578/798/wykaz-oswiadczen.html,
paginowanym po 10 wynikow na stronie (~26 stron dla 2024, ~17 dla 2025).

Pulapki obsluzone:
- LISTING ZAWIERA WIELE RODZAJOW OSWIADCZEN: radni, czlonkowie zarzadu, sekretarz itp.
  Filtrujemy po slugu URL: bierzemy tylko pozycje z 'oswiadczenie-radnego-wojewodztwa'
  LUB 'oswiadczenie-radnej-wojewodztwa' LUB 'oswiadczenie-majatkowe-radnego-wojewodztwa'
  ORAZ 'za-YYYY-r' w URL. Pomijamy 'na-poczatku-kadencji', 'na-koniec-kadencji', korekty.
- KOLEJNOSC ODWROTNA: tytul w <strong> to 'Imie Nazwisko - ...' -> odwracamy do
  'Nazwisko Imie' (kontrakt). Pierwszy token = imie, reszta = nazwisko.
- DWUETAPOWE POBIERANIE: listing daje URL strony szczegolowej (nie bezposrednio PDF);
  PDF to /download/attachment/{attId}/{plik}.pdf na stronie szczegolowej.
- LICZBA STRON: wyciagamy z 'Liczba wynikow: NNN' podzielonego przez PAGE_SIZE=10.
- WARIANT MAJATKOWY: od 2025 czesc radnych ma sluga
  '...-oswiadczenie-majatkowe-radnego-wojewodztwa-...' (np. Piotr Calbecki) obok
  standardowego '...-oswiadczenie-radnego-wojewodztwa-...'. Oba sa rownowazne.
"""

import html
import math
import re
import time

CITY = "Sejmik Województwa Kujawsko-Pomorskiego"
BASE = "https://bip.kujawsko-pomorskie.pl"

# Strona wykazu i parametry paginacji
WYKAZ_PATH = "/4578/798/wykaz-oswiadczen.html"
PAGE_SIZE = 10  # ile wynikow na strone (staly parametr BIP)
YEARS = (2024, 2025)

# Slug URL radnego (roczne oswiadczenie): 'oswiadczenie-radnego-wojewodztwa' lub
# 'oswiadczenie-radnej-wojewodztwa' lub 'oswiadczenie-majatkowe-radnego-wojewodztwa',
# zawierajacy 'za-YYYY-r'. Pomijamy 'na-poczatku-kadencji' etc. przez sam dobor wzorca.
_RADNY_SLUG = re.compile(
    r"oswiadczenie-(?:majatkowe-)?radne(?:go|j)-wojewodztwa.*?za-(\d{4})-r"
)

# Link pozycji listingu: URL strony szczegolowej w cct-item__name + tytul w <strong>.
_ITEM = re.compile(
    r'<a href="(https://bip\.kujawsko-pomorskie\.pl/[^"]+)"[^>]*>\s*'
    r"<strong>([^<]+)</strong>",
    re.S,
)

# Laczna liczba wynikow w paginacji (do obliczenia liczby stron).
_TOTAL = re.compile(r"Liczba wynik[oó]w:\s*<b>(\d+)</b>")

# Link do PDF na stronie szczegolowej: /download/attachment/{id}/{plik}.pdf
_PDF = re.compile(r'href="(https?://bip\.kujawsko-pomorskie\.pl/download/attachment/\d+/[^"]+\.pdf)"')


def surname_first(title_raw):
    """'Imie Nazwisko - tytul...' (imie pierwsze) -> 'Nazwisko Imie'. Pierwszy token = imie."""
    # tytul to np. 'Zbigniew Ostrowski - oświadczenie radnego...'
    name_part = html.unescape(title_raw).split(" - ")[0].strip()
    parts = name_part.split()
    if len(parts) < 2:
        return " ".join(parts)
    given, *rest = parts
    return " ".join([*rest, given])


def parse_listing(page_html, year):
    """HTML strony listingu -> [(name, year, detail_url), ...] dla radnych danego roku.

    Bierze tylko pozycje, ktorych URL zawiera wzorzec radnego i rok 'za-YYYY-r'.
    Pomija korekty i snapshoty przez filtr _RADNY_SLUG. Tytul z <strong> odwracamy
    do 'Nazwisko Imie'. dedup per (name, year).
    """
    out, seen = [], set()
    for href, title in _ITEM.findall(page_html):
        slug = href.rsplit("/", 1)[-1]  # ostatni segment URL
        m = _RADNY_SLUG.search(slug)
        if not m:
            continue
        if int(m.group(1)) != year:
            continue
        name = surname_first(title)
        if not name or (name, year) in seen:
            continue
        seen.add((name, year))
        out.append((name, year, href))
    return out


def parse_total_pages(page_html):
    """HTML strony listingu -> laczna liczba stron (zaokraglona w gore)."""
    m = _TOTAL.search(page_html)
    if not m:
        return 1
    return max(1, math.ceil(int(m.group(1)) / PAGE_SIZE))


def parse_pdf_url(detail_html):
    """HTML strony szczegolowej radnego -> absolutny URL pierwszego PDF, albo None."""
    m = _PDF.search(detail_html)
    return m.group(1) if m else None


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per roczne oswiadczenie radnego.

    Dla kazdego roku: paginator po listingu -> zbieram (name, year, detail_url);
    nastepnie GET na kazda strone szczegolowa -> PDF. sleep 0.3 miedzy kazdym GET.
    Dedup per (name, year).
    """
    seen = set()
    for year in YEARS:
        # Strona 1 - poznajemy liczbe stron
        time.sleep(0.3)
        try:
            first_page = client.get(
                BASE + WYKAZ_PATH
                + f"?t3_f37={year}&is_content_type_search=1&Page=1"
            ).text
        except Exception:
            continue
        total_pages = parse_total_pages(first_page)
        # Zbieramy (name, year, detail_url) ze wszystkich stron listingu
        detail_items = []
        page_html = first_page
        for page_num in range(1, total_pages + 1):
            if page_num > 1:
                time.sleep(0.3)
                try:
                    page_html = client.get(
                        BASE + WYKAZ_PATH
                        + f"?t3_f37={year}&is_content_type_search=1&Page={page_num}"
                    ).text
                except Exception:
                    continue
            for name, yr, detail_url in parse_listing(page_html, year):
                if (name, yr) not in seen:
                    detail_items.append((name, yr, detail_url))
                    seen.add((name, yr))
        # Dla kazdej znalezionej strony szczegolowej pobieramy PDF
        for name, yr, detail_url in detail_items:
            time.sleep(0.3)
            try:
                detail_html = client.get(detail_url).text
            except Exception:
                continue
            pdf_url = parse_pdf_url(detail_html)
            if not pdf_url:
                continue
            yield name, yr, pdf_url
