from greedy_doctor.sources.pomorskie import annual_year, parse_name


def test_parse_name_already_surname_first():
    assert parse_name("Bonna Leszek") == "Bonna Leszek"
    assert parse_name("  Mielewczyk   Iwona ") == "Mielewczyk Iwona"


def test_annual_year_textual_date():
    n = "Radny Sejmiku Województwa Pomorskiego. Oświadczenie majątkowe wg stanu na dzień 31 grudnia roku poprzedniego tj. 31 grudnia 2024 roku."
    assert annual_year(n) == 2024


def test_annual_year_numeric_date():
    n = "Bonna Leszek - Wicemarszałek Województwa Pomorskiego - oświadczenie majątkowe wg.stanu majątkowego na dzień 31.12.2025 r."
    assert annual_year(n) == 2025


def test_annual_year_skips_corrections():
    n = "Przewodniczący Sejmiku. Korekta oświadczenia majątkowego wg stanu na dzień 31 grudnia roku poprzedniego tj. 31 grudnia 2023 roku"
    assert annual_year(n) is None


def test_annual_year_skips_non_year_end_dates():
    assert (
        annual_year(
            "...oświadczenie majątkowe wg stanu na dzień powołania tj. 07.05.2024 roku"
        )
        is None
    )
    assert annual_year("...na dzień wyboru tj. 24.06.2024 r..pdf") is None
    assert annual_year("...na dzień rezygnacji tj. 29.07.2024r..pdf") is None
    assert (
        annual_year("...składane na dwa miesiące przed upływem VI kadencji SWP") is None
    )
