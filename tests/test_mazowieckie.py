from pathlib import Path

from greedy_doctor.sources.mazowieckie import (
    is_current_annual,
    parse_name,
    parse_pdf_url,
    parse_person_declarations,
    parse_person_links,
)

FIX = Path(__file__).parent / "fixtures"


def test_parse_name_already_surname_first():
    # etykieta akordeonu jest juz 'Nazwisko Imie'; normalizujemy biale znaki
    assert parse_name("Rakowski Ludwik Jerzy") == "Rakowski Ludwik Jerzy"
    assert parse_name("  Lanc   Elżbieta ") == "Lanc Elżbieta"


def test_person_links_lists_councilors():
    rows = parse_person_links(
        (FIX / "mazowieckie_radni_list.html").read_text(encoding="utf-8")
    )
    names = {n for n, _ in rows}
    assert "Rakowski Ludwik Jerzy" in names
    assert "Cicholski Łukasz" in names  # polskie znaki z title=
    assert "Paprocka-Ślusarska Wioletta" in names  # nazwisko dwuczlonowe
    assert "Łęgiewicz Katarzyna" in names  # wiodace Ł
    # link osoby to wzgledny ?p= z separatorem osoby (@ = %40), rozwiniety przez urljoin w iter
    assert all(h.startswith("?p=Radni") and "%40" in h for _, h in rows)


def test_person_links_keeps_typo_duplicates_distinct():
    # akordeon ma wpisy-widma (literowka / skrocone imie) — to ROZNE wpisy, nie scalamy ich tutaj;
    # filtr rocznych VII (parse_person_declarations) odsiewa je pozniej (brak rocznego VII 2024/2025)
    rows = parse_person_links(
        (FIX / "mazowieckie_radni_list.html").read_text(encoding="utf-8")
    )
    names = {n for n, _ in rows}
    assert {"Benedykciński Grzegorz Józef", "Benedykcińśki Grzegorz"} <= names
    assert {"Uzdowska-Gacek Anna", "Uzdowska-Gacek Anna Maria"} <= names


def test_is_current_annual_filters_term_and_circumstance():
    assert is_current_annual("VII kadencja (2024-2029)", "Oświadczenie roczne") is True
    # roczne, ale POPRZEDNIA kadencja -> odrzucamy
    assert is_current_annual("VI kadencja (2018-2024)", "Oświadczenie roczne") is False
    # VII, ale snapshot na rozpoczecie / zakonczenie -> odrzucamy
    assert is_current_annual("VII kadencja (2024-2029)", "Oświadczenie pierwsze") is False
    assert is_current_annual("VII kadencja (2024-2029)", "Oświadczenie ostatnie") is False
    assert is_current_annual("VII kadencja (2024-2029)", "Korekta oświadczenia") is False


def test_person_declarations_keeps_only_vii_annual_2024_2025():
    # Rakowski ma 8 oswiadczen: roczne 2020-2023 (VI), 'pierwsze' 2024 (VII, brak kadencji),
    # 'ostatnie' 2024 (VI), roczne 2024 (VII), roczne 2025 (VII).
    # Zostaja DOKLADNIE: roczne VII za 2024 i 2025.
    decls = parse_person_declarations(
        (FIX / "mazowieckie_rakowski.html").read_text(encoding="utf-8")
    )
    years = sorted(y for _, y in decls)
    assert years == [2024, 2025]
    by_year = {y: u for u, y in decls}
    # rok 2024 -> wlasnie roczne VII (page-7), NIE 'ostatnie' VI (page-3) ani 'pierwsze' (page-6)
    assert by_year[2024].endswith(
        "/oswiadczenie-majatkowe-ludwik-jerzy-rakowski-7.html"
    )
    assert by_year[2025].endswith(
        "/oswiadczenie-majatkowe-ludwik-jerzy-rakowski-8.html"
    )
    # URL leaf-strony jest absolutny
    assert all(u.startswith("https://bip.mazovia.pl/") for u, _ in decls)


def test_person_declarations_year_2024_not_duplicated():
    # rok 2024 pojawia sie 3x w danych, ale tylko jedno jest rocznym VII -> brak duplikatu roku
    decls = parse_person_declarations(
        (FIX / "mazowieckie_rakowski.html").read_text(encoding="utf-8")
    )
    assert [y for _, y in decls].count(2024) == 1


def test_parse_pdf_url_from_attachment_json():
    data = {
        "title": "Oświadczenie majątkowe Ludwik Jerzy Rakowski",
        "components": [
            {"type": "ContentWYSIWYG", "content": {"content": ""}},
            {
                "type": "Attachment",
                "content": [
                    {
                        "src": "/resource/74569/rakowski+ludwik+20250430+20250430+om_.pdf",
                        "extension": "PDF",
                        "name": "abc.pdf",
                        "size": "4.72 MB",
                    }
                ],
            },
        ],
    }
    assert (
        parse_pdf_url(data)
        == "https://bip.mazovia.pl/resource/74569/rakowski+ludwik+20250430+20250430+om_.pdf"
    )


def test_parse_pdf_url_returns_none_when_no_attachment():
    assert parse_pdf_url({"components": [{"type": "Attachment", "content": None}]}) is None
    assert parse_pdf_url({"components": []}) is None
