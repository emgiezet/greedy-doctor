"""Worker classify: raw_text -> ustrukturyzowany JSON (Bielik via Ollama).

Model w configu (OLLAMA_MODEL). Domyslnie Bielik-Minitron-7B (SpeakLeash, polski);
swap na Bielik-11B = zmienna srodowiskowa. Wyciaga pozycje dochodu (tytul+kwota) i flage
'wzmianka medyczna'. Autorytatywne 'czy lekarz + specjalizacja' rozstrzyga NIL (enrich.py).
"""

import os

import httpx
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ValidationError

from greedy_doctor import db
from greedy_doctor.queue import advance, claim

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get(
    "OLLAMA_MODEL", "hf.co/SpeakLeash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q8_0"
)


class IncomeEntry(BaseModel):
    title: str
    amount: float | None = None  # zl/rok; None gdy "nie dotyczy"/nieczytelna/pominieta


class ParsedDeclaration(BaseModel):
    income: list[IncomeEntry]  # wymagane — rdzen ekstrakcji
    mentions_medical: bool = False  # model bywa pomija -> brak wzmianki


def parse_model_json(raw: str) -> ParsedDeclaration:
    """Waliduje JSON modelu. ValueError gdy krzywy (lapiemy zly output)."""
    try:
        return ParsedDeclaration.model_validate_json(raw)
    except (ValidationError, ValueError) as e:
        raise ValueError(f"krzywy output modelu: {e}") from e


PROMPT = """Jesteś ekstraktorem danych z polskich oświadczeń majątkowych radnych.
Wyciągnij dochody radnego:
- z zatrudnienia, umów i diet (rubryka "inne dochody"),
- z DZIAŁALNOŚCI GOSPODARCZEJ i PRAKTYKI LEKARSKIEJ.
WAŻNE: dla każdego źródła podaj DOKŁADNIE JEDNĄ kwotę = DOCHÓD (netto). Jeśli podano
i przychód, i dochód tego samego źródła (albo brutto i netto) — wybierz dochód/netto
i NIE wypisuj drugiej kwoty.
NIE bierz oszczędności, nieruchomości, kredytów ani mienia ruchomego.
Uwaga: kwoty bywają oddzielone od opisu długimi kropkami wypełniającymi.

Zwróć TYLKO JSON:
{{"income":[{{"title":"<tytuł>","amount":<kwota zł jako liczba z kropką, lub null>}}],"mentions_medical":<true jeśli jest praktyka lekarska/medycyna/szpital/przychodnia, inaczej false>}}

Kwotę zapisz jako liczbę z kropką dziesiętną, np. "12 345,67 zł" -> 12345.67.
Jeśli kwoty nie ma lub jest nieczytelna, daj null — NIE zgaduj i NIE kopiuj przykładu.

TEKST:
{text}
"""


def classify_text(text: str) -> ParsedDeclaration:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": PROMPT.format(text=text),
            "stream": False,
            # structured outputs: wymusza poprawny JSON wg schematu (vs samo "json",
            # ktore puszczalo zepsuty output w srodku struktury)
            "format": ParsedDeclaration.model_json_schema(),
            "options": {"temperature": 0},
        },
        timeout=180,
    )
    resp.raise_for_status()
    return parse_model_json(resp.json()["response"])


def run_once(conn):
    cid = claim(conn, "text_extracted")
    if cid is None:
        return False
    (text,) = conn.execute(
        "SELECT raw_text FROM declaration WHERE id = %s", (cid,)
    ).fetchone()
    try:
        parsed = classify_text(text or "")
    except (ValueError, httpx.HTTPError):
        # ponytail: poison-row nie zapetla pipeline'u — odklada na bok, idziemy dalej
        advance(conn, cid, "classify_failed")
        conn.commit()
        return True
    conn.execute(
        "UPDATE declaration SET parsed = %s WHERE id = %s",
        (Jsonb(parsed.model_dump()), cid),
    )
    advance(conn, cid, "classified")
    conn.commit()
    return True


def run(limit=None):
    n = 0
    with db.connect() as conn:
        while run_once(conn):
            n += 1
            if limit and n >= limit:
                break
    return n


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    db.init_schema()
    print(f"sklasyfikowano: {run(args.limit)}")
