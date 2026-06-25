from pathlib import Path

from greedy_doctor.sources.kielce import parse_listing, parse_person

FIX = Path(__file__).parent / "fixtures"


def test_listing_finds_all_councilors():
    html = (FIX / "kielce_listing.html").read_text(encoding="utf-8")
    urls = parse_listing(html)
    assert len(urls) == 25
    assert any(u.endswith("piasecki-michal.html") for u in urls)
    # tylko strony radnych, zero nawigacji
    assert all("kadencji-" in u and u.endswith(".html") for u in urls)


def test_person_extracts_name_and_annual_pdfs():
    html = (FIX / "kielce_piasecki.html").read_text(encoding="utf-8")
    name, docs = parse_person(html)
    assert name == "Piasecki Michał"
    years = {y for y, _ in docs}
    assert {2024, 2025} <= years
    assert all(url.lower().endswith(".pdf") for _, url in docs)
    # snapshot "na rozpoczecie kadencji" (bez 'za YYYY') pomijamy -> same lata int
    assert all(isinstance(y, int) for y, _ in docs)
