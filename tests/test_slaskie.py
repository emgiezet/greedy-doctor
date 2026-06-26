from pathlib import Path

from greedy_doctor.sources.slaskie import (
    is_annual_filename,
    parse_doc_links,
    parse_listing,
    parse_pdf_url,
    parse_year_links,
)

FIX = Path(__file__).parent / "fixtures"


def test_listing_lists_councilors_surname_first():
    rows = parse_listing(
        (FIX / "slaskie_listing_p1.html").read_text(encoding="utf-8")
    )
    assert len(rows) == 10  # 10 radnych na stronie listingu
    names = {n for n, _ in rows}
    # title= jest juz 'Nazwisko Imie' (kontrakt) — nie odwracamy; polskie znaki zachowane
    assert "Adamczyk Rafał" in names
    assert "Baczyński Stanisław" in names
    assert "Białowąs Beata" in names
    # kazdy link to bezstanowy deep-link radnego ?p=Nazwisko@Imie (bez '^' roku), absolutny
    assert all(
        u.startswith("https://bip.slaskie.pl/sejmik_wojewodztwa/oswiadczenia_majatkowe?p=")
        for _, u in rows
    )
    assert all("%40" in u and "%5E" not in u for _, u in rows)


def test_year_links_keeps_current_term_only():
    # Strona radnego (Adamczyk) — ma wezel roczny 2024.
    rows = parse_year_links(
        (FIX / "slaskie_adamczyk_landing.html").read_text(encoding="utf-8")
    )
    years = {y for y, _ in rows}
    assert 2024 in years
    # archiwum poprzednich kadencji (2019-2023) odsiane przez MIN_YEAR
    assert all(y >= 2024 for y in years)
    # url roku to deep-link ?p=...%5E2024, absolutny
    url_2024 = dict(rows)[2024]
    assert url_2024.startswith(
        "https://bip.slaskie.pl/sejmik_wojewodztwa/oswiadczenia_majatkowe?p="
    )
    assert "%5E2024" in url_2024


def test_doc_links_from_year_page():
    # Strona roku Adamczyka 2024 ma DWA dokumenty (roczny + 'na poczatek kadencji').
    docs = parse_doc_links(
        (FIX / "slaskie_adamczyk_2024.html").read_text(encoding="utf-8")
    )
    assert len(docs) == 2
    assert all(
        u.startswith(
            "https://bip.slaskie.pl/sejmik_wojewodztwa/oswiadczenia_majatkowe/"
        )
        and u.endswith(".html")
        for u in docs
    )


def test_pdf_url_extracted_verbatim_double_encoded():
    # Podstrona dokumentu rocznego -> link PDF z biblioteki /resource/<id>/...pdf.
    # href jest PODWOJNIE url-encoded — zwracamy go verbatim (serwer tak go obsluguje).
    pdf = parse_pdf_url((FIX / "slaskie_doc_annual.html").read_text(encoding="utf-8"))
    assert pdf is not None
    assert pdf.startswith("https://bip.slaskie.pl/resource/")
    assert pdf.lower().endswith(".pdf")
    assert "%25C5" in pdf  # podwojne kodowanie zachowane (%25.. = zakodowane %..)

    # Snapshot 'na poczatek kadencji' tez ma PDF — parser go wyciaga (filtr typu jest osobno).
    snap = parse_pdf_url((FIX / "slaskie_doc_start.html").read_text(encoding="utf-8"))
    assert snap is not None and snap.lower().endswith(".pdf")


def test_pdf_url_none_when_no_attachment():
    assert parse_pdf_url("<html><body>brak pliku</body></html>") is None


def test_is_annual_filename_only_yearly():
    # Nazwy plikow tak, jak wystepuja w href (podwojnie url-encoded, '+' jako spacje).
    annual = (
        "/resource/81495/O%25C5%259Bwiadczenie+maj%25C4%2585tkowe+za+2024+rok"
        "_Rafa%25C5%2582+Adamczyk.pdf"
    )
    start = (
        "/resource/77379/O%25C5%259Bwiadczenie+maj%25C4%2585tkowe+na+pocz%25C4%2585tek"
        "+kadencji_Rafa%25C5%2582+Adamczyk.pdf"
    )
    end = (
        "/resource/1/O%25C5%259Bwiadczenie+maj%25C4%2585tkowe+na+koniec+kadencji"
        "_Jacek+%25C5%259Awierkocki.pdf"
    )
    korekta = (
        "/resource/2/Korekta+o%25C5%259Bwiadczenia+maj%25C4%2585tkowego"
        "_Jaros%25C5%2582aw+Szcz%25C4%2599sny+(na+koniec+kadencji).pdf"
    )
    wygasniecie = (
        "/resource/3/O%25C5%259Bwiadczenie+maj%25C4%2585tkowe_wyga%25C5%259Bni%25C4%2599cie"
        "+mandatu_Urszula+Koszutska.pdf"
    )

    assert is_annual_filename(annual, 2024) is True
    assert is_annual_filename(start, 2024) is False
    assert is_annual_filename(end, 2024) is False
    assert is_annual_filename(korekta, 2024) is False
    assert is_annual_filename(wygasniecie, 2024) is False
    # roczny za 2024 nie jest rocznym za 2025 (rok musi pasowac)
    assert is_annual_filename(annual, 2025) is False
