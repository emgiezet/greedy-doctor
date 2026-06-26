from pathlib import Path

from greedy_doctor.sources.skierniewice import (
    BASE,
    YEAR_ARTICLES,
    iter_declarations,
    parse_article,
    parse_name,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- parse_name (czyste; nazwa radnego siedzi w nazwie pliku) ----------


def test_parse_name_surname_first_single_given_name():
    # nazwa pliku jest juz 'Nazwisko Imie'; '_' -> spacja, ASCII-folded zostaje jak w zrodle
    assert parse_name("/dokumenty/Borowski_Jaroslaw_2024.pdf", 2024) == "Borowski Jaroslaw"
    assert parse_name("/dokumenty/Golebiewski_Jerzy_2024.pdf", 2024) == "Golebiewski Jerzy"


def test_parse_name_two_given_names():
    assert (
        parse_name("/dokumenty/Pastusiak_Janusz_Marek_2024.pdf", 2024)
        == "Pastusiak Janusz Marek"
    )


def test_parse_name_hyphenated_surname_normalized_across_years():
    # ten sam radny zakodowany niespojnie: 2024 bez spacji, 2025 z '_-_' -> jedno name
    assert (
        parse_name("/dokumenty/Polakowska-Binder_Eliza_2024.pdf", 2024)
        == "Polakowska-Binder Eliza"
    )
    assert (
        parse_name("/dokumenty/Polakowska_-_Binder_Eliza_2025.pdf", 2025)
        == "Polakowska-Binder Eliza"
    )


def test_parse_name_rejects_korekta_even_with_year():
    # korekta tez niesie '..._za_2024' -> filtr 'korekt' musi wygrac
    assert parse_name("/dokumenty/Sulek_Artur_korekta_oswiadczenia_za_2024.pdf", 2024) is None
    assert parse_name("/dokumenty/Lyzen_Piotr_korekta_za_2024.pdf", 2024) is None
    assert (
        parse_name("/dokumenty/Paradowski_Piotr_korekta_oswiadczenia_za_2024_rok.pdf", 2024)
        is None
    )


def test_parse_name_rejects_snapshot_and_wrong_year():
    # snapshot na poczatek kadencji nie konczy sie '_<rok>' -> None
    assert parse_name("/dokumenty/Borowski_Jaroslaw_poczatek_kadencji.pdf", 2024) is None
    # plik za inny rok niz pytany -> None (sufiks sie nie zgadza)
    assert parse_name("/dokumenty/Borowski_Jaroslaw_2024.pdf", 2025) is None


# ---------- parse_article (na zapisanym, realnym HTML artykulu) ----------


def test_parse_article_2024_keeps_21_annual_skips_korekty():
    rows = parse_article(_read("skierniewice_2024.html"), 2024)
    names = [n for n, _, _ in rows]
    # 21 radnych biezacej kadencji, jedno roczne na osobe
    assert len(rows) == 21
    assert len(set(names)) == 21  # bez duplikatow
    assert all(y == 2024 for _, y, _ in rows)
    # przykladowi radni obecni
    assert ("Borowski Jaroslaw", 2024, f"{BASE}/dokumenty/Borowski_Jaroslaw_2024.pdf") in rows
    assert (
        "Polakowska-Binder Eliza",
        2024,
        f"{BASE}/dokumenty/Polakowska-Binder_Eliza_2024.pdf",
    ) in rows
    # zaden URL nie jest korekta i wszystkie sa pelne (https://.../dokumenty/..._2024.pdf)
    assert all("korekt" not in u.lower() for _, _, u in rows)
    assert all(u.startswith(f"{BASE}/dokumenty/") and u.endswith("_2024.pdf") for _, _, u in rows)


def test_parse_article_2025_keeps_21_and_unifies_hyphen():
    rows = parse_article(_read("skierniewice_2025.html"), 2025)
    names = {n for n, _, _ in rows}
    assert len(rows) == 21
    assert len(names) == 21
    # nazwisko dwuczlonowe znormalizowane mimo '_-_' w nazwie pliku 2025
    assert "Polakowska-Binder Eliza" in names
    assert all(y == 2025 for _, y, _ in rows)


def test_parse_article_ignores_template_and_unrelated_pdf():
    # szablon .doc i plan zamowien (/zdjecia/..._P-1.pdf) nie sa oswiadczeniami
    rows = parse_article(_read("skierniewice_2024.html"), 2024)
    urls = {u for _, _, u in rows}
    assert all(".doc" not in u for u in urls)
    assert all("/zdjecia/" not in u for u in urls)


# ---------- iter_declarations (stub httpx mapujacy URL artykulu -> fixture) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Minimalny stub httpx.Client: /artykuly/{id} -> wczytany fixture HTML."""

    def __init__(self, by_article_id):
        self._by_id = by_article_id  # {id(int): html}

    def get(self, url):
        art_id = int(url.rsplit("/", 1)[-1])
        return _FakeResp(self._by_id[art_id])


def test_iter_declarations_both_years_dedup_per_name_year():
    client = _FakeClient(
        {
            YEAR_ARTICLES[2024]: _read("skierniewice_2024.html"),
            YEAR_ARTICLES[2025]: _read("skierniewice_2025.html"),
        }
    )
    rows = list(iter_declarations(client))
    # 21 radnych x 2 lata
    assert len(rows) == 42
    years = sorted({y for _, y, _ in rows})
    assert years == [2024, 2025]
    # ten sam radny pojawia sie raz na rok (klucz (name, year) unikalny)
    assert len({(n, y) for n, y, _ in rows}) == 42
    # spojnosc name miedzy latami: Polakowska-Binder ma DWA wpisy (2024 i 2025), nie cztery wariantow
    polak = sorted(y for n, y, _ in rows if n == "Polakowska-Binder Eliza")
    assert polak == [2024, 2025]
    # wszystkie URL-e to pelne PDF-y z /dokumenty/
    assert all(u.startswith(f"{BASE}/dokumenty/") and u.endswith(".pdf") for _, _, u in rows)
