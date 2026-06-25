from greedy_doctor.enrich import b2b_category_for, match_doctor

HITS = [
    {
        "name": "Sławomir",
        "surname": "Kowalski",
        "specializations": ["chirurg naczyniowy", "chirurg"],
        "cities": ["Warszawa"],
    },
    {
        "name": "Anna",
        "surname": "Kowalska",
        "specializations": ["pediatra"],
        "cities": ["Kielce", "Radom"],
    },
]


def test_matches_surname_firstname_and_city():
    is_doc, specs = match_doctor("Kowalski Sławomir", "Warszawa", HITS)
    assert is_doc is True
    assert "chirurg" in specs


def test_no_match_when_city_differs():
    is_doc, specs = match_doctor("Kowalski Sławomir", "Kraków", HITS)
    assert is_doc is False
    assert specs == []


def test_match_is_accent_and_order_insensitive():
    # diakrytyki, wielkosc liter, kolejnosc imie/nazwisko
    is_doc, specs = match_doctor("anna KOWALSKA", "kielce", HITS)
    assert is_doc is True
    assert "pediatra" in specs


def test_b2b_category_mapping_handles_declension():
    assert b2b_category_for(["anestezjolog"]) == "anesthesiology"
    assert b2b_category_for(["lekarz medycyny ratunkowej"]) == "sor"
    assert b2b_category_for(["radiolog"]) == "radiology"
    assert b2b_category_for(["kardiolog"]) == "general_shift"  # default


def test_match_without_city_matches_by_full_name():
    # sejmik wojewodzki: brak realnego miasta -> dopasowanie po pelnym imieniu+nazwisku
    is_doc, specs = match_doctor("Kowalski Sławomir", None, HITS)
    assert is_doc is True
    assert "chirurg" in specs
