"""Adapter zrodla: Sejmik Wojewodztwa Lodzkiego (kadencja VII, 2024-2029).

BIP Wojewodztwa Lodzkiego (bip.lodzkie.pl) stoi na CMS Joomla z komponentem K2 — INNY
silnik niz wszystkie dotychczasowe zrodla (NIE Madkom, NIE SmartSite). Nawigacja K2:
  - listing kategorii: '/itemlist/category/18-oswiadczenie-majatkowe' (kategoria K2 = 18),
    paginowany przez '?start=N' (10 pozycji na strone, 'Strona 1 z 11'); start=0,10,20,...
  - strona osoby: '/item/{id}-{slug}-oswiadczenia-majatkowe' — JEDNA na radnego, listuje
    wszystkie jego PDF-y (roczne + snapshoty + korekty), kazdy jako <a href="/files/...pdf">
    z ETYKIETA opisujaca typ/rok ('Oswiadczenie majatkowe za 2024 r.').

Organizacja: listing -> strona osoby -> N x link PDF. Yieldujemy jedno ROCZNE oswiadczenie
per (name, year).

PULAPKI (zweryfikowane na zywym BIP):

1. STARE POZYCJE WMIESZANE W KATEGORIE. Radni biezacej kadencji maja wysokie, ciagle id
   15111-15143 (33 osoby, alfabetycznie Adamczyk->Zyberyng; listing sortuje malejaco po
   dacie, wiec leca od 15143). Dalsze strony kategorii wyciagaja STARE pozycje o niskich id
   (432-451, 9471, 10549, 14305...) z poprzednich kadencji. Filtrujemy po id >= MIN_ITEM_ID.

2. NAZWA Z TEKSTU LINKU, NIE ZE SLUGA. Tekst kotwicy na listingu to 'Nazwisko Imie -
   Oswiadczenia majatkowe' (polskie znaki, wlasciwa wielkosc liter) — to jest zrodlo nazwy.
   SLUG W URL-u BYWA BLEDNY: item 15114 ma slug 'ciesielski-tomasz', a faktyczny radny to
   'Ciesielski Janusz' (literowka CMS). Dlatego NIE parsujemy nazwy ze sluga ani z nazwy
   pliku. Format jest juz 'Nazwisko Imie' (zgodny z kontraktem) — nie odwracamy.

3. ROK I TYP Z ETYKIETY LINKU, NIE Z NAZWY PLIKU. Nazwy plikow sa skrajnie niespojne
   ('/files/adamczyk.pdf', '/files/ADAMCZYK_P.pdf', '/files/zybering.pdf' (literowka!),
   '/files/radni_roczne_2025/<slug>---radny.pdf'). Typ/rok siedzi w TEKSCIE kotwicy:
     'Oswiadczenie majatkowe za 2024 r.'        -> ROCZNE 2024 (bierzemy)
     'Oswiadczenie majatkowe za 2025 r.'        -> ROCZNE 2025 (bierzemy)
     'Oswiadczenie majatkowe na rozpoczecie kadencji' -> snapshot (pomijamy — brak 'za YYYY')
     'Korekta oswiadczenia majatkowego za 2024 r.'    -> KOREKTA rocznego 2024 (preferujemy)
     'Korekta oswiadczenia majatkowego'               -> korekta bez roku (pomijamy — nie da
                                                         sie przypisac do rocznika)
     'Korekta ... na rozpoczecie kadencji'            -> korekta snapshotu (pomijamy)
     'Korekta oswiadczenia majatkowego za 2024r. i 2025r.' -> korekta DWoCH lat (oba lata)
   Rok parsujemy regexem 'za YYYY r.' (odstep po roku opcjonalny: '2024r.'); jedna etykieta
   moze niesc wiele lat ('2024r. i 2025r.').

4. KOREKTA WYGRYWA. Pod jedna osoba ten sam rok bywa i jako zwykle roczne, i jako korekta
   (item 15114: 'za 2024 r.' ORAZ 'Korekta ... za 2024 r.'). Emitujemy JEDEN PDF per
   (name, year), preferujac korekte (nowsza, poprawiona wersja).

PDF-y to SKANY -> extract robi fallback OCR (tesseract -l pol). Sejmik traktujemy jak
'miasto' (pole city). Parsowanie czyste (HTML -> dane), bez sieci; sciaganie robi crawl.py.

ponytail: kategoria K2 zahardcodowana (18) — nowa kadencja => nowa kategoria => nowe id.
MIN_ITEM_ID (15000) odsiewa stare pozycje prosciej niz dedup-po-najwyzszym-id; biezace id
zaczynaja sie od 15111, prog 15000 daje zapas. Paginacje konczymy, gdy strona nie wnosi
nowych id radnych (>=MIN_ITEM_ID) — strony 5+ to same stare pozycje. ponytail: re+html ze
stdlib (strona statyczna, silnik przegladarki to narzut).
"""

import html
import re
import time
from urllib.parse import urljoin

CITY = "Sejmik Łódzki"
BASE = "https://bip.lodzkie.pl"
# Kategoria K2 z oswiadczeniami radnych VII kadencji. ponytail: nowa kadencja -> nowe id kategorii.
CATEGORY_ID = 18
LISTING_PATH = (
    "/wojewodztwo-lodzkie/oswiadczenia-majatkowe/radni/radni-sejmiku-vii-kadencji"
    "/itemlist/category/18-o%C5%9Bwiadczenie-maj%C4%85tkowe"
)
LISTING_URL = BASE + LISTING_PATH
# Biezaca kadencja ma ciagle id 15111-15143; prog 15000 odsiewa stare pozycje (432-451,
# 9471, 10549, 14305...) wmieszane w te sama kategorie. ponytail: prog zamiast dedup-po-id.
MIN_ITEM_ID = 15000
PER_PAGE = 10  # K2: 10 pozycji na strone (paginacja ?start=N)
MAX_PAGES = 20  # bezpiecznik: realnie 11 stron; i tak konczymy, gdy brak nowych id

# Tytulowa kotwica pozycji na listingu: /item/{id}-{slug}-oswiadczenia-majatkowe.
# Tekst kotwicy to 'Nazwisko Imie - Oswiadczenia majatkowe' (zrodlo nazwy; slug bywa bledny).
_ITEM_LINK = re.compile(
    r'<a[^>]*href="([^"]*/item/(\d+)-[^"]*)"[^>]*>(.*?)</a>', re.S | re.I
)
# Link PDF na stronie osoby: <a href="/files/...pdf">ETYKIETA</a>. Etykieta niesie rok/typ.
_PDF_LINK = re.compile(r'<a[^>]*href="(/files/[^"]+\.pdf)"[^>]*>(.*?)</a>', re.S | re.I)
# Rok rocznego oswiadczenia z etykiety. Wymagamy postaci 'YYYY r' (rok + znacznik 'r.'/'r '),
# bo to odroznia rok rocznika od innych liczb. 'za' rzadzi calym ciagiem, wiec w 'za 2024r.
# i 2025r.' drugiego roku NIE poprzedza 'za' — dlatego nie zadamy 'za' tuz przed kazdym rokiem.
# Odstep przed 'r' opcjonalny ('2024r.' i '2024 r.'). label_years i tak odpala tylko, gdy w
# etykiecie pada 'za' (snapshot 'na rozpoczecie' nie ma 'za YYYY r' i wypada).
_YEAR = re.compile(r"\b(20\d\d)\s*r\b", re.I)
# Sufiks tekstu kotwicy listingu do odciecia z nazwy.
_NAME_SUFFIX = re.compile(r"\s*-\s*o[śs]wiadczeni.*$", re.I)


def _text(inner_html: str) -> str:
    """Wnetrze kotwicy -> czysty tekst: usuwa zagniezdzone tagi, encje i biale znaki."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", inner_html)).split())


def parse_listing(page_html: str):
    """HTML strony listingu -> [(item_id:int, name:str, item_url:str), ...].

    Bierze tylko pozycje biezacej kadencji (id >= MIN_ITEM_ID) — odsiewa stare pozycje
    wmieszane w kategorie. name z TEKSTU kotwicy ('Nazwisko Imie - Oswiadczenia majatkowe'
    -> 'Nazwisko Imie'), NIE ze sluga (slug bywa bledny). Dedup per id (kazda pozycja ma
    dwie kotwice: tytul + 'czytaj wiecej'). item_url absolutny.
    """
    out, seen = [], set()
    for href, sid, inner in _ITEM_LINK.findall(page_html):
        item_id = int(sid)
        if item_id < MIN_ITEM_ID or item_id in seen:
            continue
        name = _NAME_SUFFIX.sub("", _text(inner)).strip()
        if not name:
            continue  # 'czytaj wiecej' (sama ikona, brak nazwy) — pomijamy
        seen.add(item_id)
        out.append((item_id, name, urljoin(LISTING_URL, href)))
    return out


def label_years(label: str):
    """Etykieta linku PDF -> (set lat rocznego oswiadczenia, czy_korekta).

    Roczne id z 'za YYYY r.' (moze byc wiele lat w jednej etykiecie: 'za 2024r. i 2025r.').
    Snapshot 'na rozpoczecie kadencji' nie ma 'za YYYY' -> pusty zbior -> pominiety.
    Korekte rozpoznajemy po slowie 'korekt' (preferujemy ja dla danego (name, year)).
    Korekta bez roku ('Korekta oswiadczenia majatkowego') -> pusty zbior -> pominieta.
    """
    txt = (label or "").lower()
    is_korekta = "korekt" in txt
    # Tylko etykiety 'za ...' niosa rocznik; bez 'za' (snapshot / korekta bez roku) -> pusto.
    years = {int(y) for y in _YEAR.findall(txt)} if "za " in txt else set()
    return years, is_korekta


def parse_item(page_html: str):
    """HTML strony osoby -> {year: pdf_url} dla rocznych oswiadczen, korekta wygrywa.

    Iteruje po linkach /files/*.pdf, mapuje rok->URL z etykiety. Gdy dla danego roku jest
    i zwykle roczne, i korekta -> zostaje korekta. pdf_url absolutny (href verbatim).
    """
    annual: dict[int, str] = {}
    korekta: dict[int, str] = {}
    for href, inner in _PDF_LINK.findall(page_html):
        years, is_korekta = label_years(_text(inner))
        if not years:
            continue
        url = urljoin(BASE, href)
        for y in years:
            (korekta if is_korekta else annual)[y] = url
    # korekta nadpisuje zwykle roczne dla tego samego roku
    return {**annual, **korekta}


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url, landing_url) per roczne oswiadczenie.

    1) Chodzi po stronach listingu (?start=N), zbiera pozycje biezacej kadencji (id>=15000);
       konczy, gdy strona nie wnosi nowych id (strony 5+ to same stare pozycje).
    2) Dla kazdej osoby 1 GET strony -> roczne PDF-y (korekta wygrywa). Dedup per (name, year).
    """
    items = {}  # id -> (name, item_url); dedup pozycji miedzy stronami
    for page in range(MAX_PAGES):
        start = page * PER_PAGE
        url = LISTING_URL if start == 0 else f"{LISTING_URL}?start={start}"
        rows = parse_listing(client.get(url).text)
        fresh = {iid: (name, iurl) for iid, name, iurl in rows if iid not in items}
        if not fresh:
            break  # ta strona nie wniosla nowych radnych -> koniec biezacej kadencji
        items.update(fresh)
        time.sleep(0.3)

    seen = set()
    for _iid, (name, item_url) in sorted(items.items()):
        time.sleep(0.3)
        for year, pdf_url in sorted(parse_item(client.get(item_url).text).items()):
            if (name, year) in seen:
                continue
            seen.add((name, year))
            yield name, year, pdf_url, item_url
