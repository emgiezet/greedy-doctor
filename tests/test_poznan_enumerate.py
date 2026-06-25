from pathlib import Path

from greedy_doctor.sources.poznan import parse_listing, parse_person

FIX = Path(__file__).parent / "fixtures"


def test_listing_finds_councilors():
    urls = parse_listing((FIX / "poznan_listing.html").read_text(encoding="utf-8"))
    assert len(urls) >= 39
    assert any("andrzej-rataj" in u for u in urls)
    assert all("/bip/radni/" in u for u in urls)


def test_person_name_and_annual_declarations():
    name, docs = parse_person(
        (FIX / "poznan_ganowicz.html").read_text(encoding="utf-8")
    )
    assert name == "Ganowicz Grzegorz"  # 'Imie Nazwisko' -> 'Nazwisko Imie'
    years = {y for y, _ in docs}
    assert {2024, 2025} <= years  # 'za 2024 r.' i 'za rok 2025'
    assert all("lz_id=" in u for _, u in docs)  # PDF przez lz_id, nie .pdf
    # snapshot 'Pierwsze oswiadczenie w IX kadencji' (bez roku) pominiety
    assert all(isinstance(y, int) for y, _ in docs)
