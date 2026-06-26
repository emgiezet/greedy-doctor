"""Adapter zrodla: Rada Miasta Skierniewice (kadencja 2024-2029).

BIP Urzedu Miasta (www.bip.um.skierniewice.pl) to statyczny CMS (PHP/nginx, zwykly HTML —
NIE Madkom: brak /api/menu, /api/articles). Strona oswiadczen majatkowych radnych
('/kategorie/oswiadczenia_majatkowe_radnych') to listing artykulow POGRUPOWANYCH PER ROK,
kazdy artykul pod wlasnym /artykuly/{id}:
  2024 -> /artykuly/4413   ('... zlozone za 2024 rok')
  2025 -> /artykuly/5347   ('... zlozone za 2025 rok')
Snapshoty maja WLASNE artykuly (pomijamy je przez sam dobor id): '/artykuly/3647'
(na poczatek kadencji 2024-2029) i '/artykuly/3601' (2 miesiace przed konca kadencji
2018-2024). Nowy rocznik -> dodac (rok, id) do YEAR_ARTICLES.

W artykule rocznym kazdy radny to JEDEN link PDF /dokumenty/<Nazwisko>_<Imie>[_Imie2]_<rok>.pdf.
Pulapki obsluzone:
- IMIE+NAZWISKO SIEDZI WYLACZNIE W NAZWIE PLIKU (na stronie nie ma osobnej etykiety z imieniem;
  tekst kotwicy to sama nazwa pliku + rozmiar). Nazwa jest ASCII-folded (bez polskich znakow:
  'Lyzen'=Łyżeń, 'Golebiewski'=Gołębiewski, 'Checielewski'=Chęcielewski) — to maksimum, jakie
  daje zrodlo; klasyfikator i tak dopasowuje po TRESCI PDF, a DB kluczuje po (city, name).
  Kolejnosc w nazwie pliku jest juz 'Nazwisko Imie' (zgodna z kontraktem) — nie odwracamy.
- KOREKTY: w tym samym artykule rocznym wisza tez pliki '..._korekta_oswiadczenia_za_2024.pdf'
  / '..._korekta_za_2024.pdf' / '..._korekta_..._2024_rok.pdf' — odrzucamy po slowie 'korekt'.
- NAZWISKA DWUCZLONOWE niespojnie kodowane miedzy latami: 'Polakowska-Binder_Eliza_2024.pdf'
  vs 'Polakowska_-_Binder_Eliza_2025.pdf'. Bez normalizacji ten sam radny dostaje DWA rozne
  name -> dwa wpisy w 'radny'. Dlatego sciagamy spacje wokol '-' (jednolicie 'Polakowska-Binder').
- na stronie sa tez nie-oswiadczeniowe linki: szablon '.doc' (wzor oswiadczenia) i przypadkowy
  '/zdjecia/..._P-1.pdf' (plan zamowien) — odrzucamy: wymagamy katalogu /dokumenty/ oraz
  konca nazwy '_<rok>.pdf'.
- dedup per (name, rok): w artykule rocznym kazdy radny ma jeden plik '_<rok>.pdf'.

PDF-y to SKANY (pdfplumber: 4 strony, 0 znakow) -> extract robi fallback OCR (tesseract -l pol).
Parsowanie czyste (HTML -> dane), bez sieci; sciaganie robi crawl.py. ponytail: id artykulow
rocznych zahardcodowane (zweryfikowane na zywym BIP: 21 radnych za 2024 i 21 za 2025, 0 kolizji
z korektami) — prostsze i stabilniejsze niz chodzenie po listingu kategorii.
"""

import html
import re
import time

CITY = "Skierniewice"
BASE = "https://www.bip.um.skierniewice.pl"
# Artykul roczny per ROK (kadencja 2024-2029). Snapshoty maja inne id i tu nie wchodza.
YEAR_ARTICLES = {2024: 4413, 2025: 5347}

# Link do pliku oswiadczenia w bibliotece /dokumenty/ (tylko PDF; szablon .doc i inne odpadaja).
_PDF_HREF = re.compile(r'href="(/dokumenty/[^"]+\.pdf)"', re.I)


def parse_name(pdf_href: str, year: int):
    """Nazwa pliku PDF -> 'Nazwisko Imie' dla rocznego oswiadczenia za `year`, albo None.

    Roczny plik konczy sie na '_<year>.pdf'. Odrzucamy korekty (slowo 'korekt' w nazwie)
    oraz pliki o innym sufiksie (snapshoty/szablony). Nazwa jest ASCII-folded (zrodlo nie
    podaje polskich znakow); kolejnosc 'Nazwisko Imie' juz zgodna. Spacje wokol '-' w
    nazwiskach dwuczlonowych sciagamy, by ten sam radny mial jednolite name miedzy latami.
    """
    fname = pdf_href.rsplit("/", 1)[-1]
    stem = fname[:-4]  # bez '.pdf'
    if "korekt" in stem.lower():
        return None
    suffix = f"_{year}"
    if not stem.endswith(suffix):
        return None
    base = stem[: -len(suffix)].replace("_", " ")
    base = re.sub(r"\s*-\s*", "-", base)  # 'Polakowska - Binder' -> 'Polakowska-Binder'
    name = " ".join(base.split())
    return name or None


def parse_article(page_html: str, year: int):
    """HTML artykulu rocznego -> [(name, year, pdf_url), ...] dla rocznych oswiadczen.

    Bierze tylko pliki '/dokumenty/..._<year>.pdf' (bez korekt); dedup per name. pdf_url
    absolutny. Korzysta z parse_name do odsiania korekt/snapshotow/szablonow.
    """
    src = html.unescape(page_html)
    out, seen = [], set()
    for href in _PDF_HREF.findall(src):
        name = parse_name(href, year)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append((name, year, BASE + href))
    return out


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url) per roczne oswiadczenie radnego.

    Jeden GET na artykul roczny (per rok z YEAR_ARTICLES). Dedup per (name, year) na wypadek
    gdyby ten sam radny mial dwa pliki '_<rok>.pdf' w jednym artykule.
    """
    seen = set()
    for year, art_id in YEAR_ARTICLES.items():
        time.sleep(0.3)
        page = client.get(f"{BASE}/artykuly/{art_id}").text
        for name, yr, pdf_url in parse_article(page, year):
            if (name, yr) in seen:
                continue
            seen.add((name, yr))
            yield name, yr, pdf_url
