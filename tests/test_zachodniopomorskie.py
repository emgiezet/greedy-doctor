from pathlib import Path

from greedy_doctor.sources.zachodniopomorskie import (
    BASE,
    YEAR_NODES,
    _normalize_name,
    iter_declarations,
    parse_detail,
    parse_listing,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- _normalize_name (czyste; normalizacja przed dedup) ----------


def test_normalize_name_trims_whitespace():
    # na listingu zdarzaja sie trailing spaces np. 'Niedzielski Andrzej '
    assert _normalize_name("Niedzielski Andrzej ") == "Niedzielski Andrzej"


def test_normalize_name_strips_korekta_suffix():
    assert _normalize_name("Geblewicz Olgierd korekta") == "Geblewicz Olgierd"
    assert _normalize_name("Geblewicz Olgierd Korekta") == "Geblewicz Olgierd"


def test_normalize_name_normalizes_hyphen_spacing():
    # 2024: 'Holub - Kowalik Malgorzata' -> bez spacji wokol myslnika
    assert _normalize_name("Hołub - Kowalik Małgorzata") == "Hołub-Kowalik Małgorzata"
    # 2025: 'Kolodziejska- Motyl Krystyna' -> tez normalizujemy
    assert _normalize_name("Kołodziejska- Motyl Krystyna") == "Kołodziejska-Motyl Krystyna"


def test_normalize_name_plain_name_unchanged():
    assert _normalize_name("Smoleńska Beata") == "Smoleńska Beata"
    assert _normalize_name("Nieckarz Krzysztof") == "Nieckarz Krzysztof"


# ---------- parse_listing (na realnym fixture listingu) ----------


def test_parse_listing_2024_counts_entries():
    rows = parse_listing(_read("zachodniopomorskie_listing_2024.html"))
    # fixture: 7 wierszy (6 unikalnych osob + 1 korekta dla Geblewicza)
    assert len(rows) == 7


def test_parse_listing_2024_detects_korekta_flag():
    rows = parse_listing(_read("zachodniopomorskie_listing_2024.html"))
    by_name = {name: (url, is_k) for name, url, is_k in rows}
    # Geblewicz wystepuje dwa razy: zwykly (is_korekta=False) i korekta (is_korekta=True)
    geblewicz_entries = [(n, k) for n, u, k in rows if n == "Geblewicz Olgierd"]
    assert len(geblewicz_entries) == 2
    flags = {k for _, k in geblewicz_entries}
    assert flags == {True, False}


def test_parse_listing_2024_normalizes_hyphenated_name():
    rows = parse_listing(_read("zachodniopomorskie_listing_2024.html"))
    names = [n for n, _, _ in rows]
    # 'Holub - Kowalik' -> 'Holub-Kowalik' (bez spacji wokol myslnika)
    assert "Hołub-Kowalik Małgorzata" in names
    assert "Hołub - Kowalik Małgorzata" not in names


def test_parse_listing_2024_strips_trailing_space():
    rows = parse_listing(_read("zachodniopomorskie_listing_2024.html"))
    names = [n for n, _, _ in rows]
    assert "Niedzielski Andrzej" in names
    assert "Niedzielski Andrzej " not in names


def test_parse_listing_2024_urls_are_absolute():
    rows = parse_listing(_read("zachodniopomorskie_listing_2024.html"))
    for _name, url, _is_k in rows:
        assert url.startswith(BASE + "/artykul/")


def test_parse_listing_2025_no_korekta():
    rows = parse_listing(_read("zachodniopomorskie_listing_2025.html"))
    assert all(not is_k for _, _, is_k in rows)
    assert len(rows) == 5


def test_parse_listing_2025_normalizes_hyphen_variant():
    rows = parse_listing(_read("zachodniopomorskie_listing_2025.html"))
    names = [n for n, _, _ in rows]
    # 2025: 'Kolodziejska- Motyl' (bez spacji przed '-') -> tez normalizujemy
    assert "Kołodziejska-Motyl Krystyna" in names


# ---------- parse_detail (na realnych fixture stron osoby) ----------


def test_parse_detail_nieckarz_returns_pdf_url():
    url = parse_detail(_read("zachodniopomorskie_detail_nieckarz.html"))
    assert url == "https://www.bip.wzp.pl/sites/bip.wzp.pl/files/articles/krzysztofnieckarz.pdf"


def test_parse_detail_geblewicz_korekta_returns_korekta_url():
    url = parse_detail(_read("zachodniopomorskie_detail_geblewicz_korekta.html"))
    assert url == (
        "https://www.bip.wzp.pl/sites/bip.wzp.pl/files/articles/olgierdgeblewiczkorekta_2.pdf"
    )


def test_parse_detail_holub_kowalik_returns_pdf_url():
    url = parse_detail(_read("zachodniopomorskie_detail_holub_kowalik.html"))
    assert url == (
        "https://www.bip.wzp.pl/sites/bip.wzp.pl/files/articles/malgorzataholub-kowalik.pdf"
    )


def test_parse_detail_returns_none_when_no_pdf():
    assert parse_detail("<html><body>brak pliku</body></html>") is None


# ---------- iter_declarations (stub klienta HTTP) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Minimalny stub httpx.Client: URL -> fixture HTML.

    Mapuje:
    - URL tabeli listingu (/tabela/artykuly/748/{node}) -> fixture listingu
    - URL artykulu osoby (/artykul/{slug}) -> fixture strony osoby
    """

    def __init__(self, responses):
        self._responses = responses  # {url_fragment: html}

    def get(self, url):
        for fragment, html in self._responses.items():
            if fragment in url:
                return _FakeResp(html)
        raise AssertionError(f"nieoczekiwany URL w tescie: {url}")


def _make_client_2024():
    """Klient pokrywajacy listing 2024 + strony 7 osob (6 + korekta Geblewicza)."""
    detail_nieckarz = _read("zachodniopomorskie_detail_nieckarz.html")
    detail_korekta = _read("zachodniopomorskie_detail_geblewicz_korekta.html")
    detail_holub = _read("zachodniopomorskie_detail_holub_kowalik.html")
    # Minimalny detail dla pozostalych osob (Smolenska, Niedzielski, Kolodziejska)
    _minimal = lambda fn: (  # noqa: E731
        '<div class="field field-name-field-plik">'
        f'<a href="https://www.bip.wzp.pl/sites/bip.wzp.pl/files/articles/{fn}.pdf">{fn}</a>'
        "</div>"
    )
    return _FakeClient(
        {
            f"/tabela/artykuly/748/{YEAR_NODES[2024]}": _read(
                "zachodniopomorskie_listing_2024.html"
            ),
            "/artykul/nieckarz-krzysztof-13": detail_nieckarz,
            "/artykul/geblewicz-olgierd-korekta-2": detail_korekta,
            "/artykul/holub-kowalik-malgorzata-0": detail_holub,
            "/artykul/niedzielski-andrzej-20": _minimal("niedzielskiandrzej"),
            "/artykul/smolenska-beata-0": _minimal("smolenskabeata"),
            "/artykul/kolodziejska-motyl-krystyna-10": _minimal("kolodziejskamotyl"),
        }
    )


def test_iter_declarations_2024_yields_6_unique_persons():
    """Geblewicz korekta i zwykly -> jeden wynik; razem 6 unikalnych (name, year) par."""
    client = _make_client_2024()
    rows = list(iter_declarations(client))
    assert len(rows) == 6
    names = [n for n, _, _ in rows]
    assert len(set(names)) == 6
    assert all(y == 2024 for _, y, _ in rows)


def test_iter_declarations_2024_prefers_korekta_for_geblewicz():
    client = _make_client_2024()
    rows = list(iter_declarations(client))
    geblewicz = [r for r in rows if r[0] == "Geblewicz Olgierd"]
    assert len(geblewicz) == 1
    _name, _year, pdf_url = geblewicz[0]
    # Musi byc URL z artykulu korekty, nie zwyklego
    assert "korekta" in pdf_url.lower()


def test_iter_declarations_2024_normalizes_hyphenated_name():
    client = _make_client_2024()
    rows = list(iter_declarations(client))
    names = {n for n, _, _ in rows}
    assert "Hołub-Kowalik Małgorzata" in names


def test_iter_declarations_tuples_are_three_elements():
    client = _make_client_2024()
    for row in iter_declarations(client):
        assert len(row) == 3
        name, year, pdf_url = row
        assert isinstance(name, str) and name
        assert year == 2024
        assert pdf_url.startswith("https://") and pdf_url.endswith(".pdf")


def test_iter_declarations_dedup_per_name_year():
    """Dedup: (name, year) moze wystapic co najwyzej raz w generatorze."""
    client = _make_client_2024()
    rows = list(iter_declarations(client))
    pairs = [(n, y) for n, y, _ in rows]
    assert len(pairs) == len(set(pairs))


def test_iter_declarations_both_years():
    """Oba lata lacznie daja spojne name miedzy rocznikami."""
    detail_nieckarz = _read("zachodniopomorskie_detail_nieckarz.html")
    detail_holub = _read("zachodniopomorskie_detail_holub_kowalik.html")
    _minimal = lambda fn: (  # noqa: E731
        '<div class="field field-name-field-plik">'
        f'<a href="https://www.bip.wzp.pl/sites/bip.wzp.pl/files/articles/{fn}.pdf">{fn}</a>'
        "</div>"
    )
    client = _FakeClient(
        {
            f"/tabela/artykuly/748/{YEAR_NODES[2024]}": _read(
                "zachodniopomorskie_listing_2024.html"
            ),
            f"/tabela/artykuly/748/{YEAR_NODES[2025]}": _read(
                "zachodniopomorskie_listing_2025.html"
            ),
            "/artykul/nieckarz-krzysztof-13": detail_nieckarz,
            "/artykul/nieckarz-krzysztof-14": detail_nieckarz,
            "/artykul/geblewicz-olgierd-korekta-2": _minimal("geblewiczkorekta"),
            "/artykul/geblewicz-olgierd-22": _minimal("geblewicz2025"),
            "/artykul/holub-kowalik-malgorzata-0": detail_holub,
            "/artykul/holub-kowalik-malgorzata-1": detail_holub,
            "/artykul/niedzielski-andrzej-20": _minimal("niedzielski"),
            "/artykul/smolenska-beata-0": _minimal("smolenska"),
            "/artykul/smolenska-beata-1": _minimal("smolenska2025"),
            "/artykul/kolodziejska-motyl-krystyna-10": _minimal("kolodziejska"),
            "/artykul/kolodziejska-motyl-krystyna-11": _minimal("kolodziejska2025"),
        }
    )
    rows = list(iter_declarations(client))
    years = sorted({y for _, y, _ in rows})
    assert years == [2024, 2025]
    # Nieckarz pojawia sie w obu latach ze spojnym name
    nieckarz = sorted(y for n, y, _ in rows if n == "Nieckarz Krzysztof")
    assert nieckarz == [2024, 2025]
    # (name, year) unikalny
    pairs = [(n, y) for n, y, _ in rows]
    assert len(pairs) == len(set(pairs))
