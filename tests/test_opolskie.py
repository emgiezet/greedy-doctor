import json
from pathlib import Path

from greedy_doctor.sources.opolskie import (
    SEARCH_URL,
    annual_year,
    is_councilor_post,
    iter_declarations,
    parse_name,
    parse_pdf_url,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- czyste helpery ----------


def test_is_councilor_post_keeps_radny_skips_harmonogram():
    radny = {"link": "https://bip.opolskie.pl/2025/07/oswiadczenie-majatkowe-2025-szymon-godyla-radny-wojewodztwa-opolskiego-kadencja-vii-2024-2029/"}
    noise = {"link": "https://bip.opolskie.pl/2025/11/harmonogram-posiedzen-komisji-i-spotkan-radnych-wojewodztwa-opolskiego-kadencji-2024-2029/"}
    assert is_councilor_post(radny) is True
    assert is_councilor_post(noise) is False  # 'radnych-' (l.mn.) != 'radny-'


def test_parse_name_reverses_to_surname_first():
    assert (
        parse_name("Oświadczenie majątkowe – 2025, Szymon Godyla, Radny Województwa Opolskiego, kadencja: VII, 2024-2029")
        == "Godyla Szymon"
    )
    assert (
        parse_name("Oświadczenie majątkowe – 2024, Andrzej Buła, Radny Województwa Opolskiego, kadencja: VII, 2024-2029")
        == "Buła Andrzej"
    )


def test_parse_pdf_url_takes_canonical_skips_revisions():
    page = (
        '<a href="https://bip.opolskie.pl/wp-content/uploads/2025/07/Godyla-Szymon-oswiadczenie-majatkowe-za-2024-r.pdf">x</a>'
        '<a href="https://bip.opolskie.pl/wp-content/uploads/revisions/462941/Godyla-Szymon-oswiadczenie-majatkowe-za-2024-r.pdf">rev</a>'
    )
    assert parse_pdf_url(page) == (
        "https://bip.opolskie.pl/wp-content/uploads/2025/07/Godyla-Szymon-oswiadczenie-majatkowe-za-2024-r.pdf"
    )


def test_annual_year_fiscal_from_filename_snapshot_is_none():
    assert annual_year("https://x/Godyla-Szymon-oswiadczenie-majatkowe-za-2024-r.pdf") == 2024
    assert annual_year("https://x/Bula-Andrzej-Oswiadczenie-majatkowe-zlozone-30-dni.pdf") is None


# ---------- iter_declarations (realne fixtury: JSON listy + strony wpisow) ----------


class _FakeResp:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _build_client():
    posts = json.loads(_read("opolskie_posts.json"))
    by_id = {p["id"]: p["link"] for p in posts}
    pages = {
        by_id[462939]: "opolskie_godyla_annual.html",       # roczne za 2024
        by_id[413755]: "opolskie_godyla_snapshot.html",     # 30-dni (skip)
        by_id[463127]: "opolskie_antoszczyszyn_annual.html",  # roczne za 2024
        by_id[413839]: "opolskie_bula_snapshot.html",       # 30-dni (skip)
    }

    class _FakeClient:
        def get(self, url):
            if url == SEARCH_URL:
                return _FakeResp(payload=posts)
            if url in pages:
                return _FakeResp(text=_read(pages[url]))
            raise AssertionError(f"nieoczekiwany URL: {url}")

    return _FakeClient()


def test_iter_declarations_keeps_annual_skips_snapshot_and_noise():
    rows = list(iter_declarations(_build_client()))
    names = {n for n, _, _ in rows}
    # 2 roczne 'za 2024' (Godyla, Antoszczyszyn); 30-dni i harmonogram pominiete
    assert len(rows) == 2
    assert all(y == 2024 for _, y, _ in rows)
    assert (
        "Godyla Szymon",
        2024,
        "https://bip.opolskie.pl/wp-content/uploads/2025/07/Godyla-Szymon-oswiadczenie-majatkowe-za-2024-r.pdf",
    ) in rows
    assert "Antoszczyszyn Leszek" in names
    assert "Buła Andrzej" not in names  # ma tylko snapshot 30-dni w fixturze
    assert len({(n, y) for n, y, _ in rows}) == 2  # dedup per (name, year)
