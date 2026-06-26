from pathlib import Path

from greedy_doctor.sources.warminsko_mazurskie import (
    BASE,
    VERIFY,
    YEAR_PAGES,
    iter_declarations,
    parse_link,
    parse_page,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- parse_link (czyste; odsiewa korekty, wyciaga rok z nazwy pliku) ----------


def test_parse_link_roczne_za_rok_format():
    # stary format: 'za_rok_2023' w nazwie pliku (sekcja radnych 2024)
    href = "/upload/files/oswiadczenia/zlozone_2024/Adamczyk_Edward_za_rok_2023.pdf"
    result = parse_link(href, "Adamczyk Edward")
    assert result == ("Adamczyk Edward", 2023, BASE + href)


def test_parse_link_roczne_za_format():
    # nowy format: 'za_2024' w nazwie pliku (sekcja radnych 2025)
    href = "/upload/files/oswiadczenia/zlozone_2025/Andruszkiewicz_Piotr_oswiadczenie_za_2024.pdf"
    result = parse_link(href, "Andruszkiewicz Piotr")
    assert result == ("Andruszkiewicz Piotr", 2024, BASE + href)


def test_parse_link_uppercase_ZA():
    # niespojnosc zrodla: '_ZA_2025' (wielkie litery) — regex case-insensitive
    href = "/upload/files/oswiadczenia/zlozone_2026/Homza_Zbigniew_o%C5%9Bwiadczenie_ZA_2025.pdf"
    result = parse_link(href, "Homza Zbigniew")
    assert result is not None
    assert result[1] == 2025
    assert result[0] == "Homza Zbigniew"


def test_parse_link_rejects_korekta_in_href():
    # korekta w nazwie pliku -> None
    href = "/upload/files/oswiadczenia/zlozone_2025/Kochan_Lukasz_oswiadczenie_za_2024_korekta.pdf"
    assert parse_link(href, "Kochan Łukasz - korekta") is None


def test_parse_link_rejects_no_za_year():
    # plik bez 'za_YYYY' w nazwie (np. snapshot koniec kadencji) -> None
    href = "/upload/files/oswiadczenia/zlozone_2024/Adamczyk_Edward_koniec_kadencji_2024.pdf"
    assert parse_link(href, "Adamczyk Edward") is None


def test_parse_link_rejects_pocz_kadencji():
    href = "/upload/files/oswiadczenia/zlozone_2024/Bartnicki_Bogdan_pocz.kadencji_2024.pdf"
    assert parse_link(href, "Bartnicki Bogdan") is None


def test_parse_link_strips_dash_suffix_from_anchor():
    # tekst kotwicy moze niesc ' - oświadczenie za 2024 rok' — bierzemy czesc przed ' - '
    href = "/upload/files/oswiadczenia/zlozone_2025/Bartnicki_Bogdan_oswiadczenie_za_2024.pdf"
    result = parse_link(href, "Bartnicki Bogdan - oświadczenie za 2024 rok")
    assert result is not None
    assert result[0] == "Bartnicki Bogdan"


def test_parse_link_polish_diacritics_preserved():
    href = "/upload/files/oswiadczenia/zlozone_2024/Kluge_Grazyna_za_rok_2023.pdf"
    result = parse_link(href, "Kluge Grażyna")
    assert result is not None
    assert result[0] == "Kluge Grażyna"


def test_parse_link_html_entity_in_anchor():
    # encja HTML w tekscie kotwicy (np. Kr&oacute;lak -> Królak)
    href = "/upload/files/oswiadczenia/zlozone_2024/Krolak_Katarzyna_za_rok_2023.pdf"
    result = parse_link(href, "Kr&oacute;lak Katarzyna")
    assert result is not None
    assert result[0] == "Królak Katarzyna"


# ---------- parse_page (na zapisanym, realnym HTML strony rocznej) ----------


def test_parse_page_2024_keeps_radni_annual_only():
    rows = parse_page(_read("warminsko_mazurskie_2024.html"))
    # fixture: sekcja Radni za rok 2023 ma 6 wpisow; Czlonkowie Zarzadu, koniec_kadencji,
    # pocz.kadencji, Dyrektorzy wykluczone
    assert len(rows) == 6
    names = [n for n, _, _ in rows]
    assert all(y == 2023 for _, y, _ in rows)
    # Czlonek Zarzadu z sekcji 'Czlonkowie Zarzadu' nie wchodzi
    assert "Bartnicki Bogdan" not in names
    # Dyrektorzy nie wchodza
    assert "Bojarski Marek" not in names
    # Snapshot 'koniec kadencji' nie wchodzi
    assert "Adamczyk Edward" in names  # roczny 2023 jest
    # polskie znaki z anchor
    assert "Kluge Grażyna" in names
    assert "Żelichowski Stanisław" in names
    assert "Królak Katarzyna" in names
    # URL absolutny, PDF z /upload/
    assert all(u.startswith(BASE + "/upload/files/oswiadczenia/") for _, _, u in rows)
    assert all(u.endswith(".pdf") for _, _, u in rows)


def test_parse_page_2024_no_snapshots():
    rows = parse_page(_read("warminsko_mazurskie_2024.html"))
    urls = {u for _, _, u in rows}
    assert all("koniec_kadencji" not in u for u in urls)
    assert all("pocz.kadencji" not in u for u in urls)
    assert all("korekta" not in u.lower() for u in urls)


def test_parse_page_2025_keeps_radni_za_2024():
    rows = parse_page(_read("warminsko_mazurskie_2025.html"))
    # fixture: Radni za rok 2024 ma 7 linkow, z czego 1 korekta -> 6 rocznych (Kochan raz)
    assert len(rows) == 6
    assert all(y == 2024 for _, y, _ in rows)
    names = [n for n, _, _ in rows]
    # Kochan jest raz (korekta odsiana)
    assert names.count("Kochan Łukasz") == 1
    # polskie znaki
    assert "Bąkowska Maria" in names
    assert "Kozłowski Patryk" in names
    # Dyrektorzy i Zarzad wykluczone
    assert "Bojarski Marek" not in names


def test_parse_page_2025_korekta_does_not_shadow_real():
    rows = parse_page(_read("warminsko_mazurskie_2025.html"))
    kochan = [r for r in rows if r[0] == "Kochan Łukasz"]
    assert len(kochan) == 1
    assert kochan[0][1] == 2024
    assert "korekta" not in kochan[0][2].lower()


def test_parse_page_2026_keeps_radni_za_2025():
    rows = parse_page(_read("warminsko_mazurskie_2026.html"))
    # fixture: 2 wpisy radnych za 2025 (Bartnicki + Homza ZA)
    assert len(rows) == 2
    assert all(y == 2025 for _, y, _ in rows)
    names = {n for n, _, _ in rows}
    assert "Bartnicki Bogdan" in names
    assert "Homza Zbigniew" in names


def test_parse_page_no_dyrektorzy():
    # zadna ze stron nie powinna przynosic Dyrektorow ani Prezesow
    for fname in ("warminsko_mazurskie_2024.html", "warminsko_mazurskie_2025.html", "warminsko_mazurskie_2026.html"):
        rows = parse_page(_read(fname))
        names = {n for n, _, _ in rows}
        assert "Bojarski Marek" not in names, fname
        assert "Borkowska Marioletta" not in names, fname


# ---------- iter_declarations (stub httpx mapujacy URL strony rocznej -> fixture) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Minimalny stub httpx.Client: /N/ -> fixture HTML po id strony.

    Mapujemy po id (liczba w URL) z YEAR_PAGES — niezaleznie od ewentualnego slugu."""

    def __init__(self, by_page_id):
        self._by_id = by_page_id  # {id(int): html}

    def get(self, url):
        for page_id, page in self._by_id.items():
            if f"/{page_id}/" in url or url.endswith(f"/{page_id}/"):
                return _FakeResp(page)
        raise AssertionError(f"nieoczekiwany URL: {url}")


def test_iter_declarations_all_years_dedup_per_name_year():
    client = _FakeClient(
        {
            YEAR_PAGES[2024]: _read("warminsko_mazurskie_2024.html"),
            YEAR_PAGES[2025]: _read("warminsko_mazurskie_2025.html"),
            YEAR_PAGES[2026]: _read("warminsko_mazurskie_2026.html"),
        }
    )
    rows = list(iter_declarations(client))
    # 6 radnych za 2023 (strona 2024) + 6 radnych za 2024 (strona 2025) + 2 radnych za 2025
    assert len(rows) == 14
    years = sorted({y for _, y, _ in rows})
    assert years == [2023, 2024, 2025]
    # klucz (name, year) unikalny
    assert len({(n, y) for n, y, _ in rows}) == 14
    # wszystkie URL-e do /upload/ i kończą sie '.pdf'
    assert all(u.startswith(BASE + "/upload/files/oswiadczenia/") for _, _, u in rows)
    assert all(u.endswith(".pdf") for _, _, u in rows)


def test_iter_declarations_yields_3_tuples():
    client = _FakeClient({YEAR_PAGES[2024]: _read("warminsko_mazurskie_2024.html")})
    rows = list(iter_declarations(client))
    assert all(len(r) == 3 for r in rows)


def test_iter_declarations_skip_on_fetch_error():
    # strona 2025 rzuca wyjatek -> pomijamy, wracamy 2024 + 2026 tylko
    class _ErrorClient:
        def get(self, url):
            if f"/{YEAR_PAGES[2025]}/" in url:
                raise ConnectionError("timeout")
            page_id = YEAR_PAGES[2024] if f"/{YEAR_PAGES[2024]}/" in url else YEAR_PAGES[2026]
            fname = {YEAR_PAGES[2024]: "warminsko_mazurskie_2024.html", YEAR_PAGES[2026]: "warminsko_mazurskie_2026.html"}[page_id]
            return _FakeResp(_read(fname))

    rows = list(iter_declarations(_ErrorClient()))
    years = sorted({y for _, y, _ in rows})
    # 2025 pominiety, zostaly 2023 (ze strony 2024) i 2025 (ze strony 2026)
    assert 2024 not in years  # rok dochodowy 2024 pochodzi ze strony 2025 ktora fail
    assert len(rows) > 0


def test_iter_declarations_dedup_across_pages():
    # ten sam radny w dwoch stronach — dedup per (name, year)
    double_html = _read("warminsko_mazurskie_2024.html")
    client = _FakeClient(
        {
            YEAR_PAGES[2024]: double_html,
            YEAR_PAGES[2025]: double_html,  # ta sama zawartosc (rok 2023) dla obu stron
            YEAR_PAGES[2026]: double_html,
        }
    )
    rows = list(iter_declarations(client))
    # (name, year) unikalny mimo ze ta sama strona serwuje te same dane dla wszystkich klientow
    assert len({(n, y) for n, y, _ in rows}) == len(rows)


def test_verify_is_false():
    # BIP ma zepsuty lancuch TLS — VERIFY = False wymagane
    assert VERIFY is False
