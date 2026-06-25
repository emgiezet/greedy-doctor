"""API read-only (FastAPI): miasta, top10 lekarzy per miasto, szczegoly lekarza.

Kandydat = total_income > MIN_INCOME (drobnica odsiana). Ranking: implied_h_b2b malejaco
(najbardziej "greedy" = najwiecej godzin potrzebnych przy realnej stawce). Wiersze per rok.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from greedy_doctor import db, norms


def cities_with_doctors(conn):
    return (
        conn.cursor(row_factory=dict_row)
        .execute(
            "SELECT r.city, count(DISTINCT a.radny_id) AS n_doctors "
            "FROM analysis a JOIN radny r ON r.id = a.radny_id "
            "WHERE a.total_income > %s "
            "GROUP BY r.city ORDER BY n_doctors DESC, r.city",
            (norms.MIN_INCOME,),
        )
        .fetchall()
    )


def top_doctors(conn, city, limit=10):
    return (
        conn.cursor(row_factory=dict_row)
        .execute(
            "SELECT a.radny_id, r.name, dp.specializations, a.year, a.total_income, "
            "a.implied_h_etat, a.implied_h_b2b, a.flag "
            "FROM analysis a JOIN radny r ON r.id = a.radny_id "
            "LEFT JOIN doctor_profile dp ON dp.radny_id = a.radny_id "
            "WHERE r.city = %s AND a.total_income > %s "
            "ORDER BY a.implied_h_b2b DESC LIMIT %s",
            (city, norms.MIN_INCOME, limit),
        )
        .fetchall()
    )


def doctor_detail(conn, radny_id):
    cur = conn.cursor(row_factory=dict_row)
    base = cur.execute(
        "SELECT r.id, r.name, r.city, dp.specializations, dp.tier "
        "FROM radny r LEFT JOIN doctor_profile dp ON dp.radny_id = r.id WHERE r.id = %s",
        (radny_id,),
    ).fetchone()
    years = cur.execute(
        "SELECT year, total_income, implied_h_etat, implied_h_b2b, flag "
        "FROM analysis WHERE radny_id = %s ORDER BY year",
        (radny_id,),
    ).fetchall()
    return {**base, "years": years}


app = FastAPI(title="greedy-doctor")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/api/cities")
def api_cities():
    with db.connect() as conn:
        return cities_with_doctors(conn)


@app.get("/api/cities/{city}/doctors")
def api_city_doctors(city: str, limit: int = 10):
    with db.connect() as conn:
        return top_doctors(conn, city, limit)


@app.get("/api/doctors/{radny_id}")
def api_doctor(radny_id: int):
    with db.connect() as conn:
        return doctor_detail(conn, radny_id)
