"""Adapter zrodla: Sejmik Województwa Lubuskiego. BIP na CMS SystemDoBIP (E-LINE).

Listing pod /oswiadczenia/343/{strona}/rok/ zawiera WSZYSTKICH skladajacych oswiadczenia
(radnych, czlonkow zarzadu, dyrektorow, skarbnika itp.) — paginowany, 20 wierszy/strona,
sortowanie malejace po ID (najnowsze pierwsze). Kazdy wiersz niesie od razu:
  - grupe (td-group): filtrujemy do 'Radni Województwa Lubuskiego'
  - rok (td-date-year): filtrujemy do >= MIN_YEAR
  - imie i nazwisko: tekst kotwicy przed <br>, np. 'Jerzy Wierchowicz - kolejne'
  - link PDF (pobierz.php): bezposrednio w td-attachments-1, bez przechodzenia na strone szczegolów

Nie uzywamy filtra POST (wymaga sesji z cookie) — zwykly GET paginowany.
Wczesne zatrzymanie: gdy cala strona nie zawiera zadnego wpisu z rokiem >= MIN_YEAR.

Pulapki obsluzone:
- KOLEJNOSC SLOW w tekscie: 'Imie Nazwisko' (np. 'Jerzy Wierchowicz') — odwracamy do
  'Nazwisko Imie' (np. 'Wierchowicz Jerzy'). Ostatnie slowo = nazwisko (dotyczy tez
  nazwisk wieloczlonowych: 'Andrzej Leszek Wieczorek' -> 'Wieczorek Andrzej Leszek').
- Sufix ' - kolejne', ' - pierwsze', ' - koncowe LUW' itp. odcinamy po ' - '.
- Rok w td-date-year moze miec spacje przed cyfra (np. '<div>Rok</div> 2024').
- Brak zalacznika (brak pobierz.php) -> pomijamy wiersz.
- Dedup (name, year): ten sam radny sklada kilka oswiadczen w tej samej kadencji/roku
  (np. 'pierwsze' na poczatku + 'kolejne' roczne); bierzemy tylko pierwsze napotkane.
"""

import html
import re
import time

CITY = "Sejmik Lubuski"
BASE = "https://bip.lubuskie.pl"
LISTING_URL = BASE + "/oswiadczenia/343/{page}/rok/"
MIN_YEAR = 2024  # biezaca kadencja 2024-2029; starsze pomijamy
RADNI_GROUP = "Radni Województwa Lubuskiego"

# Wiersz tabeli — caly <tr>...</tr> (DOTALL).
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)

# Grupa (td-group).
_GROUP = re.compile(r'<td[^>]*class="td-group"[^>]*>.*?<div>[^<]*</div>(.*?)</td>', re.S | re.I)

# Rok (td-date-year). Moze byc '<div>Rok</div>2024' lub '<div>Rok</div> 2024' (spacja).
_YEAR = re.compile(r'<td[^>]*class="td-date-year"[^>]*>.*?<div>[^<]*</div>\s*(\d{4})', re.S | re.I)

# Imie i Nazwisko: tekst kotwicy osoby, az do <br> (bez pozycji po <br>).
# np. 'Jerzy Wierchowicz - kolejne' lub 'Andrzej Leszek Wieczorek - pierwsze'.
_NAME_RAW = re.compile(
    r'<div>[^<]*Imi[^<]*</div>\s*<a [^>]*>\s*(.*?)<br', re.S | re.I
)

# Link do PDF: pobierz.php?plik=...&id=... (caly url do pobierz.php).
_PDF = re.compile(
    r'href="(https?://[^"]*pobierz\.php\?[^"]+)"', re.I
)


def parse_name(raw):
    """Surowy tekst kotwicy -> 'Nazwisko Imie' lub None.

    Wejscie: 'Andrzej Leszek Wieczorek - pierwsze' (po html.unescape).
    Odcinamy sufiks ' - ...' (typ oswiadczenia), normalizujemy biale znaki,
    odwracamy kolejnosc slow: ostatnie slowo staje sie pierwszym (= nazwisko).
    """
    name = html.unescape(raw or "").strip()
    # Odtnij sufiks: ' - kolejne', ' - pierwsze', ' - koncowe', itp.
    idx = name.find(" - ")
    if idx >= 0:
        name = name[:idx]
    name = " ".join(name.split())
    if not name:
        return None
    parts = name.split()
    # Ostatnie slowo to nazwisko; reszte traktujemy jako imiona.
    return " ".join([parts[-1]] + parts[:-1])


def parse_listing_page(page_html):
    """HTML strony listingu -> [(name, year, pdf_url), ...] dla radnych >= MIN_YEAR.

    Filtruje wiersze po grupie == RADNI_GROUP i roku >= MIN_YEAR. Pomija wiersze
    bez zalacznika PDF. Zwraca czyste krotki; dedup nalezy do iter_declarations.
    """
    src = html.unescape(page_html)
    out = []
    for row_m in _ROW.finditer(src):
        row = row_m.group(1)

        # Filtr: tylko radni
        gm = _GROUP.search(row)
        if not gm:
            continue
        group = " ".join(html.unescape(gm.group(1)).split())
        if group != RADNI_GROUP:
            continue

        # Filtr: rok >= MIN_YEAR
        ym = _YEAR.search(row)
        if not ym:
            continue
        year = int(ym.group(1))
        if year < MIN_YEAR:
            continue

        # Imie i Nazwisko
        nm = _NAME_RAW.search(row)
        if not nm:
            continue
        name = parse_name(nm.group(1))
        if not name:
            continue

        # PDF
        pm = _PDF.search(row)
        if not pm:
            continue
        pdf_url = pm.group(1)

        out.append((name, year, pdf_url))
    return out


def has_any_min_year(page_html):
    """Czy strona zawiera choc jeden wpis z rokiem >= MIN_YEAR (dowolna grupa).

    Uzywane do wczesnego zatrzymania paginacji: jesli nie ma juz zadnych nowych
    wpisow, konczymy obchod.
    """
    src = html.unescape(page_html)
    for m in _YEAR.finditer(src):
        if int(m.group(1)) >= MIN_YEAR:
            return True
    return False


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per oswiadczenie radnego.

    Paginuje przez /oswiadczenia/343/{page}/rok/ (GET). Zatrzymuje sie gdy cala
    strona nie zawiera zadnego wpisu z rokiem >= MIN_YEAR. Dedup per (name, year).
    """
    seen = set()
    page = 1
    while True:
        try:
            time.sleep(0.3)
            resp = client.get(LISTING_URL.format(page=page))
            page_html = resp.text
        except Exception:
            page += 1
            continue

        # Wczesne zatrzymanie: brak jakichkolwiek wpisow z nowego okresu
        if not has_any_min_year(page_html):
            break

        for name, year, pdf_url in parse_listing_page(page_html):
            key = (name, year)
            if key in seen:
                continue
            seen.add(key)
            yield name, year, pdf_url

        page += 1
