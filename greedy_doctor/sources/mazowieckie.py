"""Adapter zrodla: Sejmik Wojewodztwa Mazowieckiego (kadencja 2024-2029).

BIP Urzedu Marszalkowskiego (bip.mazovia.pl) stoi na CMS SmartSite by BIT (NIE Madkom —
/api/menu zwraca 404). Strony sa renderowane serwerowo (HTML scrape), ale kazda strona ma
tez widok ?format=json (uzywamy go do wyciagniecia URL-a PDF z leaf-strony oswiadczenia).

Organizacja (per OSOBA -> per OSWIADCZENIE): sekcja 'Oswiadczenia majatkowe' ma komponent
Bip_PageList z zakladkami ?p=<kategoria>. Zakladka '?p=Radni wojewodztwa' to akordeon ~53
radnych; etykieta linku to JUZ 'Nazwisko Imie' (polskie znaki). Link osoby ma postac
'?p=Radni województwa^<Nazwisko>@<Imie...>' (^ = %5E, @ = %40). Rozwiniecie osoby listuje
jej oswiadczenia: kazde <li> ma blok <div class="desc"> z polami:
  'Okres, za który zostało złożone:' -> ROK (np. 2024)
  'Numer kadencji:'                  -> 'VII kadencja (2024-2029)' / 'VI kadencja (2018-2024)'
  'Okoliczność złożenia:'            -> 'Oświadczenie roczne' / 'pierwsze' / 'ostatnie' / 'Korekta...'
Leaf-strona oswiadczenia ('oswiadczenie-majatkowe-<imie-nazwisko>-N.html') ma JEDEN zalacznik
PDF (komponent Attachment, content[0].src = /resource/<id>/<plik>.pdf).

PDF-y to SKANY (pdfplumber: 0 znakow na 6 stronach) -> extract robi OCR. Sejmik traktujemy
jak 'miasto' (pole city).

Pulapki obsluzone:
- ten sam ROK (np. 2024) wystepuje u radnego nawet 3x: jako roczne VII kadencji (BIERZEMY),
  'ostatnie' VI kadencji (na zakonczenie starej kadencji) oraz 'pierwsze' VII (na rozpoczecie).
  Dlatego filtrujemy na (Okolicznosc == 'Oswiadczenie roczne') AND (kadencja zawiera 'VII').
- akordeon ma wpisy-duplikaty z literowka/skrocona forma imienia (np. 'Benedykcińśki Grzegorz'
  obok 'Benedykciński Grzegorz Józef', 'Uzdowska-Gacek Anna' obok '...Anna Maria'). Wpisy-widma
  linkuja do starych/snapshotowych oswiadczen bez rocznego VII 2024/2025 -> filtr je odrzuca,
  wiec nie produkuja kolizji (name, rok).
- dedup per (name, rok): w obrebie jednej osoby rok roczny VII wystepuje raz.
ponytail: czyste parsowanie HTML->dane (testowalne na fixture). URL PDF bierzemy z ?format=json
leaf-strony (stabilniejsze niz regex po zakodowanej nazwie pliku). Sciaganie robi crawl.py.
"""

import html
import re
import time
from urllib.parse import urljoin

CITY = "Sejmik Mazowiecki"
BASE = "https://bip.mazovia.pl"
# Sekcja oswiadczen + zakladka biezacych radnych (kadencja VII). ?p= filtruje Bip_PageList.
RADNI_TAB = (
    BASE + "/pl/bip/oswiadczenia-majatkowe/?p=Radni+wojew%C3%B3dztwa"
)
MIN_YEAR, MAX_YEAR = 2024, 2025  # biezaca kadencja; pomijamy historie i lata spoza zakresu

# Wpis osoby w akordeonie: <a href="?p=Radni województwa^Nazwisko@Imie..." title="Nazwisko Imie">.
# %40 (@) odroznia wpis OSOBY od samej zakladki kategorii.
_PERSON = re.compile(
    r'<a href="(\?p=Radni\+wojew[^"]*%40[^"]*)"\s+title="([^"]+)"', re.I
)
# Link leaf-strony oswiadczenia + caly ogon <li> (z blokiem desc) az do </li>.
_DECL = re.compile(
    r'href="(/pl/bip/oswiadczenia-majatkowe/oswiadczenie-majatkowe-[a-z0-9-]+\.html)"(.*?)</li>',
    re.S | re.I,
)


def parse_name(title: str) -> str:
    """Etykieta akordeonu to juz 'Nazwisko Imie' — normalizujemy tylko biale znaki/encje."""
    return " ".join(html.unescape(title or "").split())


def parse_person_links(list_html: str):
    """HTML zakladki 'Radni wojewodztwa' -> [(name, person_query_href), ...] (unikalne).

    person_query_href to wzgledny '?p=Radni województwa^...@...'; rozwijamy go wzgledem
    sciezki sekcji oswiadczen. name = 'Nazwisko Imie' z atrybutu title.
    """
    out, seen = [], set()
    for href, title in _PERSON.findall(list_html):
        name = parse_name(title)
        key = (name, href)
        if not name or key in seen:
            continue
        seen.add(key)
        out.append((name, html.unescape(href)))
    return out


def _desc_field(li_body: str, label: str) -> str:
    """Wartosc pola z bloku <div class='desc'>: '<span>Label</span>&nbsp;WARTOSC'."""
    m = re.search(re.escape(label) + r"[^<]*</span>(?:&nbsp;|\s)*([^<]*)", li_body)
    return html.unescape(m.group(1)).strip() if m else ""


def is_current_annual(kadencja: str, okolicznosc: str) -> bool:
    """Roczne oswiadczenie biezacej (VII) kadencji.

    Bierzemy tylko 'Oswiadczenie roczne' z kadencji VII. Odrzucamy 'pierwsze'
    (na rozpoczecie), 'ostatnie' (na zakonczenie VI kadencji) i 'Korekta...',
    oraz wszystko z VI kadencji (ten sam rok 2024 bywa tagowany VI 'ostatnie').
    """
    return (
        okolicznosc.casefold() == "oświadczenie roczne".casefold()
        and "VII" in (kadencja or "")
    )


def parse_person_declarations(person_html: str):
    """HTML rozwinietej osoby -> [(decl_page_url, year), ...] dla rocznych VII 2024/2025.

    Rok z pola 'Okres, za który zostało złożone'. Dedup per rok (rocznych VII jest <=1/rok).
    """
    out, seen = [], set()
    for url, body in _DECL.findall(person_html):
        rok = _desc_field(body, "Okres, za który zostało złożone:")
        kad = _desc_field(body, "Numer kadencji:")
        okol = _desc_field(body, "Okoliczność złożenia:")
        if not rok.isdigit() or not is_current_annual(kad, okol):
            continue
        year = int(rok)
        if year < MIN_YEAR or year > MAX_YEAR or year in seen:
            continue
        seen.add(year)
        out.append((urljoin(BASE, url), year))
    return out


def parse_pdf_url(decl_json: dict):
    """JSON leaf-strony oswiadczenia -> pelny URL pierwszego zalacznika PDF, albo None."""
    for comp in decl_json.get("components", []):
        if comp.get("type") != "Attachment":
            continue
        content = comp.get("content")
        if isinstance(content, list) and content:
            src = content[0].get("src")
            if src:
                return urljoin(BASE, src)
    return None


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url, landing_url) per roczne oswiadczenie radnego (VII).

    Dla kazdej osoby: 1 GET rozwinietej zakladki -> filtr rocznych VII 2024/2025 ->
    po 1 GET (?format=json) na zachowane oswiadczenie po URL PDF. Dedup per (name, year).
    """
    persons = parse_person_links(client.get(RADNI_TAB).text)
    seen = set()
    for name, person_q in persons:
        time.sleep(0.3)
        person_url = urljoin(BASE + "/pl/bip/oswiadczenia-majatkowe/", person_q)
        decls = parse_person_declarations(client.get(person_url).text)
        for decl_url, year in decls:
            if (name, year) in seen:
                continue
            time.sleep(0.3)
            data = client.get(decl_url + "?format=json").json()
            pdf_url = parse_pdf_url(data)
            if not pdf_url:
                continue
            seen.add((name, year))
            yield name, year, pdf_url, person_url
