"""Adapter zrodla: Rada Miasta Gdanska. BIP na CMS eUrzad (NIE Madkom — /api/ zwraca HTML/500).

Organizacja per ROK -> per RADNY: strona roczna 'Radni Miasta Gdanska' (osobna per rok)
listuje ~kilkudziesieciu radnych (link 'prawo-lokalne/<Slug>,a,<id>', nazwisko w <span>
juz jako 'Nazwisko Imie'). Na podstronie radnego sa zalaczniki PDF z klasa 'article-file'
i etykieta w <span class="title">: 'Oswiadczenie' (roczne), 'Oswiadczenie 2/3/4'
(snapshoty: na rozpoczecie/koniec kadencji — w 2024 rok wyboru wpada ich kilka),
'Korekta' (korekty). PDF-y to SKANY (pelnostronicowy JPEG ~300 DPI, pdfplumber -> 0 znakow)
-> extract robi OCR (tesseract -l pol). Rade traktujemy jak 'miasto' (pole city).

Parsowanie czyste (HTML -> dane), bez sieci — testowalne na fixture. Sciaganie robi crawl.py.
ponytail: httpx + html.unescape (strona statyczna, encje jak w Kielcach/Poznaniu);
ID stron rocznych zahardcodowane (zweryfikowane) — nowy rok = nowy ID.

Pulapki obsluzone:
- listing zawiera tez menu boczne i kafle kategorii (Prezydent/Sekretarz/...) o tej samej
  strukturze <a><span> -> zawezamy do bloku <div class="list"> (tresc artykulu).
- stopka ma PDF deklaracji dostepnosci (class="h-100") -> bierzemy tylko class="article-file".
- jeden radny ma wiele PDF: bierzemy DOKLADNIE 'Oswiadczenie' (kanoniczne roczne),
  pomijajac numerowane snapshoty i wszystkie 'Korekta' -> dokladnie jeden plik per (radny, rok).
"""

import html
import re

CITY = "Gdańsk"
BASE = "https://bip.gdansk.pl"
# Strony roczne 'Radni Miasta Gdanska' (kadencja 2024-2029). Kazdy rok = osobny artykul.
YEAR_LISTINGS = {
    2024: BASE + "/prawo-lokalne/Radni-Miasta-Gdanska,a,256607",
    2025: BASE + "/prawo-lokalne/Radni-Miasta-Gdanska,a,278126",
}

# Blok tresci artykulu z lista radnych (odsiewa menu boczne i kafle kategorii o tej samej strukturze).
_LIST_BLOCK = re.compile(r'<div class="list">(.*?)<div class="bar-title">', re.S | re.I)
# Link do podstrony radnego wewnatrz bloku: <a href=...,a,id target="_parent"><span>Nazwisko Imie</span>.
_RADNY = re.compile(
    r'<a href="(https://bip\.gdansk\.pl/prawo-lokalne/[^"]+,a,\d+)" target="_parent">\s*'
    r"<span>([^<]+)</span>",
    re.I,
)
# Zalacznik PDF artykulu: class="article-file" + etykieta dokumentu (Oswiadczenie / Korekta / ...).
# class="article-file" odsiewa stopkowy PDF dostepnosci (ten ma class="h-100").
_ARTICLE_FILE = re.compile(
    r'<a class="article-file" href="(https://download\.cloudgdansk\.pl/[^"]+\.pdf)"[^>]*>\s*'
    r'<span class="title">([^<]*)</span>',
    re.I | re.S,
)


def parse_listing(page_html):
    """HTML strony rocznej -> [('Nazwisko Imie', url_radnego), ...] (unikalne, posortowane).

    Nazwisko bierzemy ze <span> linku — BIP podaje je juz jako 'Nazwisko Imie [Imie2]'.
    """
    src = html.unescape(page_html)
    m = _LIST_BLOCK.search(src)
    block = m.group(1) if m else ""
    out = {}
    for url, name in _RADNY.findall(block):
        out[url] = " ".join(name.split())
    return sorted((name, url) for url, name in out.items())


def pick_declaration(page_html):
    """HTML podstrony radnego -> URL rocznego 'Oswiadczenie', albo None.

    Bierzemy plik o etykiecie dokladnie 'Oswiadczenie' (kanoniczne roczne). Pomijamy
    numerowane 'Oswiadczenie 2/3/4' (snapshoty na rozpoczecie/koniec kadencji — kumuluja
    sie w roku wyboru) oraz wszystkie 'Korekta'. Daje dokladnie jeden plik per (radny, rok).
    """
    src = html.unescape(page_html)
    for href, title in _ARTICLE_FILE.findall(src):
        if title.strip().casefold() == "oświadczenie":
            return href
    return None


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per roczne oswiadczenie radnego."""
    import time

    for year, listing_url in YEAR_LISTINGS.items():
        for name, radny_url in parse_listing(client.get(listing_url).text):
            time.sleep(0.3)
            pdf_url = pick_declaration(client.get(radny_url).text)
            if pdf_url:
                yield name, year, pdf_url
