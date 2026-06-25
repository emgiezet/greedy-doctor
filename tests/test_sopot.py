from greedy_doctor.sources.sopot import parse_councilor_name


def test_plain_name_with_pdf():
    # 2024: "Imię Nazwisko.pdf"
    assert parse_councilor_name("Aleksandra Gosk.pdf") == "Gosk Aleksandra"


def test_role_prefix_radny_radna():
    assert parse_councilor_name("Radny Piotr Bagiński.pdf") == "Bagiński Piotr"
    assert parse_councilor_name("Radna Barbara Brzezicka") == "Brzezicka Barbara"


def test_function_title_with_separator():
    # 2025 single space, 2024 double space — both -> nazwisko imie
    assert (
        parse_councilor_name("Przewodnicząca Rady Miasta Sopotu - Aleksandra Gosk")
        == "Gosk Aleksandra"
    )
    assert (
        parse_councilor_name("Przewodnicząca Rady Miasta Sopotu -  Aleksandra Gosk")
        == "Gosk Aleksandra"
    )


def test_hyphenated_surname_kept_whole():
    # surname = ostatni token; myslnik w nazwisku zostaje
    assert (
        parse_councilor_name("Radna Karolina Niemczyk-Bałtowska")
        == "Niemczyk-Bałtowska Karolina"
    )


def test_double_first_name():
    assert parse_councilor_name("Radny Jan Maria Kowalski") == "Kowalski Jan Maria"


def test_dedup_gosk_in_2024_yields_one_entry():
    # art 23782 ma dwa zalaczniki dla Gosk (plain + z funkcja) -> jedna osoba/rok
    name_plain = parse_councilor_name("Aleksandra Gosk.pdf")
    name_func = parse_councilor_name(
        "Przewodnicząca Rady Miasta Sopotu -  Aleksandra Gosk"
    )
    assert name_plain == name_func == "Gosk Aleksandra"
