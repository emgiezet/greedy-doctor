import json
from pathlib import Path

from greedy_doctor.sources.gdynia import (
    is_annual,
    parse_declarations,
    parse_name,
)

FIX = Path(__file__).parent / "fixtures"


def test_parse_name_strips_whitespace_and_entities():
    assert parse_name("Anisowicz Norbert ") == "Anisowicz Norbert"
    # encja HTML w nazwisku (Kłopotek-Główczewska) -> unescape
    assert (
        parse_name("Kłopotek-Gł&oacute;wczewska Natalia ")
        == "Kłopotek-Główczewska Natalia"
    )
    assert parse_name("  Zielińska   Joanna ") == "Zielińska Joanna"


def test_is_annual_only_year_end():
    assert is_annual("oświadczenie majątkowe radnego wg stanu na 31 grudnia 2024 r.")
    assert is_annual("oświadczenie majątkowe radnej wg stanu na 31 grudnia 2025 r.")
    # snapshot na slubowanie -> nie roczne
    assert not is_annual(
        "oświadczenie majątkowe radnego na dzień ślubowania 22.01.2025 r."
    )
    assert not is_annual(
        "korekta oświadczenia majątkowego wg stanu na 31 grudnia 2024 r."
    )
    assert not is_annual("")


def test_parse_declarations_2024_skips_slubowanie_and_missing_pdf():
    data = json.loads((FIX / "gdynia_radni_2024.json").read_text(encoding="utf-8"))
    rows = parse_declarations(data, 2024)
    names = {n for n, _, _ in rows}
    # Anisowicz (roczny) i Kłopotek-Główczewska (roczny, encja) wchodza
    assert "Anisowicz Norbert" in names
    assert "Kłopotek-Główczewska Natalia" in names
    # Żynis ma tylko snapshot 'na dzien slubowania' -> pominiety
    assert not any(n.startswith("Żynis") for n in names)
    # 'Bezpliku Jan' ma roczny tytul, ale pusty protocol.url -> pominiety
    assert "Bezpliku Jan" not in names
    assert all(y == 2024 for _, y, _ in rows)
    assert all(u.lower().endswith(".pdf") for _, _, u in rows)
    assert all(u.startswith("https://") for _, _, u in rows)


def test_parse_declarations_2025_annual():
    data = json.loads((FIX / "gdynia_radni_2025.json").read_text(encoding="utf-8"))
    rows = parse_declarations(data, 2025)
    assert {n for n, _, _ in rows} == {"Anisowicz Norbert", "Zielińska Joanna"}
    assert all(y == 2025 for _, y, _ in rows)


def test_parse_declarations_empty_response():
    assert parse_declarations({"posts": []}, 2024) == []
    assert parse_declarations({}, 2024) == []
