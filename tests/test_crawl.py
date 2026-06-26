"""_records (toleruje 3- i 4-tuple ze zrodel) + backfill_landing (komplementarny crawl)."""

from greedy_doctor import crawl, db


def _seed():
    db.init_schema()
    with db.connect() as c:
        c.execute(
            "TRUNCATE analysis, doctor_profile, declaration, radny RESTART IDENTITY CASCADE"
        )
        c.execute(
            "INSERT INTO radny (id, city, name) VALUES "
            "(1,'Testowo','Nowak Jan'), (2,'Testowo','Mała Ewa')"
        )
        c.execute(
            "INSERT INTO declaration (radny_id, year, source_url, status) VALUES "
            "(1,2024,'https://x/jan-2024.pdf','downloaded'), "
            "(1,2025,'https://x/jan-2025.pdf','downloaded'), "
            "(2,2024,'https://x/ewa-2024.pdf','downloaded')"
        )
        c.commit()


def _landing(radny_id, year):
    with db.connect() as c:
        return c.execute(
            "SELECT landing_url FROM declaration WHERE radny_id=%s AND year=%s",
            (radny_id, year),
        ).fetchone()[0]


class _FakeSrc:
    CITY = "Testowo"

    def __init__(self, records):
        self.records = records

    def iter_declarations(self, client):
        yield from self.records


def test_records_normalizes_3_and_4_tuples():
    src = _FakeSrc([("A", 2024, "p1"), ("B", 2025, "p2", "land2")])
    assert list(crawl._records(src, client=None)) == [
        ("A", 2024, "p1", None),
        ("B", 2025, "p2", "land2"),
    ]


def test_backfill_fills_landing_by_city_name_year(monkeypatch):
    _seed()
    fake = _FakeSrc(
        [
            ("Nowak Jan", 2024, "https://x/jan-2024.pdf", "https://bip/jan"),
            ("Nowak Jan", 2025, "https://x/jan-2025.pdf", "https://bip/jan"),
            ("Mała Ewa", 2024, "https://x/ewa-2024.pdf", None),  # brak landing -> pomijamy
        ]
    )
    monkeypatch.setitem(crawl.SOURCES, "faketest", fake)
    assert crawl.backfill_landing("faketest") == 2
    assert _landing(1, 2024) == "https://bip/jan"
    assert _landing(1, 2025) == "https://bip/jan"
    assert _landing(2, 2024) is None  # landing None -> wiersz nietkniety


def test_backfill_is_idempotent(monkeypatch):
    _seed()
    fake = _FakeSrc([("Nowak Jan", 2024, "p", "https://bip/jan")])
    monkeypatch.setitem(crawl.SOURCES, "faketest", fake)
    assert crawl.backfill_landing("faketest") == 1
    assert crawl.backfill_landing("faketest") == 0  # juz wypelnione -> 0 zmian
    assert _landing(1, 2024) == "https://bip/jan"
