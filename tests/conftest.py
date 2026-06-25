"""Izolacja testow: osobna baza greedy_doctor_test, zeby testy (TRUNCATE itp.)
nie kasowaly scrawlowanych danych w dev DB. Ustawiane PRZED importem greedy_doctor.db."""

import os

import psycopg

TEST_DB = "greedy_doctor_test"
os.environ["DATABASE_URL"] = f"postgresql://greedy:greedy@localhost:5544/{TEST_DB}"

_admin = "postgresql://greedy:greedy@localhost:5544/postgres"
with psycopg.connect(_admin, autocommit=True) as _c:
    if not _c.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
    ).fetchone():
        _c.execute(f"CREATE DATABASE {TEST_DB}")
