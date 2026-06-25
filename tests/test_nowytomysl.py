from greedy_doctor.sources.nowytomysl import parse_attachment_name


def test_parse_attachment_name_strips_pdf():
    assert parse_attachment_name("Ratajczak Marek.pdf") == "Ratajczak Marek"
    assert parse_attachment_name("Ratajczak Marek") == "Ratajczak Marek"
    assert parse_attachment_name("  Górczyński Rafał.PDF ") == "Górczyński Rafał"
