from pathlib import Path

from greedy_doctor.sources.swietokrzyskie import (
    BASE,
    YEAR_ARTICLES,
    iter_declarations,
    parse_article,
    parse_link,
    surname_first,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- surname_first (czyste; kotwica to 'IMIE NAZWISKO' -> odwracamy) ----------


def test_surname_first_reverses_given_name_first():
    # zrodlo podaje 'Imie Nazwisko' (imie PIERWSZE) -> kontrakt wymaga 'Nazwisko Imie'
    assert surname_first("Andrzej Mochon") == "Mochon Andrzej"
    assert surname_first("Anita Koniusz") == "Koniusz Anita"


def test_surname_first_keeps_polish_diacritics():
    # bierzemy widoczny tekst kotwicy (z polskimi znakami), nie slug ASCII
    assert surname_first("Arkadiusz Bąk") == "Bąk Arkadiusz"
    assert surname_first("Andrzej Pruś") == "Pruś Andrzej"
    assert surname_first("Magdalena Zieleń") == "Zieleń Magdalena"


def test_surname_first_two_word_surname_keeps_surname_together():
    # imie = pierwszy token; reszta to nazwisko (gdyby bylo dwuczlonowe ze spacja)
    assert surname_first("Anna Kowalska Nowak") == "Kowalska Nowak Anna"


def test_surname_first_handles_extra_whitespace():
    assert surname_first("  Jan   Maćkowiak  ") == "Maćkowiak Jan"


# ---------- parse_link (czyste; odsiewa korekty, odwraca nazwe) ----------


def test_parse_link_normal_entry():
    href = (
        "/download/107104-andrzej-mochon/1305-vii-kadencja-lata-2024-2029/"
        "14712-oswiadczenia-majatkowe-radnych-wojewodztwa-swietokrzyskiego-zlozone-za-2024-rok.html"
    )
    assert parse_link(href, "Andrzej Mochoń") == ("Mochoń Andrzej", BASE + href)


def test_parse_link_rejects_korekta_in_title():
    # korekta ma w tytule slowo 'korekta' w roznych wariantach (spacja / '_' / ' - ')
    href = "/download/107963-anita-koniusz-korekta/1305-x/14712-x.html"
    assert parse_link(href, "Anita Koniusz Korekta") is None
    assert parse_link(href, "Grzegorz Socha_korekta") is None
    assert parse_link(href, "Grzegorz Cepil - korekta") is None


def test_parse_link_rejects_korekta_in_slug_even_if_title_clean():
    # gdyby tytul nie zawieral 'korekta', slug z '-korekta' i tak odrzuca
    href = "/download/109498-gerard-pedrycz-korekta/1305-x/14712-x.html"
    assert parse_link(href, "Gerard Pedrycz") is None


# ---------- parse_article (na zapisanym, realnym HTML artykulu rocznego) ----------


def test_parse_article_2024_keeps_annual_skips_korekta():
    rows = parse_article(_read("swietokrzyskie_2024.html"), 2024)
    names = [n for n, _, _ in rows]
    # fixture: 6 linkow download, z czego 1 korekta -> 5 rocznych
    assert len(rows) == 5
    assert len(set(names)) == 5  # bez duplikatow
    assert all(y == 2024 for _, y, _ in rows)
    # przyklad: nazwa odwrocona 'Imie Nazwisko' -> 'Nazwisko Imie', URL absolutny .html
    sample_href = (
        f"{BASE}/download/107104-andrzej-mochon/1305-vii-kadencja-lata-2024-2029/"
        "14712-oswiadczenia-majatkowe-radnych-wojewodztwa-swietokrzyskiego-zlozone-za-2024-rok.html"
    )
    assert ("Mochoń Andrzej", 2024, sample_href) in rows
    # korekta odsiana: realna 'Koniusz Anita' zostaje, ale wpisu 'Korekta' nie ma
    assert "Koniusz Anita" in names
    assert all("korekt" not in u.lower() for _, _, u in rows)
    assert all("Korekta" not in n for n in names)
    # wszystkie URL-e absolutne do /download/ i koncza sie '.html' (Phoca serwuje PDF z .html)
    assert all(u.startswith(f"{BASE}/download/") and u.endswith(".html") for _, _, u in rows)


def test_parse_article_2024_korekta_does_not_shadow_real_declaration():
    # 'Anita Koniusz' i 'Anita Koniusz Korekta' sa obok siebie; po pominieciu korekty
    # realny wpis Koniusz nadal jest dokladnie raz (korekta nie tworzy duplikatu po skróceniu)
    rows = parse_article(_read("swietokrzyskie_2024.html"), 2024)
    koniusz = [r for r in rows if r[0] == "Koniusz Anita"]
    assert len(koniusz) == 1


def test_parse_article_2025_skips_korekta_variant_with_underscore():
    rows = parse_article(_read("swietokrzyskie_2025.html"), 2025)
    names = {n for n, _, _ in rows}
    # 6 linkow, 1 korekta ('Grzegorz Socha_korekta') -> 5 rocznych
    assert len(rows) == 5
    assert "Socha Grzegorz" in names
    assert all(y == 2025 for _, y, _ in rows)
    assert all("korekt" not in u.lower() for _, _, u in rows)


# ---------- iter_declarations (stub httpx mapujacy URL artykulu rocznego -> fixture) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Minimalny stub httpx.Client: URL artykulu rocznego -> wczytany fixture HTML.

    Mapujemy po id artykulu (14712/16008) wystepujacym w URL — niezaleznie od reszty sciezki.
    """

    def __init__(self, by_article_id):
        self._by_id = by_article_id  # {id(int): html}

    def get(self, url):
        for art_id, page in self._by_id.items():
            if f"{art_id}-" in url:
                return _FakeResp(page)
        raise AssertionError(f"nieoczekiwany URL: {url}")


def test_iter_declarations_both_years_dedup_per_name_year():
    client = _FakeClient(
        {
            YEAR_ARTICLES[2024]: _read("swietokrzyskie_2024.html"),
            YEAR_ARTICLES[2025]: _read("swietokrzyskie_2025.html"),
        }
    )
    rows = list(iter_declarations(client))
    # 5 rocznych za 2024 + 5 za 2025 (korekty odsiane w obu)
    assert len(rows) == 10
    years = sorted({y for _, y, _ in rows})
    assert years == [2024, 2025]
    # klucz (name, year) unikalny — jedno roczne na (radny, rok)
    assert len({(n, y) for n, y, _ in rows}) == 10
    # ten sam radny pojawia sie w obu latach jako spojne 'Nazwisko Imie'
    mochon = sorted(y for n, y, _ in rows if n == "Mochoń Andrzej")
    assert mochon == [2024, 2025]
    # tuple to dokladnie 3 elementy (name, year, pdf_url) — bez landing_url
    assert all(len(r) == 3 for r in rows)
    assert all(u.startswith(f"{BASE}/download/") and u.endswith(".html") for _, _, u in rows)


def test_iter_declarations_yields_three_tuples_surname_first():
    client = _FakeClient({YEAR_ARTICLES[2024]: _read("swietokrzyskie_2024.html")})
    rows = list(iter_declarations(client))
    # 'Imie Nazwisko' z kotwicy zostalo odwrocone -> pierwszy token to nazwisko
    for name, _year, _url in rows:
        assert name not in ("Andrzej Mochoń", "Anita Koniusz")  # nie surowa kolejnosc
