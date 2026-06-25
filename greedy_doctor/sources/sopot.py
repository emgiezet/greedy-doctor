"""Adapter zrodla: Rada Miasta Sopotu (kadencja 2024-2029).

BIP Sopotu to React SPA, ale pod spodem ma REST JSON API w rodzinie Madkom
(/api/menu/{id}, /api/articles/{id}) — wiec chodzimy po API, nie po HTML.

Organizacja oswiadczen: per ORGAN + per ROK. Wezel menu 89 ('Oswiadczenia
majatkowe') ma artykuly-kontenery, m.in. 'Rada Miasta Sopotu 2024' (id 23782)
i 'Rada Miasta Sopotu 2025' (id 24669). Zalaczniki takiego artykulu to PDF-y
per radny. To uklad jak nowytomysl (artykul/rok -> zalaczniki/radny).

Nazwa zalacznika niesie imie i nazwisko, w kilku formatach:
  'Aleksandra Gosk.pdf'                                  (Imie Nazwisko + .pdf)
  'Radny Piotr Baginski.pdf' / 'Radna Barbara Brzezicka' (rola na poczatku)
  'Przewodniczaca Rady Miasta Sopotu -  Aleksandra Gosk' (funkcja + ' - ' + imie)
parse_councilor_name normalizuje to do 'Nazwisko Imie'.

PDF-y to SKANY (pdfplumber: 0 znakow na 4 stronach) -> extract robi OCR.

Pulapki:
- Imie stoi PRZED nazwiskiem (odwrotnie niz pomorskie/nowytomysl) -> flip.
- Nazwiska dwuczlonowe ('Niemczyk-Baltowska') traktujemy jako jeden ostatni token.
- W art 2024 Gosk wystepuje DWA razy (plain + z funkcja przewodniczacej)
  -> dedup per (nazwisko, rok).
- Pomijamy kontenery 'poczatek/koniec kadencji' i lata <2024 (inna kadencja /
  snapshoty) — bierzemy tylko zahardcodowane roczne artykuly biezacej kadencji.
ponytail: ID artykulow rocznych zweryfikowane recznie; nowy rok = dopisz ID.
"""

import re

CITY = "Sopot"
BASE = "https://bip.sopot.pl"

# Artykuly-kontenery 'Rada Miasta Sopotu <rok>' pod wezlem 89 (Oswiadczenia majatkowe).
YEAR_ARTICLES = {2024: 23782, 2025: 24669}

# Slowa funkcji/roli na poczatku nazwy zalacznika (przed wlasciwym imieniem).
_ROLE_PREFIX = re.compile(
    r"^(?:radny|radna|przewodnicz[aą]c[ay]|wiceprzewodnicz[aą]c[ay])\s+",
    re.I,
)


def parse_councilor_name(att_name: str) -> str:
    """Nazwa zalacznika -> 'Nazwisko Imie'. Pusty string gdy nie da sie sparsowac.

    Kroki: utnij .pdf; jesli jest separator funkcji ' - ', wez czesc po ostatnim;
    zdejmij role (Radny/Radna/Przewodniczaca...); odwroc Imie Nazwisko -> Nazwisko Imie
    (nazwisko = ostatni token, dwuczlonowe z myslnikiem zostaja caloscia).
    """
    s = re.sub(r"\.pdf$", "", (att_name or "").strip(), flags=re.I).strip()
    # Funkcja oddzielona ' - ' (zmienna liczba spacji): wlasciwe imie jest za nim.
    if " - " in s or re.search(r"\s-\s", s):
        s = re.split(r"\s+-\s+", s)[-1].strip()
    # Rola na poczatku ('Radny Jan...') — zdejmij tylko gdy zostana >=2 tokeny.
    stripped = _ROLE_PREFIX.sub("", s).strip()
    if len(stripped.split()) >= 2:
        s = stripped
    toks = s.split()
    if len(toks) < 2:
        return ""
    # Imie(-ona) Nazwisko -> Nazwisko Imie(-ona); nazwisko = ostatni token.
    return " ".join([toks[-1], *toks[:-1]])


def iter_declarations(client):
    """(name, year, pdf_url) — zalaczniki rocznego artykulu to PDF-y per radny.

    Dedup per (nazwisko, rok): w 2024 ta sama osoba bywa zalaczona dwukrotnie.
    """
    for year, aid in YEAR_ARTICLES.items():
        art = client.get(f"{BASE}/api/articles/{aid}").json()
        seen = set()
        for att in art.get("attachments", []):
            if att.get("deleted"):
                continue
            name = parse_councilor_name(att.get("name", ""))
            link = att.get("link")
            if not name or not link or name in seen:
                continue
            seen.add(name)
            yield name, year, f"{BASE}/{link}"
