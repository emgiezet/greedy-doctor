"""Adapter zrodla: Rada Miasta Gdyni. BIP to React SPA z wlasnym JSON API (NIE Madkom).

Front (bip.um.gdynia.pl) jest renderowany JS; dane leca z https://api.um.gdynia.pl
(endpoint /contents/...). Drzewo: kategoria 'Oswiadczenia majatkowe' (2211)
-> /contents/subcategories/2211 = kategorie roczne (2024->9036, 2025->9210; to ROK
PUBLIKACJI). W kategorii rocznej jest kilka postow; ten z radnymi to JEDEN post-agregat
'Oswiadczenia majatkowe radnych za rok YYYY', a wszyscy radni siedza w jego polu
extended_data.declarations[] (flat): declarations_name='Nazwisko Imie', protocol.url=PDF.
Zaden fetch per radny nie jest potrzebny — jeden GET /contents/posts/{id} na rok.

PDF-y to SKANY (legacy.um.gdynia.pl/.../downloadFile/hash/<hash>.pdf, pdfplumber -> 0 znakow)
-> extract robi fallback OCR.

PUlapki obsluzone:
- ID postu-agregatu zahardcodowany per rok (zweryfikowany). UWAGA: slug bywa mylacy —
  post za rok 2024 ma slug 'oswiadczenia-majatkowe-radni-2025'. Ufamy tytulowi/intencji,
  nie slugowi. Nowy rok -> dodac id (z /contents/posts/category/<rok_cat>/ , trailing slash).
- declarations_name miewa biale znaki na koncu ORAZ encje HTML (np. 'Kłopotek-Gł&oacute;wczewska')
  -> html.unescape + strip.
- pomijamy snapshoty 'na dzien slubowania' i korekty — bierzemy tylko roczne '31 grudnia YYYY'
  (jak w sejmiku pomorskim).
ponytail: czyste parsowanie JSON->dane, bez sieci (testowalne na fixture). Sciaganie: crawl.py.
"""

import html
import re

CITY = "Gdynia"
BASE = "https://bip.um.gdynia.pl"
API = "https://api.um.gdynia.pl"
# Post-agregat 'Oswiadczenia majatkowe radnych za rok YYYY' (kadencja 2024-2029).
# Pomijamy 'za rok 2023 oraz na zakonczenie kadencji' (poprzednia kadencja).
RADNI_POSTS = {2024: 606859, 2025: 621729}


def parse_name(raw: str) -> str:
    """'Anisowicz Norbert ' / 'Kłopotek-Gł&oacute;wczewska Natalia ' -> czyste 'Nazwisko Imie'.

    Pole jest juz w kolejnosci nazwisko-imie; normalizujemy encje HTML i biale znaki.
    """
    return " ".join(html.unescape(raw or "").split())


def is_annual(protocol_title: str) -> bool:
    """Roczne 'wg stanu na 31 grudnia YYYY'; pomijamy 'na dzien slubowania' i korekty."""
    t = (protocol_title or "").lower()
    if "korekt" in t:
        return False
    return re.search(r"31\s+grudnia\s+20\d\d", t) is not None


def parse_declarations(post_json: dict, year: int):
    """JSON postu-agregatu -> [(name, year, pdf_url), ...] dla rocznych oswiadczen.

    Struktura: {"posts":[{..., "extended_data":{"declarations":[{declarations_name,
    protocol:{url,title}}, ...]}}]}. Dedup per nazwisko (jeden plik na radnego/rok).
    """
    posts = post_json.get("posts") or []
    if not posts:
        return []
    decls = (posts[0].get("extended_data") or {}).get("declarations") or []
    out, seen = [], set()
    for d in decls:
        proto = d.get("protocol") or {}
        url = proto.get("url")
        if not url or not is_annual(proto.get("title", "")):
            continue
        name = parse_name(d.get("declarations_name", ""))
        if not name or name in seen:
            continue
        seen.add(name)
        out.append((name, year, url))
    return out


def iter_declarations(client):
    """Jednolity interfejs crawla: (name, year, pdf_url). Jeden GET API na rok."""
    for year, post_id in RADNI_POSTS.items():
        data = client.get(f"{API}/contents/posts/{post_id}").json()
        yield from parse_declarations(data, year)
