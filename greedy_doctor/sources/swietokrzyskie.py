"""Adapter zrodla: Sejmik Wojewodztwa Swietokrzyskiego (kadencja VII, 2024-2029).

BIP Urzedu Marszalkowskiego (bip.sejmik.kielce.pl — UWAGA: INNY BIP niz miejskie zrodlo
'kielce') to Joomla (com_content) + komponent Phoca Download. Brak API JSON; oswiadczenia
radnych leza w artykule ROCZNYM, jeden artykul na rok pod kategoria VII kadencji (id 1305):
  2024 -> /1305-.../14712-...-zlozone-za-2024-rok.html
  2025 -> /1305-.../16008-...-zlozone-za-2025-rok.html
Snapshot 'slubowanie / poczatek kadencji' ma WLASNY artykul (id 13490) i tu nie wchodzi
(pomijamy go przez sam dobor id w YEAR_ARTICLES).

W artykule rocznym kazdy radny to wiersz tabeli Phoca:
  <a href="/download/{fileId}-{slug}/1305-.../{art}-...zlozone-za-{rok}-rok.html">
    <span class="tabela2_tytul1">Imie Nazwisko</span> ...
Phoca serwuje PDF spod tego .html, wiec pdf_url to wlasnie ten absolutny URL .html.

Pulapki obsluzone:
- KOLEJNOSC ODWROTNA: widoczny tytul to 'Imie Nazwisko' (imie pierwsze) -> odwracamy do
  'Nazwisko Imie' (kontrakt, jak reszta zrodel). surname_first: pierwszy token = imie,
  reszta = nazwisko (zachowuje dwuczlonowe nazwiska).
- KOREKTY: w tym samym artykule rocznym wisi tez korekta ('... Korekta' w tytule lub
  '-korekta' w slugu; warianty 'socha_korekta', 'cepil - korekta') -> odrzucamy po slowie
  'korekt' w tytule LUB w slugu. Realny rocznik tej osoby zostaje (korekta to osobny wiersz).
- rok bierzemy z klucza YEAR_ARTICLES (w URL nie ma roku poza slugiem artykulu).

PDF-y maja warstwe tekstowa (pdfplumber dziala; OCR zwykle zbedny) — i tak decyduje extract.py.
Parsowanie czyste (HTML -> dane), bez sieci; sciaganie robi crawl.py. ponytail: id artykulow
rocznych (14712, 16008) i kategorii (1305) zahardcodowane (zweryfikowane na zywym BIP); nowy
rocznik -> dodac (rok, id) do YEAR_ARTICLES (snapshot 13490 swiadomie pominiety).
"""

import html
import re
import time

CITY = "Sejmik Województwa Świętokrzyskiego"
BASE = "https://bip.sejmik.kielce.pl"
# Artykul roczny per ROK (kategoria VII kadencji 1305). Snapshot slubowania (13490) tu nie wchodzi.
YEAR_ARTICLES = {2024: 14712, 2025: 16008}

# Link Phoca Download do oswiadczenia + widoczny tytul (Imie Nazwisko) w <span tabela2_tytul1>.
_LINK = re.compile(
    r'<a href="(/download/[^"]+\.html)"[^>]*>\s*'
    r'<span class="tabela2_tytul1">([^<]+)</span>',
    re.I,
)


def surname_first(title: str) -> str:
    """'Imie Nazwisko' (imie pierwsze) -> 'Nazwisko Imie'. Pierwszy token = imie, reszta = nazwisko."""
    parts = html.unescape(title).split()
    if len(parts) < 2:
        return " ".join(parts)
    given, *surname = parts
    return " ".join([*surname, given])


def parse_link(href: str, title: str):
    """(href, widoczny tytul) -> (name 'Nazwisko Imie', pdf_url) dla rocznego, albo None.

    Odrzuca korekty: slowo 'korekt' w tytule ('Korekta'/'_korekta'/' - korekta') LUB slug
    '-korekta' w href. pdf_url absolutny (.html — Phoca serwuje stamtad PDF).
    """
    if "korekt" in title.lower() or "korekta" in href.lower():
        return None
    name = surname_first(title)
    return (name, BASE + href) if name else None


def parse_article(page_html: str, year: int):
    """HTML artykulu rocznego -> [(name, year, pdf_url), ...] (korekty odsiane, dedup per name)."""
    out, seen = [], set()
    for href, title in _LINK.findall(page_html):
        parsed = parse_link(href, title)
        if not parsed:
            continue
        name, url = parsed
        if name in seen:
            continue
        seen.add(name)
        out.append((name, year, url))
    return out


def _article_url(year: int, art_id: int) -> str:
    """Kanoniczny URL artykulu rocznego (zawiera id artykulu, jak w linkach Phoca na BIP)."""
    return (
        f"{BASE}/1305-vii-kadencja-lata-2024-2029/"
        f"{art_id}-oswiadczenia-majatkowe-radnych-wojewodztwa-swietokrzyskiego-zlozone-za-{year}-rok.html"
    )


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per roczne oswiadczenie radnego.

    Jeden GET na artykul roczny (per rok z YEAR_ARTICLES). Dedup per (name, year).
    """
    seen = set()
    for year, art_id in YEAR_ARTICLES.items():
        time.sleep(0.3)
        try:
            page = client.get(_article_url(year, art_id)).text
        except Exception:  # noqa: BLE001 — rocznik moze nie byc jeszcze opublikowany -> pomijamy
            continue
        for name, yr, pdf_url in parse_article(page, year):
            if (name, yr) in seen:
                continue
            seen.add((name, yr))
            yield name, yr, pdf_url
