from greedy_doctor import norms
from greedy_doctor.analyze import (
    analyze_income,
    classify_hours,
    etat_hourly,
    implied_monthly_hours,
    is_high_earner,
    total_income,
)


def test_etat_hourly_specialist_value():
    # 8181.72 * 1.45 / 168 h
    assert round(etat_hourly("specialist"), 2) == 70.62


def test_specialist_at_etat_base_works_full_time():
    # specjalista zarabiajacy roczna podstawe etatowa "pracuje" ~168 h/mc
    rate = etat_hourly("specialist")
    annual = rate * norms.ETAT_MONTHLY_HOURS * 12
    assert round(implied_monthly_hours(annual, rate)) == norms.ETAT_MONTHLY_HOURS


def test_classify_hours_bands():
    assert classify_hours(150) == "normal"
    assert classify_hours(168) == "normal"
    assert classify_hours(350) == "heavy"
    assert classify_hours(500) == "implausible"


def test_greedy_when_income_implies_impossible_hours():
    # 2 mln zl/rok przy medianie B2B anestezjologii -> >400 h/mc -> implausible
    result = analyze_income(
        annual_income=2_000_000, tier="specialist", b2b_category="anesthesiology"
    )
    assert result["flag"] == "implausible"
    assert result["implied_h_b2b"] > 400
    # etat zawsze przeszacowany (niska stawka zasadnicza) -> jeszcze wyzszy
    assert result["implied_h_etat"] > result["implied_h_b2b"]


def test_modest_income_is_normal():
    # specjalista na dyzurze ogolnym, ~600 tys/rok -> realistyczne godziny
    result = analyze_income(
        annual_income=600_000, tier="specialist", b2b_category="general_shift"
    )
    assert result["flag"] == "normal"


def test_total_income_sums_ignoring_none():
    entries = [
        {"title": "a", "amount": 250000.0},
        {"title": "b", "amount": None},  # "nie dotyczy" / nieczytelne
        {"title": "c", "amount": 120000.5},
    ]
    assert total_income(entries) == 370000.5


def test_high_earner_gate_must_exceed_threshold():
    # "przekracza 300k" -> rownosc nie wystarcza
    assert is_high_earner(norms.MIN_INCOME) is False
    assert is_high_earner(norms.MIN_INCOME + 0.01) is True
    assert is_high_earner(50_000) is False


def test_income_is_medical_detects_practice_title():
    from greedy_doctor.analyze import income_is_medical

    # deterministyczny backstop (Bielik bywa pomija mentions_medical)
    assert (
        income_is_medical(
            [
                {
                    "title": "Indywidualna Specjalistyczna Praktyka Lekarska",
                    "amount": 759914,
                }
            ]
        )
        is True
    )
    assert (
        income_is_medical([{"title": "Dieta radnego w 2024 roku", "amount": 9000}])
        is False
    )


def test_total_income_dedups_identical_amounts():
    # model bywa dubluje te sama pozycje pod dwoma tytulami -> liczymy raz
    entries = [
        {"title": "Praktyka Lekarska", "amount": 861247.43},
        {"title": "Działalność gospodarcza (ryczałt)", "amount": 861247.43},
    ]
    assert total_income(entries) == 861247.43
