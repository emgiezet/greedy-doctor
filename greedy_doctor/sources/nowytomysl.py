"""Adapter zrodla: Rada Miejska Nowy Tomyśl. CMS Madkom (REST API jak dolnoslaskie),
ale radni per ROK: jeden artykul/rok, zalaczniki = PDF per radny ('Nazwisko Imie.pdf').
PDF-y to SKANY -> extract robi OCR (tesseract). Sejmik/rada traktowana jak 'miasto'.
ponytail: ID artykulow rocznych zahardcodowane (zweryfikowane); nowe lata dodac.
"""

import re

CITY = "Nowy Tomyśl"
BASE = "https://bip.nowytomysl.pl"
YEAR_ARTICLES = {2024: 36676, 2025: 37874}


def parse_attachment_name(filename: str) -> str:
    """'Ratajczak Marek.pdf' -> 'Ratajczak Marek' (juz nazwisko-imie)."""
    return re.sub(r"\.pdf$", "", filename.strip(), flags=re.I).strip()


def iter_declarations(client):
    """(name, year, pdf_url) — zalaczniki rocznego artykulu to PDF-y per radny."""
    for year, aid in YEAR_ARTICLES.items():
        art = client.get(f"{BASE}/api/articles/{aid}").json()
        for att in art.get("attachments", []):
            name = parse_attachment_name(att.get("name", ""))
            link = att.get("link")
            if name and link:
                yield name, year, f"{BASE}/{link}"
