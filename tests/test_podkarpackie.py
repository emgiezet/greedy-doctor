from pathlib import Path

from greedy_doctor.sources.podkarpackie import (
    BASE,
    YEAR_CATEGORIES,
    iter_declarations,
    normalize_name,
    parse_listing,
    parse_pdf_url,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- czyste helpery ----------


def test_normalize_name_strips_underscore():
    assert normalize_name("BARAN_BRONISŁAW") == "BARAN BRONISŁAW"


def test_normalize_name_space_unchanged():
    assert normalize_name("BARAN BRONISŁAW") == "BARAN BRONISŁAW"


def test_normalize_name_collapses_extra_whitespace():
    assert normalize_name("BARAN  BRONISŁAW") == "BARAN BRONISŁAW"


def test_parse_pdf_url_with_version():
    href = "/component/govarticle?task=article.downloadAttachment&amp;id=871&amp;version=376"
    assert parse_pdf_url(href) == (
        f"{BASE}/component/govarticle?task=article.downloadAttachment&id=871&version=376"
    )


def test_parse_pdf_url_without_version_returns_none():
    href = "/component/govarticle?task=article.downloadAttachment&amp;id=871"
    assert parse_pdf_url(href) is None


def test_parse_listing_2025_spaces():
    rows = parse_listing(_read("podkarpackie_2025.html"), 2025)
    names = [n for n, _, _ in rows]
    assert "BARAN BRONISŁAW" in names
    assert "BERKOWICZ ADAM" in names
    assert len(rows) == 4


def test_parse_listing_2024_underscores_normalized():
    rows = parse_listing(_read("podkarpackie_2024.html"), 2024)
    names = [n for n, _, _ in rows]
    # underscores in title attribute get normalized
    assert "BARAN BRONISŁAW" in names
    assert "BERKOWICZ ADAM" in names
    assert len(rows) == 4


def test_parse_listing_dedup_per_name():
    # same anchor duplicated (ikona + tekst pattern)
    html = (
        '<a href="/component/govarticle?task=article.downloadAttachment&amp;id=1&amp;version=1"'
        ' title="Pobierz załącznik: KOWAL JAN">x</a>'
        '<a href="/component/govarticle?task=article.downloadAttachment&amp;id=1&amp;version=1"'
        ' title="Pobierz załącznik: KOWAL JAN">y</a>'
    )
    rows = parse_listing(html, 2025)
    assert len(rows) == 1


# ---------- iter_declarations (realne fixtury: dwa roczniki) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    def get(self, url):
        for year, slug in YEAR_CATEGORIES.items():
            if url == f"{BASE}/{slug}":
                return _FakeResp(_read(f"podkarpackie_{year}.html"))
        raise AssertionError(f"nieoczekiwany URL: {url}")


def test_iter_declarations_two_years():
    rows = list(iter_declarations(_FakeClient()))
    # 4 radni × 2 lata = 8; (name, year) różne bo ten sam radny w 2024 i 2025
    assert len(rows) == 8
    names_2025 = {n for n, y, _ in rows if y == 2025}
    names_2024 = {n for n, y, _ in rows if y == 2024}
    assert "BARAN BRONISŁAW" in names_2025
    assert "BARAN BRONISŁAW" in names_2024
    # PDF URL zawiera id + version (version obowiazkowy)
    for _, _, url in rows:
        assert "id=" in url and "version=" in url
        assert url.startswith(BASE)
