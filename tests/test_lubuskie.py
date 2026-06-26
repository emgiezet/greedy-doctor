from pathlib import Path

import pytest

from greedy_doctor.sources.lubuskie import (
    BASE,
    LISTING_URL,
    MIN_YEAR,
    RADNI_GROUP,
    has_any_min_year,
    iter_declarations,
    parse_listing_page,
    parse_name,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- parse_name (czyste) ----------


def test_parse_name_dwuczlonowe_imie():
    # 'Andrzej Leszek Wieczorek - pierwsze' -> 'Wieczorek Andrzej Leszek'
    assert parse_name("Andrzej Leszek Wieczorek - pierwsze") == "Wieczorek Andrzej Leszek"


def test_parse_name_jednoczlonowe():
    # 'Jerzy Wierchowicz - kolejne' -> 'Wierchowicz Jerzy'
    assert parse_name("Jerzy Wierchowicz - kolejne") == "Wierchowicz Jerzy"


def test_parse_name_polskie_znaki():
    # Imiona/nazwiska z polskimi znakami zachowane
    assert parse_name("Anna Synowiec - pierwsze") == "Synowiec Anna"
    result = parse_name("Małgorzata Beata Paluch-Słowińska - pierwsze")
    assert result == "Paluch-Słowińska Małgorzata Beata"


def test_parse_name_kolejne_luw():
    # ' - kolejne LUW' tez odpada; liczy sie tylko czesc przed ' - '
    assert parse_name("Anna Synowiec - kolejne LUW") == "Synowiec Anna"


def test_parse_name_none_on_empty():
    assert parse_name("") is None
    assert parse_name("  ") is None


def test_parse_name_bez_sufiksu():
    # Brak ' - ' w nazwie -> po prostu odwroc
    assert parse_name("Jan Nowak") == "Nowak Jan"


# ---------- parse_listing_page (na fixture HTML) ----------


def test_parse_listing_p1_brak_radnych():
    # Strona z samymi nie-radnymi (kierownicy, skarbnik, czlonkowie zarzadu) -> pusty wynik
    rows = parse_listing_page(_read("lubuskie_listing_p1.html"))
    assert rows == []


def test_parse_listing_p2_tylko_radni_min_year():
    # Strona z mieszanymi grupami; zwraca tylko radnych z roku >= MIN_YEAR
    rows = parse_listing_page(_read("lubuskie_listing_p2.html"))
    names = [n for n, _, _ in rows]
    assert len(rows) == 3
    # Nie-radni (Bogumiła Jaske, Michał Anczykowski) nie powinni trafic do wyniku
    assert all(n not in names for n in ["Jaske Bogumiła", "Anczykowski Michał"])
    # Radni obecni
    assert "Wierchowicz Jerzy" in names
    assert "Wieczorek Andrzej" in names
    assert "Turczyniak Leszek" in names


def test_parse_listing_p22_radni_2024():
    # Strona z radnymi 2024 (pierwsze oswiadczenie kadencji) + nie-radnymi
    rows = parse_listing_page(_read("lubuskie_listing_p22.html"))
    assert len(rows) == 4
    names = {n for n, _, _ in rows}
    assert all(y == 2024 for _, y, _ in rows)
    assert "Synowiec Anna" in names
    assert "Wierchowicz Jerzy" in names
    assert "Wieczorek Andrzej Leszek" in names
    assert "Paluch-Słowińska Małgorzata Beata" in names
    # Nie-radni (Wróblewski, Piosik) nie trafiaja do wyniku
    assert "Wróblewski Tomasz" not in names
    assert "Piosik Jakub" not in names


def test_parse_listing_p22_pdf_url_format():
    # pdf_url to pelny URL pobierz.php z parametrami plik= i id=
    rows = parse_listing_page(_read("lubuskie_listing_p22.html"))
    for _, _, url in rows:
        assert url.startswith("https://bip.lubuskie.pl/system/pobierz.php?plik=")
        assert "&id=" in url


def test_parse_listing_old_ponizej_min_year():
    # Strona z wpisami 2023 -> brak wynikow (rok < MIN_YEAR)
    rows = parse_listing_page(_read("lubuskie_listing_old.html"))
    assert rows == []


def test_parse_listing_p22_konkretny_pdf():
    # Sprawdz konkretny PDF dla Wierchowicza
    rows = parse_listing_page(_read("lubuskie_listing_p22.html"))
    wierch = [(n, y, u) for n, y, u in rows if n == "Wierchowicz Jerzy"]
    assert len(wierch) == 1
    _, year, url = wierch[0]
    assert year == 2024
    assert "Wierchowicz_Jerzy_pierwsze.pdf" in url
    assert "id=a2bb154904cfad7bbde8bc52949d8c1c" in url


# ---------- has_any_min_year ----------


def test_has_any_min_year_true_gdy_min_rok():
    assert has_any_min_year(_read("lubuskie_listing_p22.html")) is True


def test_has_any_min_year_false_gdy_stary_rok():
    assert has_any_min_year(_read("lubuskie_listing_old.html")) is False


def test_has_any_min_year_true_gdy_wyzszy_rok():
    # Strona z rokiem 2026 (> MIN_YEAR) tez daje True
    assert has_any_min_year(_read("lubuskie_listing_p1.html")) is True


# ---------- iter_declarations (stub httpx) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Minimalny stub httpx: URL strony listingu -> HTML z fixture."""

    def __init__(self, pages):
        # pages: {page_num(int): html_text}
        self._pages = pages

    def get(self, url):
        # Wyciagnij numer strony z URL, np. /oswiadczenia/343/2/rok/ -> 2
        # Strona 1 moze byc pod /343/1/rok/ lub /343/rok/ (bez numeru)
        import re as _re
        m = _re.search(r"/oswiadczenia/343/(\d+)/rok/", url)
        page = int(m.group(1)) if m else 1
        if page not in self._pages:
            raise KeyError(f"brak fixture dla strony {page}: {url}")
        return _FakeResp(self._pages[page])


def test_iter_declarations_filtruje_nieradnych():
    # Strona 1 (brak radnych rok 2026) + strona 2 (radni rok 2026) + stara strona (zatrzymuje)
    client = _FakeClient(
        {
            1: _read("lubuskie_listing_p1.html"),
            2: _read("lubuskie_listing_p2.html"),
            3: _read("lubuskie_listing_old.html"),  # rok 2023 -> zatrzymaj
        }
    )
    rows = list(iter_declarations(client))
    # Strona 1: brak radnych -> 0
    # Strona 2: 3 radnych rok 2026
    # Strona 3: rok 2023 < MIN_YEAR -> koniec
    assert len(rows) == 3
    names = {n for n, _, _ in rows}
    assert "Wierchowicz Jerzy" in names
    assert "Wieczorek Andrzej" in names
    assert "Turczyniak Leszek" in names


def test_iter_declarations_rok_2024():
    # Strona 22 zawiera radnych 2024; strona 23 stara -> zatrzymanie
    client = _FakeClient(
        {
            22: _read("lubuskie_listing_p22.html"),
            23: _read("lubuskie_listing_old.html"),
        }
    )
    # Wymaga strony 22 jako start - ustaw fake zaczynajacy od strony 22
    # _FakeClient domyslnie rzuca dla strony 1 -> iter_declarations dostanie wyjatek na stronie 1
    # Pokryjmy to przez dodanie page=1 tez jako stara strone
    client._pages[1] = _read("lubuskie_listing_p22.html")
    client._pages[2] = _read("lubuskie_listing_old.html")

    client2 = _FakeClient(
        {
            1: _read("lubuskie_listing_p22.html"),
            2: _read("lubuskie_listing_old.html"),
        }
    )
    rows = list(iter_declarations(client2))
    assert len(rows) == 4
    years = {y for _, y, _ in rows}
    assert years == {2024}


def test_iter_declarations_dedup():
    # Ten sam radny na dwoch stronach (strona 1 i 2) -> tylko raz w wyniku
    client = _FakeClient(
        {
            1: _read("lubuskie_listing_p22.html"),  # Wierchowicz 2024
            2: _read("lubuskie_listing_p22.html"),  # duplikat tej samej strony
            3: _read("lubuskie_listing_old.html"),
        }
    )
    rows = list(iter_declarations(client))
    # Po deduplikacji (name, year) -> tylko 4 unikalne wpisy
    assert len(rows) == 4
    assert len({(n, y) for n, y, _ in rows}) == 4


def test_iter_declarations_tuple_format():
    # Kazda krotka to (name: str, year: int, pdf_url: str)
    client = _FakeClient(
        {
            1: _read("lubuskie_listing_p22.html"),
            2: _read("lubuskie_listing_old.html"),
        }
    )
    rows = list(iter_declarations(client))
    for name, year, url in rows:
        assert isinstance(name, str) and name
        assert isinstance(year, int) and year >= MIN_YEAR
        assert url.startswith("https://")
        assert "pobierz.php" in url


def test_iter_declarations_skip_on_http_error():
    # Strona 1 rzuca wyjatek -> pomijamy i idziemy dalej do strony 2
    class _ErrorOnFirstClient:
        def __init__(self, fallback_html):
            self._page = 0
            self._fallback = fallback_html

        def get(self, url):
            self._page += 1
            if self._page == 1:
                raise ConnectionError("timeout")
            if self._page == 2:
                return _FakeResp(self._fallback)
            return _FakeResp(_read("lubuskie_listing_old.html"))

    client = _ErrorOnFirstClient(_read("lubuskie_listing_p22.html"))
    rows = list(iter_declarations(client))
    assert len(rows) == 4
