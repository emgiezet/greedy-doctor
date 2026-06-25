"""Kolejka oparta o Postgres. Kolumna `status` na declaration = stan w pipeline.

`claim` zajmuje jeden wiersz danego statusu z FOR UPDATE SKIP LOCKED — dwa workery
nigdy nie wezma tego samego wiersza. Blokada trzyma sie do commit/rollback wywolujacego,
wiec worker robi: claim -> przetworz -> advance -> commit. ponytail: zero brokera, zero
Redis; przy potrzebie retry/backoff -> procrastinate (tez na Postgresie).
"""


def claim(conn, in_status):
    """Zajmij jeden wiersz declaration o danym statusie albo None. Wymaga otwartej
    transakcji (autocommit=False) — blokada zyje do commit/rollback wywolujacego."""
    cur = conn.execute(
        "SELECT id FROM declaration WHERE status = %s "
        "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1",
        (in_status,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def advance(conn, declaration_id, new_status):
    conn.execute(
        "UPDATE declaration SET status = %s WHERE id = %s",
        (new_status, declaration_id),
    )
