from pathlib import Path

from greedy_doctor.sources.lubelskie import (
    BASE,
    LISTING_URL,
    iter_declarations,
    parse_card,
    parse_name,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


def _card(name, rows):
    """Sklej wewnetrzny HTML karty radnego: naglowek osoby + wiersze (rok, opis, plik)."""
    head = f'<a href="?id=osoba&p1=1" class="h">{name}</a>'
    body = "".join(
        f'<div class="col-sm-1">{y}</div>'
        f'<div class="col-sm-8">{desc}</div>'
        f'<div class="col-sm-3"><a href="upload/pliki/{fn}">pdf</a></div>'
        for y, desc, fn in rows
    )
    return head + body


# ---------- parse_name (czyste) ----------


def test_parse_name_surname_first_with_diacritics():
    assert (
        parse_name('<a href="?id=osoba&p1=7" class="x">Brzózka Radosław</a>')
        == "Brzózka Radosław"
    )


def test_parse_name_none_when_no_person_anchor():
    assert parse_name('<a href="/inne">cos</a>') is None


# ---------- parse_card (czyste; synteza realnej struktury wiersza) ----------


def test_parse_card_keeps_annual_skips_pre_2024():
    card = _card(
        "Kowalski Jan",
        [
            ("2025", "oświadczenie majątkowe za 2025 r.", "k_2025.pdf"),
            ("2023", "oświadczenie majątkowe za 2023 r.", "k_2023.pdf"),  # < MIN_YEAR
        ],
    )
    assert parse_card(card) == [("Kowalski Jan", 2025, f"{BASE}/upload/pliki/k_2025.pdf")]


def test_parse_card_korekta_beats_plain_annual_same_year():
    card = _card(
        "Nowak Anna",
        [
            ("2024", "oświadczenie majątkowe za 2024 r.", "annual.pdf"),
            ("2024", "korekta oświadczenia majątkowego za 2024 r.", "korekta.pdf"),
        ],
    )
    assert parse_card(card) == [("Nowak Anna", 2024, f"{BASE}/upload/pliki/korekta.pdf")]


def test_parse_card_skips_snapshot_and_explanation():
    card = _card(
        "Lis Ewa",
        [
            ("2024", "oświadczenie majątkowe - początek kadencji", "snap.pdf"),
            ("2025", "wyjaśnienie do oświadczenia majątkowego za 2025 r.", "wyj.pdf"),
        ],
    )
    assert parse_card(card) == []


# ---------- iter_declarations (na realnym, przycietym fixture) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Stub httpx: jedyny GET to strona listingu (bez paginacji)."""

    def __init__(self, page):
        self._page = page

    def get(self, url):
        assert url == LISTING_URL
        return _FakeResp(self._page)


def test_iter_declarations_on_trimmed_fixture():
    rows = list(iter_declarations(_FakeClient(_read("lubelskie_list.html"))))
    names = {n for n, _, _ in rows}
    # 6 zwyklych radnych (rocznik 2025); karty snapshot/wyjasnienie nie wnosza nic
    assert len(rows) == 6
    assert "Lisowska Bożena" not in names
    assert "Sosnowski Wojciech" not in names
    assert "Barszczewska Barbara" in names
    assert all(y == 2025 for _, y, _ in rows)
    assert all(u.startswith(f"{BASE}/upload/pliki/") for _, _, u in rows)
    assert len({(n, y) for n, y, _ in rows}) == 6  # dedup per (name, year)
