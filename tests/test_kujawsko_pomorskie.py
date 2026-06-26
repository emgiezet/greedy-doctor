from pathlib import Path

from greedy_doctor.sources.kujawsko_pomorskie import (
    BASE,
    WYKAZ_PATH,
    iter_declarations,
    parse_listing,
    parse_pdf_url,
    parse_total_pages,
    surname_first,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- surname_first (czyste; tytul 'Imie Nazwisko - ...' -> odwracamy) ----------


def test_surname_first_reverses_given_name_first():
    # tytul z <strong> to 'Imie Nazwisko - tytul'
    assert surname_first("Zbigniew Ostrowski - oświadczenie radnego województwa za 2024 r.") == "Ostrowski Zbigniew"
    assert surname_first("Wojciech Jaranowski - oświadczenie radnego województwa za 2025 r.") == "Jaranowski Wojciech"


def test_surname_first_keeps_polish_diacritics():
    assert surname_first("Wojciech Szczęsny - oświadczenie radnego województwa za 2024 r.") == "Szczęsny Wojciech"
    assert surname_first("Paweł Zgórzyński - oświadczenie radnego województwa za 2025 r.") == "Zgórzyński Paweł"
    assert surname_first("Piotr Całbecki - oświadczenie majątkowe radnego województwa za 2025 r.") == "Całbecki Piotr"


def test_surname_first_two_word_surname():
    # imie = pierwszy token; reszta = nazwisko (dla nazwisk dwuczlonowych)
    assert surname_first("Katarzyna Stranz-Kaja - oświadczenie") == "Stranz-Kaja Katarzyna"
    assert surname_first("Anna Kowalska-Nowak - test") == "Kowalska-Nowak Anna"


def test_surname_first_handles_extra_whitespace():
    assert surname_first("  Jan   Maćkowiak  - coś") == "Maćkowiak Jan"


def test_surname_first_no_dash_separator():
    # gdy brak ' - ' bierzemy caly tekst i odwracamy
    assert surname_first("Jan Kowalski") == "Kowalski Jan"


# ---------- parse_total_pages (czyste; liczba stron z naglowka paginacji) ----------


def test_parse_total_pages_from_listing_2024():
    # fixture ma 260 wynikow => ceil(260/10) = 26 stron
    assert parse_total_pages(_read("kujawsko_pomorskie_listing_2024.html")) == 26


def test_parse_total_pages_from_listing_2025():
    # fixture ma 162 wyniki => ceil(162/10) = 17 stron
    assert parse_total_pages(_read("kujawsko_pomorskie_listing_2025.html")) == 17


def test_parse_total_pages_empty_returns_one():
    assert parse_total_pages("<html>brak paginacji</html>") == 1


# ---------- parse_listing (na zapisanym, realnym HTML strony listingu) ----------


def test_parse_listing_2024_keeps_radnych_skips_non_radnych():
    rows = parse_listing(_read("kujawsko_pomorskie_listing_2024.html"), 2024)
    names = [n for n, _, _ in rows]
    # fixture ma 5 pozycji: 1 oswiadczenie-majatkowe (non-radny Seroka) + 4 radnych
    assert len(rows) == 4
    assert len(set(names)) == 4
    assert all(y == 2024 for _, y, _ in rows)
    # Seroka (oswiadczenie-majatkowe bez 'radnego-wojewodztwa') odsiany
    assert not any("Seroka" in n for n in names)
    # radni sa: Ostrowski, Szczęsny, Jaranowski, Pogoda
    assert "Ostrowski Zbigniew" in names
    assert "Szczęsny Wojciech" in names
    assert "Jaranowski Wojciech" in names
    assert "Pogoda Tadeusz" in names


def test_parse_listing_2024_detail_urls_are_absolute():
    rows = parse_listing(_read("kujawsko_pomorskie_listing_2024.html"), 2024)
    assert all(u.startswith("https://bip.kujawsko-pomorskie.pl/") for _, _, u in rows)
    assert all(u.endswith(".html") for _, _, u in rows)


def test_parse_listing_2025_keeps_all_radnych_including_majatkowe_variant():
    rows = parse_listing(_read("kujawsko_pomorskie_listing_2025.html"), 2025)
    names = [n for n, _, _ in rows]
    # fixture: 5 pozycji, wszystkie radni (3 oswiadczenie-radnego + 1 majatkowe-radnego + 1 radnego)
    assert len(rows) == 5
    assert all(y == 2025 for _, y, _ in rows)
    # Całbecki w wariancie 'oswiadczenie-majatkowe-radnego-wojewodztwa' tez wchodzi
    assert "Całbecki Piotr" in names
    assert "Jaranowski Wojciech" in names
    assert "Zgórzyński Paweł" in names


def test_parse_listing_rejects_wrong_year():
    # strona 2025 nie powinna zwracac wynikow dla roku 2024
    rows = parse_listing(_read("kujawsko_pomorskie_listing_2025.html"), 2024)
    assert len(rows) == 0


def test_parse_listing_no_duplicates():
    rows_2024 = parse_listing(_read("kujawsko_pomorskie_listing_2024.html"), 2024)
    rows_2025 = parse_listing(_read("kujawsko_pomorskie_listing_2025.html"), 2025)
    assert len({(n, y) for n, y, _ in rows_2024}) == len(rows_2024)
    assert len({(n, y) for n, y, _ in rows_2025}) == len(rows_2025)


# ---------- parse_pdf_url (na zapisanym, realnym HTML strony szczegolowej) ----------


def test_parse_pdf_url_ostrowski_2024():
    url = parse_pdf_url(_read("kujawsko_pomorskie_detail_ostrowski.html"))
    assert url == (
        "https://bip.kujawsko-pomorskie.pl/download/attachment/68316/"
        "zbigniew-ostrowski-radny-wojewodztwa-oswiadczenie-majatkowe-za-2024-r.pdf"
    )


def test_parse_pdf_url_jaranowski_2025():
    url = parse_pdf_url(_read("kujawsko_pomorskie_detail_jaranowski.html"))
    assert url == (
        "https://bip.kujawsko-pomorskie.pl/download/attachment/89472/"
        "wojciech-jaranowski-radny-wojewodztwa-oswiadczenie-majatkowe-za-2025-r.pdf"
    )


def test_parse_pdf_url_calbecki_majatkowe_variant():
    url = parse_pdf_url(_read("kujawsko_pomorskie_detail_calbecki.html"))
    assert url == (
        "https://bip.kujawsko-pomorskie.pl/download/attachment/89445/"
        "piotr-calbecki-radny-wojewodztwa-oswiadczenie-majatkowe-za-2025-r.pdf"
    )


def test_parse_pdf_url_no_pdf_returns_none():
    assert parse_pdf_url("<html><body>brak zalacznika</body></html>") is None


# ---------- iter_declarations (stub httpx mapujacy URL -> fixture) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Minimalny stub httpx.Client: URL -> wczytany fixture HTML.

    Mapowanie:
    - listing 2024 strona 1: zwraca fixture listingu 2024 (jedyna strona w tescie)
    - listing 2025 strona 1: zwraca fixture listingu 2025 (jedyna strona w tescie)
    - strona szczegolowa radnego: mapowanie bezposrednie po URL
    Strony 2+ listingu (wg parse_total_pages z fixture: 26 dla 2024, 17 dla 2025)
    zwracaja pusty listing (brak wynikow) - to symuluje, ze radni sa tylko na str. 1.
    """

    def __init__(self, listing_by_year, detail_by_url):
        self._listing = listing_by_year  # {year: html}
        self._detail = detail_by_url     # {url: html}

    def get(self, url):
        # listing
        for year, page_html in self._listing.items():
            if f"t3_f37={year}" in url and "Page=1" in url:
                return _FakeResp(page_html)
        # strony 2+ listingu -> pusty listing
        if WYKAZ_PATH in url:
            return _FakeResp('<div class="paginationRow"><div class="totalResult">Liczba wyników: <b>0</b></div></div>')
        # strona szczegolowa
        if url in self._detail:
            return _FakeResp(self._detail[url])
        raise AssertionError(f"nieoczekiwany URL: {url}")


def _build_detail_map():
    """Mapowanie URL szczegolowych z fixture listingow -> HTML strony szczegolowej."""
    # Z fixture 2024: 4 radnych; przypisujemy im detail Ostrowskiego (wspolny fixture PDF)
    detail_map = {}
    listing_2024 = parse_listing(
        (FIX / "kujawsko_pomorskie_listing_2024.html").read_text(encoding="utf-8"), 2024
    )
    listing_2025 = parse_listing(
        (FIX / "kujawsko_pomorskie_listing_2025.html").read_text(encoding="utf-8"), 2025
    )
    ostrowski_html = (FIX / "kujawsko_pomorskie_detail_ostrowski.html").read_text(encoding="utf-8")
    jaranowski_html = (FIX / "kujawsko_pomorskie_detail_jaranowski.html").read_text(encoding="utf-8")
    calbecki_html = (FIX / "kujawsko_pomorskie_detail_calbecki.html").read_text(encoding="utf-8")
    for name, year, detail_url in listing_2024:
        detail_map[detail_url] = ostrowski_html
    for name, year, detail_url in listing_2025:
        if "calbecki" in detail_url:
            detail_map[detail_url] = calbecki_html
        elif "jaranowski" in detail_url:
            detail_map[detail_url] = jaranowski_html
        else:
            detail_map[detail_url] = jaranowski_html
    return detail_map


def test_iter_declarations_both_years_yields_tuples():
    client = _FakeClient(
        {
            2024: _read("kujawsko_pomorskie_listing_2024.html"),
            2025: _read("kujawsko_pomorskie_listing_2025.html"),
        },
        _build_detail_map(),
    )
    rows = list(iter_declarations(client))
    # 4 radnych za 2024 + 5 radnych za 2025 (z fixture stron listingow)
    assert len(rows) == 9
    years = sorted({y for _, y, _ in rows})
    assert years == [2024, 2025]
    # kazda trojka: (name, year, pdf_url)
    assert all(len(r) == 3 for r in rows)
    assert all(isinstance(n, str) and isinstance(y, int) and isinstance(u, str) for n, y, u in rows)
    # PDF URL-e do download/attachment
    assert all("/download/attachment/" in u and u.endswith(".pdf") for _, _, u in rows)


def test_iter_declarations_dedup_per_name_year():
    client = _FakeClient(
        {
            2024: _read("kujawsko_pomorskie_listing_2024.html"),
            2025: _read("kujawsko_pomorskie_listing_2025.html"),
        },
        _build_detail_map(),
    )
    rows = list(iter_declarations(client))
    keys = [(n, y) for n, y, _ in rows]
    assert len(keys) == len(set(keys)), "duplikaty (name, year)"


def test_iter_declarations_surname_first_format():
    client = _FakeClient(
        {2024: _read("kujawsko_pomorskie_listing_2024.html")},
        _build_detail_map(),
    )
    rows = list(iter_declarations(client))
    # nie surowa kolejnosc 'Imie Nazwisko'
    for name, _, _ in rows:
        assert name not in ("Zbigniew Ostrowski", "Wojciech Szczęsny", "Wojciech Jaranowski", "Tadeusz Pogoda")


def test_iter_declarations_skips_failed_year():
    """Rok, ktory nie jest opublikowany (HTTP error) -> cichy pominiecie."""

    class _ErrorClient:
        def get(self, url):
            if "t3_f37=2025" in url:
                raise ConnectionError("nie opublikowany")
            if "t3_f37=2024" in url and "Page=1" in url:
                return _FakeResp(_read("kujawsko_pomorskie_listing_2024.html"))
            if WYKAZ_PATH in url:
                return _FakeResp(
                    '<div class="paginationRow"><div class="totalResult">'
                    'Liczba wyników: <b>0</b></div></div>'
                )
            return _FakeResp(_read("kujawsko_pomorskie_detail_ostrowski.html"))

    rows = list(iter_declarations(_ErrorClient()))
    # tylko 2024 (4 radnych z fixture)
    assert len(rows) == 4
    assert all(y == 2024 for _, y, _ in rows)
