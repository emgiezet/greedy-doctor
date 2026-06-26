"""Adapter zrodla: Sejmik Wojewodztwa Podlaskiego. BIP na tym samym CMS co Slaski
(SmartSite / BIT Sp. z o.o.) — NIE Madkom (brak /api/), wiec HTML scrape. Niemal kopia
sources/slaskie.py; rozni sie tylko logika filtra typu i mapowaniem roku (patrz nizej).

Organizacja per OSOBA -> per ROK -> per DOKUMENT (3 poziomy bezstanowych deep-linkow 'p='):
  1. Listing (paginowany ?page=1..7): kazda osoba to <a href="?p=Nazwisko@Imie"
     title="Nazwisko Imie"> w bloku menu. Tytul JEST obecny i jest juz 'Nazwisko Imie'
     (kolejnosc jak w kontrakcie / jak Slaski) — nie odwracamy. Separator '@' (= %40).
     UWAGA: listing kumuluje WSZYSTKICH skladajacych od 2009 (zarzad, dyrektorzy ZOZ,
     poprzednie kadencje) — 165 osob. Do radnych sejmiku filtrujemy po TYTULE dokumentu,
     nie po listingu (patrz annual_year()).
  2. Strona osoby (?p=Nazwisko@Imie): linki roczne ?p=Nazwisko@Imie^YYYY (tekst kotwicy
     = sam rok; '^' = %5E). Bierzemy lata >= MIN_YEAR.
  3. Strona roku (?p=...^YYYY): kazdy dokument to <a href=".../oswiadczenie-majatkowe-<slug>.html">
     a TUZ ZA nim <div class="desc"> z 'Okolicznosci zlozenia: <typ>'. Typ niesie i rodzaj
     oswiadczenia, i rok fiskalny ('... za YYYY rok'). Parujemy link z jego okolicznosciami.
  4. Podstrona dokumentu: bezposredni link PDF /resource/<id>/<size>/<nazwa>.pdf.

ROZNICE WZGLEDEM SLASKIEGO (istotne):
  * Rok w wezle ^YYYY to rok ZLOZENIA, nie fiskalny: oswiadczenie za 2024 r. lezy pod
    wezlem ^2025 (zlozone w 2025), zatytulowane '... za 2024 rok'. Wezel ^2024 trzyma
    resztki VI kadencji + snapshot poczatku VII kadencji. Dlatego rok fiskalny bierzemy
    z TYTULU ('za YYYY rok'), nie z numeru wezla.
  * Filtr roczne-vs-snapshot dziala na TYTULE z okolicznosci (nie na nazwie pliku — pliki
    maja generyczna nazwe 'Oswiadczenie majatkowe radnego wojewodztwa - Imie Nazwisko.pdf').
    Roczne: 'Oswiadczenie majatkowe <funkcja/radnego> za YYYY rok'. Pomijamy snapshoty
    ('po objeciu mandatu', 'na 2 miesiace przed uplywem kadencji', 'wygasniecie mandatu',
    'w zw. z zakonczeniem pelnienia funkcji') — nie maja 'za YYYY rok', wiec odpadaja same.
  * Filtr radnych sejmiku jest UBOCZNYM efektem 'za YYYY rok': dyrektorzy ZOZ i inni
    urzednicy skladaja jako generyczne 'oswiadczenie majatkowe roczne' (bez 'za YYYY rok'),
    radni sejmiku jako 'Oswiadczenie majatkowe radnego/radnej/Przewodniczacego... za YYYY
    rok'. Zweryfikowane na zywym BIP: 'za 2024 rok' w wezlach ^2025 trafia w DOKLADNIE 30
    osob = liczba radnych VII kadencji (2024-2029).
  * Korekta 'za 2024 rok- korekta' ZAWIERA 'za YYYY rok' -> jak w Slaskim odrzucamy po
    podlancuchu 'korekt' (filtr negatywny jest tu konieczny).

UWAGA — nazwa pliku w href PDF jest PODWOJNIE url-encoded (np. '%25C5%259B' = '%C5%9B' =
's' z kreska). httpx/curl wysylaja sciezke doslownie i serwer zwraca PDF (HTTP 200) — wiec
pdf_url to href verbatim, bez dekodowania.

PDF-y to SKANY -> extract robi fallback OCR (tesseract -l pol). MIN_YEAR=2024: roczniki
2025+ (za 2025, pod wezlem ^2026) wejda automatycznie, gdy sie pojawia — bez zmian w kodzie.
Dedup per (nazwisko, rok). Parsowanie czyste (HTML -> dane), bez sieci; sciaganie robi crawl.py.
ponytail: httpx + html.unescape + re (strona statyczna, silnik przegladarki to narzut).
"""

import html
import re
import time
from urllib.parse import urljoin

CITY = "Sejmik Województwa Podlaskiego"
BASE = "https://bip.podlaskie.eu"
# ponytail: wezel listingu 'oswi_maja_zloz_od_2009' (id 9009) — sciezka stabilna, nie ID.
LISTING_URL = BASE + "/wojewodztwo/oswiadczenia/oswiadczenia_majatkowe_od_2009/"
MIN_YEAR = 2024  # biezaca (VII) kadencja 2024-2029; archiwum 2009-2023 odsiewamy

# Listing: osoba = <a href="?p=Nazwisko@Imie" title="Nazwisko Imie"> (bez '^' = bez roku).
# title= bywa w nastepnej linii niz href, wiec \s+ (obejmuje newline). Wymagamy %40 (@).
_RADNY = re.compile(r'<a href="(\?p=[^"]*%40[^"]*?)"\s+title="([^"]+)"', re.I)
# Strona osoby: link roczny ?p=...%5EYYYY (tekst kotwicy = rok).
_YEAR_LINK = re.compile(r'href="(\?p=[^"]*%5E(20\d\d))"', re.I)
# Strona roku: link dokumentu (slug 'oswiadczenie-majatkowe-...') SPAROWANY z jego
# 'Okolicznosci zlozenia: <typ>'. re.S, bo desc jest kilka linii za <a>; .*? trzyma
# parowanie najblizsze (nielapczywe). Wykluczamy szum menu (klauzula-informacyjna,
# formul_oswiad_do_pobran) przez wymog slugu 'oswiadczenie-majatkowe-'.
_DOC = re.compile(
    r'href="(/wojewodztwo/oswiadczenia/oswiadczenia_majatkowe_od_2009/'
    r'oswiadczenie-majatkowe-[^"?]+\.html)".*?'
    r"Okoliczno[^<]*</span>([^<]*)",
    re.I | re.S,
)
# Podstrona dokumentu: bezposredni link PDF z biblioteki /resource/<id>/<size>/<nazwa>.pdf.
_PDF_LINK = re.compile(r'href="(/resource/\d+/\d+/[^"]+\.pdf)"', re.I)
# Rok fiskalny w tytule okolicznosci: '... za YYYY rok'.
_ZA_ROK = re.compile(r"za\s+(20\d\d)\s+rok", re.I)


def parse_listing(page_html):
    """HTML strony listingu -> [('Nazwisko Imie', url_osoby), ...] (unikalne, posortowane).

    Tytul w atrybucie title= jest juz 'Nazwisko Imie' — normalizujemy tylko biale znaki
    i encje HTML. url_osoby to absolutny deep-link ?p=Nazwisko@Imie (bezstanowy).
    Nie filtrujemy tu radnych sejmiku — to robi annual_year() po tytule dokumentu.
    """
    src = html.unescape(page_html)
    out = {}
    for href, title in _RADNY.findall(src):
        if "%5E" in href:  # to juz link roczny, nie wpis osoby
            continue
        name = " ".join(html.unescape(title).split())
        if name:
            out[urljoin(LISTING_URL, href)] = name
    return sorted((name, url) for url, name in out.items())


def parse_year_links(page_html):
    """HTML strony osoby -> [(rok, url_roku), ...] dla lat >= MIN_YEAR (unikalne, rosnaco).

    rok to numer WEZLA (rok zlozenia); rok fiskalny i tak bierzemy pozniej z tytulu.
    Bierzemy >= MIN_YEAR, bo za 2024 r. lezy pod ^2025 — gdyby ciac na ^2024, ucielibysmy
    biezacy rocznik. Lata < MIN_YEAR (archiwum) pomijamy.
    """
    src = html.unescape(page_html)
    out = {}
    for href, year in _YEAR_LINK.findall(src):
        y = int(year)
        if y >= MIN_YEAR:
            out[y] = urljoin(LISTING_URL, href)
    return sorted(out.items())


def parse_docs(page_html):
    """HTML strony roku -> [(url_dokumentu, okolicznosci), ...] (unikalne, posortowane).

    Paruje kazdy link dokumentu z jego 'Okolicznosci zlozenia' (tytul niosacy typ i rok
    fiskalny). Bialy szum normalizujemy. Filtr typu/roku jest osobno w annual_year().
    """
    src = html.unescape(page_html)
    out = {}
    for href, okol in _DOC.findall(src):
        out[urljoin(BASE, href)] = " ".join(html.unescape(okol).split())
    return sorted(out.items())


def annual_year(okolicznosci):
    """Okolicznosci dokumentu -> rok fiskalny ROCZNEGO oswiadczenia, albo None.

    Roczne radnego sejmiku: tytul zawiera 'za YYYY rok' (radnego/radnej wojewodztwa,
    Przewodniczacego/Marszalka/Wicemarszalka Sejmiku...). Zwracamy YYYY z tytulu (rok
    FISKALNY, nie numer wezla). Odrzucamy korekty (zawieraja 'za YYYY rok', ale tez
    'korekt'). Snapshoty i generyczne 'oswiadczenie majatkowe roczne' (dyrektorzy ZOZ itp.)
    nie maja 'za YYYY rok' -> None, czyli wypadaja same (filtr radnych jako efekt uboczny).
    """
    txt = okolicznosci.lower()
    if "korekt" in txt:
        return None
    m = _ZA_ROK.search(txt)
    return int(m.group(1)) if m else None


def parse_pdf_url(page_html):
    """HTML podstrony dokumentu -> pelny URL PDF (href verbatim — podwojne kodowanie zostaje)."""
    src = html.unescape(page_html)
    m = _PDF_LINK.search(src)
    return urljoin(BASE, m.group(1)) if m else None


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url, landing_url) per roczne oswiadczenie radnego.

    Chodzimy: listing (paginowany) -> osoba -> rok(>=MIN_YEAR) -> dokument(+okolicznosci) -> PDF.
    Rok WYNIKOWY to rok FISKALNY z tytulu ('za YYYY rok'), nie numer wezla. Bierzemy tylko
    dokumenty, dla ktorych annual_year() zwraca rok >= MIN_YEAR (roczne radnych sejmiku,
    bez korekt/snapshotow/urzednikow). Dedup per (nazwisko, rok_fiskalny).
    """
    # 1) zbierz wszystkie osoby ze wszystkich stron listingu (paginacja ?page=N)
    radni = {}
    page = 1
    while True:
        url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
        rows = parse_listing(client.get(url).text)
        new = {url_: name for name, url_ in rows if url_ not in radni}
        if not new:
            break  # ta strona nie wniosla nowych osob -> koniec paginacji
        radni.update(new)
        page += 1
        time.sleep(0.2)

    # 2) dla kazdej osoby: lata >= MIN_YEAR -> dokumenty -> roczne PDF-y radnych sejmiku
    for radny_url, name in sorted(radni.items(), key=lambda kv: kv[1]):
        seen = set()  # rok_fiskalny -> raz na (osoba, rok)
        time.sleep(0.2)
        for _node_year, year_url in parse_year_links(client.get(radny_url).text):
            time.sleep(0.2)
            for doc_url, okol in parse_docs(client.get(year_url).text):
                fiscal = annual_year(okol)
                if fiscal is None or fiscal < MIN_YEAR or fiscal in seen:
                    continue
                time.sleep(0.2)
                pdf_url = parse_pdf_url(client.get(doc_url).text)
                if pdf_url:
                    seen.add(fiscal)
                    yield name, fiscal, pdf_url, radny_url
