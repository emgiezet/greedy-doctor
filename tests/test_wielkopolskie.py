from pathlib import Path

from greedy_doctor.sources.wielkopolskie import (
    _surname_first,
    parse_radny_page,
    parse_year_page,
)

FIX = Path(__file__).parent / "fixtures"


def test_surname_first():
    assert _surname_first("Leszek Bierła") == "Bierła Leszek"
    # nazwisko z myslnikiem to jeden token -> bez rozbicia
    assert (
        _surname_first("Katarzyna Rzepecka-Andrzejak") == "Rzepecka-Andrzejak Katarzyna"
    )


def test_year_page_lists_councilors():
    rows = parse_year_page(
        (FIX / "wielkopolskie_2024.html").read_text(encoding="utf-8")
    )
    assert len(rows) == 30
    names = {n for n, _ in rows}
    assert (
        "Bierła Leszek" in names
    )  # 'Imie Nazwisko' -> 'Nazwisko Imie', polskie znaki z title=
    # kazdy link to podstrona radnego (blok czytaj-wiecej), absolutny
    assert all(
        u.startswith("https://bip.umww.pl/7---k_62---k_63---k_") for _, u in rows
    )


def test_radny_page_resolves_pdf():
    page_url = "https://bip.umww.pl/7---k_62---k_63---k_368---leszek-bierla"
    pdf = parse_radny_page(
        (FIX / "wielkopolskie_bierla.html").read_text(encoding="utf-8"), page_url
    )
    # wzgledny ../artykuly/.../pliki/*.pdf rozwiazany urljoin do absolutnego
    assert (
        pdf
        == "https://bip.umww.pl/artykuly/2832433/pliki/20250612110001_bieraleszekza2024.pdf"
    )


def test_radny_page_no_pdf_returns_none():
    assert (
        parse_radny_page("<html><body>brak zalacznikow</body></html>", "https://x/y")
        is None
    )
