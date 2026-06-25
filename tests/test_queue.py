from greedy_doctor import db
from greedy_doctor.queue import advance, claim


def _reset_and_seed(n):
    with db.connect() as conn:
        conn.execute("TRUNCATE declaration, radny RESTART IDENTITY CASCADE")
        conn.execute("INSERT INTO radny (city, name) VALUES ('Test', 'X')")
        for y in range(n):
            conn.execute(
                "INSERT INTO declaration (radny_id, year, source_url, status) "
                "VALUES (1, %s, 'u', 'downloaded')",
                (2000 + y,),
            )
        conn.commit()


def test_skip_locked_two_workers_get_different_rows():
    db.init_schema()
    _reset_and_seed(2)
    a, b = db.connect(), db.connect()
    try:
        id_a = claim(a, "downloaded")  # blokuje wiersz w transakcji A
        id_b = claim(b, "downloaded")  # MUSI pominac zablokowany wiersz A
        assert id_a is not None and id_b is not None
        assert id_a != id_b
    finally:
        a.rollback()
        a.close()
        b.rollback()
        b.close()


def test_claim_returns_none_when_empty():
    db.init_schema()
    _reset_and_seed(0)
    with db.connect() as conn:
        assert claim(conn, "downloaded") is None


def test_advance_changes_status():
    db.init_schema()
    _reset_and_seed(1)
    with db.connect() as conn:
        cid = claim(conn, "downloaded")
        advance(conn, cid, "text_extracted")
        conn.commit()
    with db.connect() as conn:
        cur = conn.execute("SELECT status FROM declaration WHERE id = %s", (cid,))
        assert cur.fetchone()[0] == "text_extracted"
