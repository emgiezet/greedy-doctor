"""Adapter zrodla: Sejmik Wojewodztwa Lubelskiego (kadencja 7, 2024-2029).

BIP Urzedu Marszalkowskiego (umwl.bip.lubelskie.pl) to wlasny CMS na TYPO3 ('System BIP',
*.bip.lubelskie.pl). Oswiadczenia majatkowe radnych sa NA JEDNEJ stronie (`index.php?id=113`),
serwerowo wyrenderowane w bootstrapowym akordeonie `#person-assets-accordion` — BEZ paginacji
i BEZ JS (cialo akordeonu jest w HTML nawet gdy wizualnie zwiniete). Pliki leza plasko w
`upload/pliki/`. Brak API JSON.

Listing filtrujemy parametrem kadencji: `id=113&filters[2][]=1094` = 'Kadencja 7 [2024-2029]'.
Bez filtra id=113 pokazuje wszystkich ~60 radnych historycznych; z filtrem ~35 obecnych.
ponytail: page id `113` i filtr `filters[2][]=1094` zahardcodowane (zweryfikowane na zywym BIP)
— prostsze i stabilniejsze niz rozpoznawanie kadencji z UI.

Struktura: kazdy radny = `<div class="card card-toggle-expand">`; w naglowku
`<a href="?id=osoba&p1={pid}" ...>Nazwisko Imie</a>` (nazwisko-pierwsze, z polskimi znakami).
W ciele wiersze `<div class="row mb-2">`: `col-sm-1` = ROK, `col-sm-8` = OPIS typu oswiadczenia,
`col-sm-3` = `<a href="upload/pliki/{plik}.pdf">`. Nazwy plikow sa DOWOLNE i NIE da sie ich
wyprowadzic ('oswiadczenie-majatkowe-k.babisz.pdf', '0Mulawa_Michal.pdf') — zawsze czytamy href.

Pulapki obsluzone:
- FILTR KADENCJI ZAWEZA OSOBY, NIE WIERSZE: karta radnego z poprzedniej kadencji niesie tez
  stare PDF-y (rok < 2024). Filtrujemy wiersze po `year >= MIN_YEAR` (=2024). Publikowane lata
  obecnej kadencji to 2024 i 2025.
- WIELE WPISOW NA (osoba, rok): roczne 'oswiadczenie majatkowe za 2024 r.' wspolistnieje ze
  snapshotem 'poczatek kadencji', z 'korekta ...' i z 'wyjasnienie ...'. Typ jest w OPISIE
  (col-sm-8), nie w nazwie pliku. Zostawiamy JEDEN na (osoba, rok):
  * snapshoty 'poczatek kadencji' -> odrzucamy (NAWET 'korekta ... na poczatek kadencji'),
  * 'wyjasnienie ...' -> odrzucamy,
  * sposrod prawdziwych rocznikow: 'korekta ... za <rok>' BIJE zwykly rocznik (nowsza wersja),
  * zwykly rocznik bez markera to baza.

PDF-y to skany/teksty mieszane; ekstrakcja (extract.py) sama dobiera sciezke. Parsowanie czyste
(HTML -> dane), bez sieci; sciaganie robi crawl.py.
"""

import html
import re

CITY = "Sejmik Województwa Lubelskiego"
BASE = "https://umwl.bip.lubelskie.pl"
# ponytail: id strony + filtr kadencji 7 zahardcodowane (zweryfikowane na zywym BIP).
LISTING_URL = f"{BASE}/index.php?id=113&filters%5B2%5D%5B%5D=1094"
# Tylko obecna kadencja: karty radnych re-elektowanych niosa tez stare PDF-y (rok < 2024).
MIN_YEAR = 2024

# Karta jednego radnego (akordeon). DOTALL: cialo karty obejmuje wiele wierszy.
_CARD = re.compile(r'<div class="card card-toggle-expand">(.*?)</div>\s*</div>\s*</div>', re.S)
# Naglowek karty: anchor osoby -> 'Nazwisko Imie'.
_HEADER_NAME = re.compile(r'\?id=osoba&p1=\d+"[^>]*>([^<]+)</a>')
# Wiersz: ROK (col-sm-1), OPIS (col-sm-8), href PDF (col-sm-3). DOTALL miedzy kolumnami.
_ROW = re.compile(
    r'<div class="col-sm-1">\s*(\d{4})\s*</div>'
    r'\s*<div class="col-sm-8">([^<]*)'
    r'.*?href="(upload/pliki/[^"]+\.pdf)"',
    re.S | re.I,
)


def parse_name(header_html: str):
    """Naglowek karty -> 'Nazwisko Imie' (nazwisko-pierwsze, jak podaje zrodlo), albo None.

    Bierzemy tekst kotwicy osoby; encje HTML rozwijamy, scalamy biale znaki. Kolejnosc juz
    zgodna z kontraktem ('Nazwisko Imie') — nie odwracamy.
    """
    m = _HEADER_NAME.search(header_html)
    if not m:
        return None
    name = " ".join(html.unescape(m.group(1)).split())
    return name or None


def _is_snapshot(desc: str) -> bool:
    """Snapshot na poczatek kadencji (slubowanie) — odrzucamy, nawet jako 'korekta'."""
    return "początek kadencji" in desc.lower()


def _is_explanation(desc: str) -> bool:
    """'wyjasnienie do oswiadczenia ...' — to nie jest oswiadczenie roczne -> odrzucamy."""
    return "wyjaśnieni" in desc.lower()


def _is_korekta(desc: str) -> bool:
    """Korekta prawdziwego rocznika ('korekta ... za <rok>') — bije zwykly rocznik."""
    return "korekta" in desc.lower()


def parse_card(card_html: str):
    """HTML jednej karty -> [(name, year, pdf_url), ...] z dedupem per (name, year).

    Tylko wiersze rocznikow `year >= MIN_YEAR` (stare kadencje odpadaja). Snapshoty
    'poczatek kadencji' i 'wyjasnienia' odrzucone. Sposrod pozostalych per rok korekta
    bije zwykly rocznik; przy rownym priorytecie wygrywa pierwszy (strona listuje od
    najnowszych). pdf_url absolutny.
    """
    name = parse_name(card_html)
    if not name:
        return []
    # klucz (name, year) -> (priorytet, pdf_url); priorytet: korekta=1 > rocznik=0.
    best: dict[tuple[str, int], tuple[int, str]] = {}
    for year_s, desc, href in _ROW.findall(card_html):
        desc = html.unescape(desc)
        if _is_snapshot(desc) or _is_explanation(desc):
            continue
        year = int(year_s)
        if year < MIN_YEAR:
            continue
        rank = 1 if _is_korekta(desc) else 0
        key = (name, year)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, f"{BASE}/{href}")
    return [(n, y, url) for (n, y), (_rank, url) in best.items()]


def parse_listing(page_html: str):
    """Cala strona listingu -> [(name, year, pdf_url), ...] (dedup per (name, year)).

    Dzieli strone na karty radnych i scala wynik parse_card. Globalny dedup na wypadek,
    gdyby ten sam radny pojawil sie w dwoch kartach.
    """
    out, seen = [], set()
    for card in _CARD.findall(page_html):
        for name, year, url in parse_card(card):
            if (name, year) in seen:
                continue
            seen.add((name, year))
            out.append((name, year, url))
    return out


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per roczne oswiadczenie radnego.

    Jeden GET na strone listingu (bez paginacji). Pierwszy GET ustawia ciasteczko sesji —
    domyslny httpx.Client je obsluguje. Tylko GET (HEAD na tym BIP zwraca 500).
    """
    page = client.get(LISTING_URL).text
    yield from parse_listing(page)
