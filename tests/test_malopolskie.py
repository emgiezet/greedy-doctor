import json
from pathlib import Path

from greedy_doctor.sources.malopolskie import (
    BASE,
    annual_year,
    iter_declarations,
    parse_name,
)

FIX = Path(__file__).parent / "fixtures"


def test_parse_name_already_surname_first():
    # Title artykulu juz jest 'Nazwisko Imie'; normalizujemy tylko biale znaki.
    assert parse_name("Arkit Tadeusz") == "Arkit Tadeusz"
    assert parse_name("  Biedroń   Grzegorz ") == "Biedroń Grzegorz"
    assert parse_name("Duda Jan Tadeusz") == "Duda Jan Tadeusz"
    assert parse_name("") == ""


def test_annual_year_standard():
    assert annual_year("Oświadczenie majątkowe za 2024 rok Arkit_T") == 2024
    assert annual_year("Oświadczenie majątkowe za 2025 rok Kowalski_J") == 2025


def test_annual_year_no_space_after_za():
    # radny Duda: 'za2024' bez spacji
    assert annual_year("Oświadczenie majątkowe za2024 rok Duda_Wiesław_Jan") == 2024


def test_annual_year_skips_snapshot_poczatek_kadencji():
    # snapshot na poczatek kadencji nie ma 'za YYYY' -> None
    assert (
        annual_year("Arkit_T oświadczenie majątkowe na początek kadencji 2024_2029.pdf")
        is None
    )


def test_annual_year_skips_corrections_even_with_year():
    # korekta tez niesie 'za 2024 rok' -> filtr korekty musi wygrac
    assert (
        annual_year("Michał Słowik korekta oświadczenia majątkowego za 2024 rok. ")
        is None
    )
    # literowka 'korektoa' nadal zaczyna sie od 'korekt'
    assert (
        annual_year("Słowik Michał korektoa oświadczenia majątkowego na początek kadencji. ")
        is None
    )
    assert annual_year("") is None


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Minimalny stub httpx: mapuje URL -> wczytany fixture JSON."""

    def __init__(self, listing, articles):
        self._listing = listing
        self._articles = articles  # {article_id(str): payload}

    def get(self, url):
        if "/api/menu/" in url:
            return _FakeResp(self._listing)
        if "/api/articles/" in url:
            aid = url.rsplit("/", 1)[-1]
            return _FakeResp(self._articles[aid])
        raise AssertionError(f"unexpected URL: {url}")


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_iter_declarations_skips_snapshots_corrections_and_builds_urls():
    # Listing z 3 radnymi (Arkit, Slowik, Duda); kazdy artykul z fixture.
    arkit = _load("malopolskie_arkit.json")
    slowik = _load("malopolskie_slowik.json")
    duda = _load("malopolskie_duda.json")
    listing = {
        "articles": [
            {"id": str(arkit["id"])},
            {"id": str(slowik["id"])},
            {"id": str(duda["id"])},
        ]
    }
    articles = {
        str(arkit["id"]): arkit,
        str(slowik["id"]): slowik,
        str(duda["id"]): duda,
    }
    rows = list(iter_declarations(_FakeClient(listing, articles)))

    # Po jednym rocznym (za 2024) na radnego — snapshoty i korekty pominiete.
    assert sorted(rows) == sorted(
        [
            ("Arkit Tadeusz", 2024, f"{BASE}/e,pobierz,get.html?id=3881268"),
            ("Słowik Michał", 2024, f"{BASE}/e,pobierz,get.html?id=3881514"),
            ("Duda Jan", 2024, f"{BASE}/e,pobierz,get.html?id=3881329"),
        ]
    )
    # Slowik ma 2 korekty + snapshot -> mimo to dokladnie jeden wpis (rok 2024).
    assert sum(1 for n, _, _ in rows if n == "Słowik Michał") == 1
    # wszystkie URL-e absolutne do endpointu pobierania
    assert all(u.startswith(f"{BASE}/e,pobierz,get.html?id=") for _, _, u in rows)
    assert all(y == 2024 for _, y, _ in rows)


def test_iter_declarations_dedups_same_year_twice():
    # Sztuczny artykul: dwa zalaczniki za ten sam rok -> jeden wpis (dedup per rok).
    art = {
        "id": 999,
        "title": "Testowy Jan",
        "attachments": [
            {"name": "Oświadczenie majątkowe za 2024 rok A", "link": "e,pobierz,get.html?id=1", "deleted": False},
            {"name": "Oświadczenie majątkowe za 2024 rok B", "link": "e,pobierz,get.html?id=2", "deleted": False},
        ],
    }
    listing = {"articles": [{"id": "999"}]}
    rows = list(iter_declarations(_FakeClient(listing, {"999": art})))
    assert rows == [("Testowy Jan", 2024, f"{BASE}/e,pobierz,get.html?id=1")]
