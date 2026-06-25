import pytest

from greedy_doctor.classify import parse_model_json


def test_parses_valid_model_json():
    raw = (
        '{"income":[{"title":"umowa o prace ze Szpitalem Miejskim","amount":120000.5}],'
        '"mentions_medical":true}'
    )
    p = parse_model_json(raw)
    assert p.mentions_medical is True
    assert p.income[0].amount == 120000.5
    assert "Szpitalem" in p.income[0].title


def test_amount_may_be_null_when_unreadable():
    p = parse_model_json(
        '{"income":[{"title":"x","amount":null}],"mentions_medical":false}'
    )
    assert p.income[0].amount is None


def test_tolerates_omitted_amount_and_medical_flag():
    # realny przypadek: dla "nie dotyczy" model pomija amount i mentions_medical
    p = parse_model_json('{"income":[{"title":"nie dotyczy"}]}')
    assert p.income[0].amount is None
    assert p.mentions_medical is False


def test_rejects_non_json():
    with pytest.raises(ValueError):
        parse_model_json("blah, nie json")


def test_rejects_wrong_shape():
    with pytest.raises(ValueError):
        parse_model_json('{"foo": 1}')  # brak wymaganych pol
