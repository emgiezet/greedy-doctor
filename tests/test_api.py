from greedy_doctor import db
from greedy_doctor.api import cities_with_doctors, doctor_detail, top_doctors


def _seed():
    db.init_schema()
    with db.connect() as c:
        c.execute(
            "TRUNCATE analysis, doctor_profile, declaration, radny RESTART IDENTITY CASCADE"
        )
        c.execute(
            "INSERT INTO radny (id, city, name) VALUES "
            "(1,'Testowo','Nowak Jan'), (2,'Testowo','Mala Ewa')"
        )
        c.execute(
            "INSERT INTO doctor_profile (radny_id, specializations, tier) VALUES "
            "(1, '{anestezjolog}', 'specialist'), (2, '{pediatra}', 'specialist')"
        )
        # Jan: 2 mln, implausible (kandydat); Ewa: 100k, ponizej progu 300k
        c.execute(
            "INSERT INTO analysis (radny_id, year, total_income, implied_h_etat, implied_h_b2b, flag) VALUES "
            "(1,2024,2000000,2360,444,'implausible'), (2,2024,100000,118,22,'normal')"
        )
        c.commit()


def test_top_doctors_filters_below_threshold_and_ranks():
    _seed()
    with db.connect() as c:
        rows = top_doctors(c, "Testowo", 10)
    names = [r["name"] for r in rows]
    assert "Nowak Jan" in names  # >300k -> kandydat
    assert "Mala Ewa" not in names  # <300k -> odsiany
    assert rows[0]["flag"] == "implausible"
    assert rows[0]["implied_h_b2b"] == 444


def test_cities_with_doctors_counts_only_candidates():
    _seed()
    with db.connect() as c:
        counts = {r["city"]: r["n_doctors"] for r in cities_with_doctors(c)}
    assert counts.get("Testowo") == 1  # tylko Jan przekracza prog


def test_doctor_detail_has_income_history():
    _seed()
    with db.connect() as c:
        d = doctor_detail(c, 1)
    assert d["name"] == "Nowak Jan"
    assert "anestezjolog" in d["specializations"]
    assert d["years"][0]["year"] == 2024
    assert d["years"][0]["total_income"] == 2000000
