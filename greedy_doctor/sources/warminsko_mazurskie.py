"""Adapter zrodla: Sejmik Województwa Warmińsko-Mazurskiego (kadencja VII, 2024-2029).

BIP Urzedu Marszalkowskiego (bip.warmia.mazury.pl) to Yii2 (PHP). Strona deklaracji majatkowych
('/kategoria/46/oswiadczenia-majatkowe.html') to listing z odniesnieniami do stron rocznych
(jeden artykul per rok). Kazda strona roczna segmentuje PDF-y w blokach <details><summary>:

  <details><summary>Radni Województwa - oświadczenia za rok YYYY</summary>
    <ul><li><a href="/upload/files/oswiadczenia/zlozone_{YEAR}/...">Nazwisko Imie</a></li>
    ...
  </details>

Strony roczne:
  2024 (pliki za 2023 r.) -> /3096/oswiadczenia-majatkowe-zlozone-w-2024-roku.html
  2025 (pliki za 2024 r.) -> /3609/oswiadczenia-majatkowe-zlozone-w-2025-roku.html
  2026 (pliki za 2025 r.) -> /4127/oswiadczenia-majatkowe-zlozone-w-2026-roku.html

Pulapki obsluzone:
- WIELE SEKCJI NA STRONIE. Kazda strona ma kilka blokow <details>: Czlonkowie Zarzadu,
  Radni - koniec kadencji, Radni - za rok YYYY, Radni - poczatek kadencji, Dyrektorzy
  Jednostek Organizacyjnych, Prezesi Spolek. Bierzemy TYLKO bloki, ktorych <summary>
  zawiera 'Radni' ORAZ 'za rok' (case-insensitive). Dyrektorzy, Zarzad i inne sekcje
  wypadaja przez sam filtr sekcji.
- NAZWY Z KOTWICY, NIE Z NAZWY PLIKU. Tekst kotwicy podaje pelne imie i nazwisko z
  polskimi znakami (np. 'Grażyna', 'Żelichowski'). Format juz 'Nazwisko Imie' —
  nie odwracamy.
- ROK Z NAZWY PLIKU. Wzorzec '_za_(?:rok_)?(YYYY)' w nazwie pliku (case-insensitive;
  '..._ZA_2025.pdf' tez). Rok to rok dochodowy, nie rok zlozenia.
- KOREKTY. Pliki z 'korekta' w nazwie (case-insensitive) odrzucamy. W sekcji rocznej
  radnych takie pliki nie powinny sie pojawic, ale BIP bywa niespojny.
- URL-ENCODED NAZWY. Plik 'Homza_Zbigniew_o%C5%9Bwiadczenie_ZA_2025.pdf' ma 'ZA' (duze).
  Regex jest case-insensitive.
- ZAMAN TARGET. Niektorzy Czlonkowie Zarzadu maja 'za_2023_rok' (rok po 'za'), nie
  'za_rok_2023'. Odsiana przez filtr sekcji (sa w 'Czlonkowie Zarzadu', nie w 'Radni
  ... za rok'). Wzorzec '_za_(?:rok_)?YYYY' takze dziala dla 'za_2023_rok' — ale to
  nie przeszkadza, bo sekcja Zarzadu i tak jest wykluczona.

VERIFY = False — BIP ma niepelny lancuch TLS (brak posredniego CA); crawl.py czyta
getattr(src, 'VERIFY', True) i buduje klienta z verify=VERIFY.

PDF-y maja warstwe tekstowa (pdfplumber dziala). Parsowanie czyste (HTML -> dane),
bez sieci; sciaganie robi crawl.py. ponytail: id artykulow rocznych zahardcodowane
(zweryfikowane na zywym BIP); nowy rocznik -> dodac (rok, id) do YEAR_PAGES.
"""

import html
import re
import time
from urllib.parse import unquote

CITY = "Sejmik Województwa Warmińsko-Mazurskiego"
BASE = "https://bip.warmia.mazury.pl"
# ponytail: BIP ma niepelny lancuch TLS — crawl.py czyta VERIFY i buduje klienta z verify=VERIFY.
VERIFY = False
# Strona roczna per ROK (id strony i slug). Nowy rocznik -> dodac (rok, id) do YEAR_PAGES.
YEAR_PAGES = {
    2024: 3096,
    2025: 3609,
    2026: 4127,
}

# Blok <details>...<summary>tekst</summary>...zawartosc...</details>.
# Zakladamy, ze bloki nie sa zagniezdzone (CMS generuje plaska liste sekcji).
_DETAILS = re.compile(r"<details>(.*?)</details>", re.S | re.I)
_SUMMARY = re.compile(r"<summary>(.*?)</summary>", re.S | re.I)
# Link PDF w bloku sekcji: href "/upload/files/oswiadczenia/zlozone_{YEAR}/..." + tekst kotwicy.
_LINK = re.compile(
    r'<a[^>]*href="(/upload/files/oswiadczenia/[^"]+\.pdf)"[^>]*>([^<]*)</a>',
    re.I,
)
# Rok dochodowy z nazwy pliku: '_za_rok_2024.pdf', '_za_2024.pdf', '_ZA_2025.pdf'.
# Dopasowanie case-insensitive; URL-encoded wersje odkodujesz przed przeszukaniem.
_ZA_YEAR = re.compile(r"_za_(?:rok_)?(\d{4})", re.I)


def _page_url(submission_year, page_id):
    """Kanoniczny URL strony rocznej: /{id}/oswiadczenia-majatkowe-zlozone-w-{rok}-roku.html"""
    return f"{BASE}/{page_id}/oswiadczenia-majatkowe-zlozone-w-{submission_year}-roku.html"


def _is_radni_annual_section(summary_html):
    """True, gdy <summary> odnosi sie do sekcji rocznej oswiadczen radnych.

    Filtrujemy po 'radni' (radny/radnych) ORAZ 'za rok' — odsiewa Zarzad, Dyrektorzy,
    Prezesow i snapshoty ('poczatek kadencji', 'koniec kadencji').
    """
    txt = html.unescape(summary_html).lower()
    return "radni" in txt and "za rok" in txt


def parse_link(href, anchor_text):
    """(href PDF, tekst kotwicy) -> (name, year, pdf_url) lub None.

    Odrzuca korekty (slowo 'korekta' w href — case-insensitive). Rok z '_za_(?:rok_)?YYYY'
    w nazwie pliku (URL-decoded). Nazwa = html.unescape(tekst kotwicy), bez kresek/daty
    po myslniku (anchor w sekcji radnych to samo nazwisko+imie lub z dopiskiem za YYYY).
    pdf_url absolutny.
    """
    href_decoded = unquote(href)
    if "korekta" in href_decoded.lower():
        return None
    m = _ZA_YEAR.search(href_decoded)
    if not m:
        return None
    year = int(m.group(1))
    name = " ".join(html.unescape(anchor_text).split())
    # Odsiewamy puste nazwy oraz opisy typu 'X - oświadczenie za YYYY rok'
    # Bierzemy czesc przed myslnikiem i spacja (czesto pelna nazwa bez dopisku);
    # ale gdy caly tekst to 'Nazwisko Imie' — zostawiamy jak jest.
    # W sekcji radnych teksty to zwykle 'Nazwisko Imie' lub 'Nazwisko Imie - korekta' (korekty juz wykluczone).
    # Dla Czlonkow Zarzadu: 'Bartnicki Bogdan - oswiadczenie za 2023 rok' — ale ta sekcja jest
    # wykluczona przez _is_radni_annual_section, wiec tu nie wchodzimy.
    if " - " in name:
        name = name.split(" - ")[0].strip()
    return (name, year, BASE + href) if name else None


def parse_page(page_html):
    """HTML strony rocznej -> [(name, year, pdf_url), ...].

    Bierze tylko sekcje <details> z <summary> zawierajacym 'Radni' i 'za rok'.
    W kazdej takiej sekcji parsuje linki PDF z _za_YYYY w nazwie pliku (bez korekt).
    Dedup per name w obrebie jednej strony (nie per (name, year) — to robi iter_declarations).
    """
    out, seen = [], set()
    for block in _DETAILS.findall(page_html):
        m = _SUMMARY.search(block)
        if not m or not _is_radni_annual_section(m.group(1)):
            continue
        for href, anchor in _LINK.findall(block):
            parsed = parse_link(href, anchor)
            if not parsed:
                continue
            name, year, pdf_url = parsed
            key = (name, year)
            if key in seen:
                continue
            seen.add(key)
            out.append((name, year, pdf_url))
    return out


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per roczne oswiadczenie radnego.

    Jeden GET na strone roczna (per rok z YEAR_PAGES). Dedup per (name, year) miedzy
    stronami. Jezeli GET strony rocznej sie nie uda, pomijamy rok cicho (try/except).
    """
    seen = set()
    for submission_year, page_id in YEAR_PAGES.items():
        time.sleep(0.3)
        try:
            page = client.get(_page_url(submission_year, page_id)).text
        except Exception:  # noqa: BLE001 — strona roczna moze nie byc jeszcze opublikowana
            continue
        for name, year, pdf_url in parse_page(page):
            if (name, year) in seen:
                continue
            seen.add((name, year))
            yield name, year, pdf_url
