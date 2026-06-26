"""Adapter zrodla: Sejmik Województwa Zachodniopomorskiego (kadencja VII, 2024-2029).

BIP Urzedu Marszalkowskiego (bip.wzp.pl) stoi na Drupal 7. Oswiadczenia roczne
radnych leza w tabelach pogrupowanych per rok i kategoria:
  2024 -> /tabela/artykuly/748/2301  (node tabeli = 2301)
  2025 -> /tabela/artykuly/748/2406  (node tabeli = 2406)
Nowy rocznik -> dodac (rok, node) do YEAR_NODES.

Kazda komorka tabeli to link /artykul/{slug} ze strona osoby. Na stronie osoby
siedzi jeden (lub rzadko dwa) link PDF w div.field-name-field-plik. Wyciagamy
PIERWSZY link PDF; jesli jest drugi z "korekta" w tytule, preferujemy go.

Pulapki:
- KOREKTY NA LISTINGU: dla tej samej osoby moga istniec dwa wpisy — zwykly i z
  sufiksem ' korekta' w nazwie (np. 'Geblewicz Olgierd' i 'Geblewicz Olgierd
  korekta'). Wybieramy artykul korekty i pomijamy zwykly.
- NAZWISKA DWUCZLONOWE ze spacjami: 'Holub - Kowalik Malgorzata' (2024) vs
  'Holub-Kowalik Malgorzata' (2025) — sciagamy spacje wokol '-' dla spojnosci.
- TRAILING WHITESPACE w nazwie na listingu (np. 'Niedzielski Andrzej ') — strip().
"""

import re
import time

CITY = "Sejmik Województwa Zachodniopomorskiego"
BASE = "https://www.bip.wzp.pl"
# Tabela oswiadczen radnych per ROK. Nowy rocznik -> dodac (rok, node).
YEAR_NODES = {2024: 2301, 2025: 2406}

# Link artykulu osoby w komorce tabeli Drupal views.
_ENTRY = re.compile(
    r'<h3><a href="(/artykul/([^"]+))">([^<]+)</a></h3>',
    re.I,
)
# Link PDF w div field-name-field-plik; bierzemy href absolutny.
_PDF = re.compile(
    r'href="(https://www\.bip\.wzp\.pl/sites/bip\.wzp\.pl/files/articles/[^"]+\.pdf)"',
    re.I,
)


def _normalize_name(raw):
    """Surowa nazwa z listingu -> 'Nazwisko Imie', spacje wokol '-' sciagniete.

    Zrodlo podaje juz 'Nazwisko Imie'. Usuwamy: sufiks ' korekta', spacje wokol
    myslnika (niespojnosc miedzy latami), nadmiarowe biale znaki.
    """
    name = raw.strip()
    # Odciecie sufiksu ' korekta' (case-insensitive; przed normalizacja '-')
    name = re.sub(r"\s+korekta\s*$", "", name, flags=re.I).strip()
    # 'Holub - Kowalik' -> 'Holub-Kowalik' (spacje wokol myslnika)
    name = re.sub(r"\s*-\s*", "-", name)
    return " ".join(name.split()) or None


def parse_listing(page_html):
    """HTML tabeli listingu -> [(name, article_url, is_korekta), ...].

    name to znormalizowana 'Nazwisko Imie' (bez sufiksu korekta, myslnik bez spacji).
    is_korekta=True gdy raw nazwa zawierala ' korekta'. article_url absolutny.
    Dedup per slug (kazdy artykul raz).
    """
    out, seen = [], set()
    for href, slug, raw in _ENTRY.findall(page_html):
        if slug in seen:
            continue
        seen.add(slug)
        is_korekta = "korekta" in raw.lower()
        name = _normalize_name(raw)
        if not name:
            continue
        out.append((name, BASE + href, is_korekta))
    return out


def parse_detail(page_html):
    """HTML strony artykulu osoby -> pdf_url (absolutny) lub None.

    Bierze PIERWSZY link PDF z div field-name-field-plik.
    """
    pdfs = _PDF.findall(page_html)
    return pdfs[0] if pdfs else None


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per roczne oswiadczenie.

    1) Dla kazdego roku pobiera tabele listingu (jeden GET), zbiera artykuly osob.
    2) Korekta wygrywa nad zwyklym rocznym: jesli ta sama osoba ma oba wpisy,
       bierzemy URL korekty, pomijamy zwykly.
    3) Dla kazdego wybranego artykulu jeden GET strony osoby -> pdf_url.
    Dedup per (name, year) na calym generatorze.
    """
    seen = set()
    for year, node in YEAR_NODES.items():
        time.sleep(0.3)
        try:
            listing_html = client.get(f"{BASE}/tabela/artykuly/748/{node}").text
        except Exception:  # noqa: BLE001 — rocznik moze byc jeszcze niepubliczny
            continue
        entries = parse_listing(listing_html)

        # Korekta-dedup: dla tej samej name wybieramy artykul korekty.
        # Budujemy slownik name -> (article_url, is_korekta); korekta nadpisuje zwykly.
        best = {}  # name -> (article_url, is_korekta)
        for name, art_url, is_korekta in entries:
            prev = best.get(name)
            if prev is None or (is_korekta and not prev[1]):
                best[name] = (art_url, is_korekta)

        for name, (art_url, _is_korekta) in best.items():
            if (name, year) in seen:
                continue
            time.sleep(0.3)
            try:
                detail_html = client.get(art_url).text
            except Exception:  # noqa: BLE001 — brakujacy artykul -> pomijamy
                continue
            pdf_url = parse_detail(detail_html)
            if not pdf_url:
                continue
            seen.add((name, year))
            yield name, year, pdf_url
