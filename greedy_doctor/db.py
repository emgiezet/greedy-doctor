"""Polaczenie z Postgresem i schema. Kolumna `status` na declaration = kolejka."""

import os

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://greedy:greedy@localhost:5544/greedy_doctor"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS radny (
    id   SERIAL PRIMARY KEY,
    city TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (city, name)
);
CREATE TABLE IF NOT EXISTS declaration (
    id         SERIAL PRIMARY KEY,
    radny_id   INTEGER NOT NULL REFERENCES radny(id),
    year       INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    pdf_data   BYTEA,
    raw_text   TEXT,
    parsed     JSONB,
    status     TEXT NOT NULL DEFAULT 'downloaded',
    UNIQUE (radny_id, year)
);
ALTER TABLE declaration ADD COLUMN IF NOT EXISTS pdf_data BYTEA;
CREATE TABLE IF NOT EXISTS doctor_profile (
    radny_id        INTEGER PRIMARY KEY REFERENCES radny(id),
    pwz             TEXT,
    specializations TEXT[],
    tier            TEXT
);
CREATE TABLE IF NOT EXISTS analysis (
    radny_id       INTEGER NOT NULL REFERENCES radny(id),
    year           INTEGER NOT NULL,
    total_income   NUMERIC,
    implied_h_etat NUMERIC,
    implied_h_b2b  NUMERIC,
    flag           TEXT,
    PRIMARY KEY (radny_id, year)
);
"""


def connect():
    return psycopg.connect(DATABASE_URL)


def init_schema():
    with connect() as conn:
        for stmt in filter(str.strip, SCHEMA.split(";")):
            conn.execute(stmt)
        conn.commit()
