from greedy_doctor.sources.dolnoslaskie import is_annual, parse_name


def test_parse_name_surname_first():
    t = "Mirosław Lubiński - radny województwa - oświadczenie majątkowe za 2024 r."
    assert parse_name(t) == "Lubiński Mirosław"


def test_parse_name_double_firstname():
    t = "Mirosław Aleksander Lubiński - radny województwa - oświadczenie majątkowe za 2024 r."
    assert parse_name(t) == "Lubiński Mirosław Aleksander"


def test_is_annual_accepts_yearly_skips_corrections_and_start():
    assert is_annual("Jan Kowalski - radny - oświadczenie majątkowe za 2024 r.") is True
    assert (
        is_annual("Jan Kowalski - radny - korekta oświadczenia majątkowego za 2024 r.")
        is False
    )
    assert (
        is_annual("Jan Kowalski - radny - oświadczenie na rozpoczęcie kadencji")
        is False
    )
