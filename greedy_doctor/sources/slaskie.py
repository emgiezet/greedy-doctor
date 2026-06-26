"""Adapter zrodla: Sejmik Wojewodztwa Slaskiego. BIP na CMS SmartSite (BIT Sp. z o.o.) —
NIE Madkom (brak /api/), wiec HTML scrape jak Kielce/Poznan/Wielkopolska.

Organizacja per RADNY -> per ROK -> per DOKUMENT (3 poziomy nawigacji 'p=', wszystkie
to bezstanowe deep-linki — cold GET dziala):
  1. Listing (paginowany ?page=1..N): kazdy radny to <a href="?p=Nazwisko@Imie"
     title="Nazwisko Imie"> w bloku Bip_PageList. Tytul jest JUZ 'Nazwisko Imie'
     (kolejnosc jak w kontrakcie) — nie odwracamy. Separator nazwisko/imie to '@'
     (url-encoded %40). Strona kumuluje WSZYSTKICH, co kiedykolwiek skladali (radni
     poprzednich kadencji tez) -> filtrujemy po roku.
  2. Strona radnego (?p=Nazwisko@Imie): linki roczne ?p=Nazwisko@Imie^YYYY (tekst kotwicy
     = sam rok; '^' to %5E). Bierzemy tylko lata >= MIN_YEAR (biezaca kadencja 2024-2029).
  3. Strona roku (?p=...^YYYY): linki do podstron-dokumentow
     /sejmik_wojewodztwa/oswiadczenia_majatkowe/<slug>.html (tekst '1. Oswiadczenie...').
  4. Podstrona dokumentu: bezposredni link PDF /resource/<id>/<nazwa>.pdf.

PULAPKA — wezel roczny ^YYYY MIESZA typy oswiadczen, a ordinal ('1.'/'2.') ich NIE
rozroznia. Typ siedzi w NAZWIE PLIKU PDF:
  'Oswiadczenie majatkowe za 2024 rok_...'              -> ROCZNE (bierzemy)
  'Oswiadczenie majatkowe na poczatek/poczatku kadencji_...' -> snapshot (pomijamy)
  'Oswiadczenie majatkowe na koniec kadencji_...'        -> snapshot konca POPRZEDNIEJ
                                                            kadencji (pomijamy)
  'Oswiadczenie majatkowe_wygasniecie mandatu_...'       -> snapshot (pomijamy)
  'Korekta oswiadczenia majatkowego...'                  -> korekta (pomijamy)
Dlatego is_annual_filename() dziala na nazwie pliku PDF: wymaga 'za YYYY rok' i odrzuca
'korekt'. Zweryfikowane na zywym BIP: 147 dokumentow pod wezlami 2024 -> dokladnie 45
rocznych (= liczba radnych biezacej kadencji), 0 kolizji 'za YYYY rok' z 'korekta'.

UWAGA — nazwa pliku w href jest PODWOJNIE url-encoded (np. '%25C5%259B' = '%C5%9B' = 's'
z kreska, zakodowane raz jeszcze). httpx/curl wysylaja sciezke doslownie i serwer zwraca
PDF (HTTP 200) — wiec pdf_url to href verbatim, bez dekodowania. Do ROZPOZNANIA typu
dekodujemy nazwe dwukrotnie (czysto lokalnie, nie do pobierania).

PDF-y to SKANY (pdfplumber: 5 stron, ~170 znakow — tylko stopka 'Wylaczenia jawnosci',
reszta to obraz) -> extract robi fallback OCR (tesseract -l pol). Sejmik traktujemy jak
'miasto' (pole city).

2025 jeszcze NIE opublikowane na BIP (stan: tylko 2019-2024); MIN_YEAR=2024 sprawia, ze
nowe roczniki (2025+) wejda automatycznie, gdy sie pojawia — bez zmian w kodzie. Dedup
per (nazwisko, rok). Parsowanie czyste (HTML -> dane), bez sieci; sciaganie robi crawl.py.
ponytail: httpx + html.unescape + re (strona statyczna, silnik przegladarki to narzut).
"""

import html
import re
import time
from urllib.parse import unquote, urljoin

CITY = "Sejmik Śląski"
BASE = "https://bip.slaskie.pl"
LISTING_URL = BASE + "/sejmik_wojewodztwa/oswiadczenia_majatkowe"
MIN_YEAR = 2024  # biezaca kadencja (2024-2029); pomijamy archiwum 2019-2023 (inne kadencje)

# Listing: radny = <a href="?p=Nazwisko@Imie" title="Nazwisko Imie"> (bez '^' = bez roku).
# Blok Bip_PageList nie miesza tu pozycji menu, ale i tak wymagamy '%40' (@) i braku '%5E' (^).
_RADNY = re.compile(
    r'<a href="(\?p=[^"]*%40[^"]*?)"\s+title="([^"]+)"', re.I
)
# Strona radnego: link roczny ?p=...%5EYYYY (tekst kotwicy = rok).
_YEAR_LINK = re.compile(r'href="(\?p=[^"]*%5E(20\d\d))"', re.I)
# Strona roku: podstrona-dokument oswiadczenia (.html w katalogu oswiadczenia_majatkowe).
_DOC_LINK = re.compile(
    r'href="(/sejmik_wojewodztwa/oswiadczenia_majatkowe/[^"?]+\.html)"', re.I
)
# Podstrona dokumentu: bezposredni link PDF z biblioteki /resource/<id>/<nazwa>.pdf.
_PDF_LINK = re.compile(r'href="(/resource/\d+/[^"]+\.pdf)"', re.I)


def parse_listing(page_html):
    """HTML strony listingu -> [('Nazwisko Imie', url_radnego), ...] (unikalne, posortowane).

    Tytul w atrybucie title= jest juz 'Nazwisko Imie' — normalizujemy tylko biale znaki
    i encje HTML. url_radnego to absolutny deep-link ?p=Nazwisko@Imie (bezstanowy).
    """
    src = html.unescape(page_html)
    out = {}
    for href, title in _RADNY.findall(src):
        if "%5E" in href:  # to juz link roczny, nie wpis radnego
            continue
        name = " ".join(html.unescape(title).split())
        if name:
            out[urljoin(LISTING_URL, href)] = name
    return sorted((name, url) for url, name in out.items())


def parse_year_links(page_html):
    """HTML strony radnego -> [(rok, url_roku), ...] dla lat >= MIN_YEAR (unikalne, rosnaco).

    Lata < MIN_YEAR (archiwum poprzednich kadencji) pomijamy.
    """
    src = html.unescape(page_html)
    out = {}
    for href, year in _YEAR_LINK.findall(src):
        y = int(year)
        if y >= MIN_YEAR:
            out[y] = urljoin(LISTING_URL, href)
    return sorted(out.items())


def parse_doc_links(page_html):
    """HTML strony roku -> absolutne URL-e podstron-dokumentow (unikalne, posortowane)."""
    src = html.unescape(page_html)
    return sorted({urljoin(BASE, h) for h in _DOC_LINK.findall(src)})


def is_annual_filename(pdf_href, year):
    """Czy nazwa pliku PDF to ROCZNE oswiadczenie 'za <year> rok' (a nie snapshot/korekta).

    Nazwa w href jest podwojnie url-encoded; dekodujemy dwukrotnie, '+' -> spacja.
    Roczne: zawiera 'za YYYY rok'. Odrzucamy korekty (nawet gdyby kiedys dotyczyly rocznego).
    """
    fname = unquote(unquote(pdf_href.split("/")[-1])).replace("+", " ").lower()
    if "korekt" in fname:
        return False
    return re.search(rf"za\s+{year}\s+rok", fname) is not None


def parse_pdf_url(page_html):
    """HTML podstrony dokumentu -> pelny URL PDF (href verbatim — podwojne kodowanie zostaje)."""
    src = html.unescape(page_html)
    m = _PDF_LINK.search(src)
    return urljoin(BASE, m.group(1)) if m else None


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url, landing_url) per roczne oswiadczenie radnego.

    Chodzimy: listing (paginowany) -> radny -> rok(>=MIN_YEAR) -> dokument -> PDF.
    Bierzemy tylko pliki 'za YYYY rok' (is_annual_filename); dedup per (nazwisko, rok),
    bo pod jednym wezlem rocznym potrafi byc kilka dokumentow.
    """
    # 1) zbierz wszystkich radnych ze wszystkich stron listingu (paginacja ?page=N)
    radni = {}
    page = 1
    while True:
        url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
        rows = parse_listing(client.get(url).text)
        new = {url_: name for name, url_ in rows if url_ not in radni}
        if not new:
            break  # ta strona nie wniosla nowych radnych -> koniec paginacji
        radni.update(new)
        page += 1
        time.sleep(0.2)

    # 2) dla kazdego radnego: lata >= MIN_YEAR -> dokumenty -> roczne PDF-y
    for radny_url, name in sorted(radni.items(), key=lambda kv: kv[1]):
        time.sleep(0.2)
        for year, year_url in parse_year_links(client.get(radny_url).text):
            time.sleep(0.2)
            for doc_url in parse_doc_links(client.get(year_url).text):
                time.sleep(0.2)
                pdf_url = parse_pdf_url(client.get(doc_url).text)
                if pdf_url and is_annual_filename(pdf_url, year):
                    yield name, year, pdf_url, radny_url
                    break  # jeden roczny plik per (radny, rok)
