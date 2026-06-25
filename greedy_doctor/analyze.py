"""Metryka implied hours: ile godzin trzeba by przepracowac przy normie, by tyle zarobic.

Czyste funkcje (przetestowane) + worker (status classified -> analyzed): dla radnych-lekarzy
(majacych doctor_profile z enrich) liczy implied hours i zapisuje do `analysis`. Nie-lekarzy
przepuszcza bez wpisu. WYMAGA, by enrich zadzialal wczesniej (profile lekarzy gotowe).
"""

from greedy_doctor import db, norms
from greedy_doctor.queue import advance, claim


def etat_hourly(tier: str) -> float:
    return norms.ETAT_BASE * norms.ETAT_COEFF[tier] / norms.ETAT_MONTHLY_HOURS


def b2b_hourly(category: str) -> float:
    low, high = norms.B2B_RATES[category]
    return (low + high) / 2


def implied_monthly_hours(annual_income: float, hourly_rate: float) -> float:
    return annual_income / (hourly_rate * 12)


def classify_hours(hours: float) -> str:
    if hours >= norms.THRESHOLD_IMPLAUSIBLE:
        return "implausible"
    if hours >= norms.THRESHOLD_HEAVY:
        return "heavy"
    return "normal"


def total_income(entries) -> float:
    """Suma kwot dochodu, pomijajac None; dedup identycznych kwot (model bywa dubluje
    te sama pozycje pod dwoma tytulami, np. 'praktyka lekarska' i 'dzialalnosc ryczalt')."""
    seen, total = set(), 0.0
    for e in entries:
        a = e.get("amount")
        if a and a not in seen:
            seen.add(a)
            total += a
    return total


_MED_KEYWORDS = (
    "lekarsk",
    "lekarz",
    "medyczn",
    "szpital",
    "przychodni",
    "zdrowotn",
    "stomatolog",
    "nzoz",
)


def income_is_medical(entries) -> bool:
    """Deterministyczny backstop detekcji lekarza: slowa medyczne w tytulach dochodu
    (Bielik bywa niespojnie ustawia mentions_medical, np. pomija 'Praktyka Lekarska')."""
    text = " ".join((e.get("title") or "") for e in entries).lower()
    return any(k in text for k in _MED_KEYWORDS)


def is_high_earner(total: float) -> bool:
    """Czy roczna suma dochodu przekracza prog kandydata (MIN_INCOME)."""
    return total > norms.MIN_INCOME


def analyze_income(annual_income: float, tier: str, b2b_category: str) -> dict:
    implied_h_etat = implied_monthly_hours(annual_income, etat_hourly(tier))
    implied_h_b2b = implied_monthly_hours(annual_income, b2b_hourly(b2b_category))
    return {
        "implied_h_etat": implied_h_etat,
        "implied_h_b2b": implied_h_b2b,
        # flaga od B2B (realny, wyzszy model) — etat zawsze przeszacowany
        "flag": classify_hours(implied_h_b2b),
    }


def run_once(conn):
    cid = claim(conn, "classified")
    if cid is None:
        return False
    radny_id, year, parsed, tier, specs = conn.execute(
        "SELECT d.radny_id, d.year, d.parsed, dp.tier, dp.specializations "
        "FROM declaration d LEFT JOIN doctor_profile dp ON dp.radny_id = d.radny_id "
        "WHERE d.id = %s",
        (cid,),
    ).fetchone()
    parsed = parsed or {}
    # lekarz: profil z ZnanyLekarz LUB wzmianka medyczna w samym oswiadczeniu
    # (lapie lekarzy z prywatna praktyka, ktorych nie ma na ZnanyLekarz, np. Lubinski)
    is_doctor = (
        bool(tier)
        or bool(parsed.get("mentions_medical"))
        or income_is_medical(parsed.get("income", []))
    )
    if is_doctor:
        from greedy_doctor.enrich import b2b_category_for

        total = total_income(parsed.get("income", []))
        res = analyze_income(total, tier or "specialist", b2b_category_for(specs or []))
        conn.execute(
            "INSERT INTO analysis (radny_id, year, total_income, implied_h_etat, "
            "implied_h_b2b, flag) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (radny_id, year) DO UPDATE SET total_income=EXCLUDED.total_income, "
            "implied_h_etat=EXCLUDED.implied_h_etat, implied_h_b2b=EXCLUDED.implied_h_b2b, "
            "flag=EXCLUDED.flag",
            (
                radny_id,
                year,
                total,
                res["implied_h_etat"],
                res["implied_h_b2b"],
                res["flag"],
            ),
        )
    else:  # nie-lekarz -> skasuj ewentualny nieaktualny wpis (np. po re-klasyfikacji)
        conn.execute(
            "DELETE FROM analysis WHERE radny_id = %s AND year = %s", (radny_id, year)
        )
    advance(conn, cid, "analyzed")
    conn.commit()
    return True


def run():
    n = 0
    with db.connect() as conn:
        while run_once(conn):
            n += 1
    return n


if __name__ == "__main__":
    db.init_schema()
    print(f"przeanalizowano: {run()}")
