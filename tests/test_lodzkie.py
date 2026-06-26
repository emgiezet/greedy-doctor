from pathlib import Path

from greedy_doctor.sources.lodzkie import (
    BASE,
    LISTING_URL,
    MIN_ITEM_ID,
    iter_declarations,
    label_years,
    parse_item,
    parse_listing,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- parse_listing (pozycje K2: id + nazwa z tekstu kotwicy, nie ze sluga) ----------


def test_listing_page1_lists_current_councilors_surname_first():
    rows = parse_listing(_read("lodzkie_listing_p1.html"))
    # strona 1: 10 radnych biezacej kadencji (id 15134-15143)
    assert len(rows) == 10
    ids = {iid for iid, _, _ in rows}
    assert ids == set(range(15134, 15144))
    names = {n for _, n, _ in rows}
    # nazwa z TEKSTU kotwicy 'Nazwisko Imie - Oswiadczenia majatkowe' -> 'Nazwisko Imie';
    # polskie znaki zachowane, kolejnosc surname-first (kontrakt) — nie odwracamy
    assert "Zyberyng Konrad" in names
    assert "Ziółkowski Wojciech" in names
    assert "Więckowska Dorota" in names
    # zadna nazwa nie nosi sufiksu 'Oswiadczenia majatkowe'
    assert all("świadcz" not in n.lower() for n in names)
    # item_url absolutny, wskazuje na /item/{id}-...
    assert all(u.startswith(f"{BASE}/") and "/item/" in u for _, _, u in rows)


def test_listing_filters_stale_low_id_items_on_boundary_page():
    # strona graniczna (start=30): 3 pozycje biezace (15111-15113) wmieszane ze STARYMI
    # (9471,9472,9474,10549,14305,14306,14346) -> filtr id>=MIN_ITEM_ID musi zostawic 3
    rows = parse_listing(_read("lodzkie_listing_p4_boundary.html"))
    ids = {iid for iid, _, _ in rows}
    assert ids == {15111, 15112, 15113}
    assert all(iid >= MIN_ITEM_ID for iid, _, _ in rows)
    # stare pozycje odsiane
    assert 9471 not in ids and 14305 not in ids and 451 not in ids
    names = {n for _, n, _ in rows}
    assert "Adamczyk Piotr" in names  # id 15111


def test_listing_dedups_double_anchor_per_item():
    # kazda pozycja ma DWIE kotwice (tytul + 'czytaj wiecej' z sama ikona) -> jeden wiersz/id
    rows = parse_listing(_read("lodzkie_listing_p1.html"))
    ids = [iid for iid, _, _ in rows]
    assert len(ids) == len(set(ids))  # bez duplikatow id
    # i bez pustych nazw (kotwica 'czytaj wiecej' odrzucona)
    assert all(n for _, n, _ in rows)


# ---------- label_years (rok + typ z ETYKIETY linku, nie z nazwy pliku) ----------


def test_label_years_annual_single_year():
    assert label_years("Oświadczenie majątkowe za 2024 r.") == ({2024}, False)
    assert label_years("Oświadczenie majątkowe za 2025 r.") == ({2025}, False)


def test_label_years_snapshot_has_no_year():
    # 'na rozpoczecie kadencji' nie ma 'za YYYY' -> pusty zbior (zostanie pominiete)
    years, kor = label_years("Oświadczenie majątkowe na rozpoczęcie kadencji")
    assert years == set()
    assert kor is False


def test_label_years_korekta_with_year_flagged():
    # korekta rocznego -> rok + flaga korekty (preferowana dla (name, year))
    assert label_years("Korekta oświadczenia majątkowego za 2024 r.") == ({2024}, True)


def test_label_years_korekta_without_year_is_dropped():
    # korekta bez roku i korekta snapshotu -> brak lat (pomijane), ale flaga korekty=True
    assert label_years("Korekta oświadczenia majątkowego") == (set(), True)
    assert label_years("Korekta oświadczenia majątkowego na rozpoczęcie kadencji") == (
        set(),
        True,
    )
    assert label_years("Oświadczenie majątkowe korekta") == (set(), True)


def test_label_years_multi_year_and_missing_space_before_r():
    # jedna korekta na DWA lata, bez spacji przed 'r.' ('2024r.')
    years, kor = label_years("Korekta oświadczenia majątkowego za 2024r. i 2025r.")
    assert years == {2024, 2025}
    assert kor is True


# ---------- parse_item (strona osoby -> {year: pdf_url}; korekta wygrywa) ----------


def test_parse_item_clean_two_years_skips_snapshot():
    res = parse_item(_read("lodzkie_item_adamczyk.html"))
    assert set(res) == {2024, 2025}
    assert res[2024] == f"{BASE}/files/adamczyk.pdf"
    assert res[2025] == f"{BASE}/files/radni_roczne_2025/adamczyk-piotr---radny.pdf"
    # snapshot '/files/ADAMCZYK_P.pdf' (na rozpoczecie) NIE wchodzi
    assert all("ADAMCZYK_P" not in u for u in res.values())


def test_parse_item_korekta_wins_over_plain_annual_same_year():
    # Ciesielski: za 2024 r. (zwykle) ORAZ Korekta ... za 2024 r. -> zostaje KOREKTA
    res = parse_item(_read("lodzkie_item_ciesielski.html"))
    assert set(res) == {2024, 2025}
    assert res[2024] == f"{BASE}/files/CIESIELSKI_-_korekta_BIP.pdf"
    assert res[2024] != f"{BASE}/files/ciesielski.pdf"  # zwykle roczne ustepuje korekcie
    assert res[2025] == f"{BASE}/files/radni_roczne_2025/ciesielski-janusz---radny.pdf"


def test_parse_item_skips_snapshot_and_korekta_of_snapshot():
    # Zyberyng: 'Korekta ... na rozpoczecie' (korekta SNAPSHOTU, bez 'za YYYY') i sam snapshot
    # -> oba pominiete; zostaja tylko roczne 2024 i 2025
    res = parse_item(_read("lodzkie_item_zyberyng.html"))
    assert set(res) == {2024, 2025}
    assert res[2024] == f"{BASE}/files/zybering.pdf"  # literowka w nazwie pliku — nieistotna
    assert all("rozpocz" not in u.lower() and "ZYBERYNG_K" not in u for u in res.values())


def test_parse_item_empty_when_no_pdf():
    assert parse_item("<html><body>brak plikow</body></html>") == {}


# ---------- iter_declarations (stub httpx: listing(?start=N) + strony osob -> fixtures) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


# minimalna strona osoby z jednym rocznym PDF-em (dla radnych bez wlasnego fixture)
def _stub_item(slug, year=2024):
    return (
        f'<html><body><a href="/files/{slug}.pdf">'
        f"Oświadczenie majątkowe za {year} r.</a></body></html>"
    )


class _FakeClient:
    """Stub httpx.Client: URL listingu(?start=N) i strony /item/{id} -> fixture/HTML.

    Listing serwujemy jako 2 strony tresci + pusta trzecia, by udowodnic paginacje i
    zakonczenie petli (strona bez nowych id przerywa). Strony osob: 2 realne fixtury
    (Adamczyk 15111, Zyberyng 15143), reszta listowanych radnych to stuby z jednym
    rocznym PDF-em — wystarcza do policzenia (name, year).
    """

    def __init__(self):
        # listing: start=0 -> p1 (15134-15143), start=10 -> granica (15111-15113),
        # dowolny dalszy start -> pusto (koniec paginacji)
        self._listing = {
            0: _read("lodzkie_listing_p1.html"),
            10: _read("lodzkie_listing_p4_boundary.html"),
        }
        self._items = {
            15111: _read("lodzkie_item_adamczyk.html"),
            15143: _read("lodzkie_item_zyberyng.html"),
        }

    def get(self, url):
        if "/item/" in url:
            iid = int(url.split("/item/")[1].split("-")[0])
            if iid in self._items:
                return _FakeResp(self._items[iid])
            return _FakeResp(_stub_item(f"radny_{iid}"))
        # listing: wyciagnij start (brak -> 0)
        start = 0
        if "start=" in url:
            start = int(url.split("start=")[1].split("&")[0])
        return _FakeResp(self._listing.get(start, "<html><body></body></html>"))


def test_iter_declarations_paginates_filters_and_dedups():
    rows = list(iter_declarations(_FakeClient()))
    names = {n for n, _, _, _ in rows}
    # 13 radnych biezacej kadencji z 2 stron listingu (10 + 3); stare pozycje odsiane
    assert len(names) == 13
    # Adamczyk i Zyberyng (realne fixtury) maja po 2 lata; pozostali (stuby) po 1 roku
    assert len(rows) == 11 * 1 + 2 * 2  # 11 stubow x1 + 2 realne x2 = 15
    # klucz (name, year) unikalny — dedup dziala
    assert len({(n, y) for n, y, _, _ in rows}) == len(rows)
    # lata tylko z biezacej kadencji
    assert {y for _, y, _, _ in rows} <= {2024, 2025}


def test_iter_declarations_real_fixtures_two_years_each():
    rows = list(iter_declarations(_FakeClient()))
    by_name = {}
    for n, y, _, _ in rows:
        by_name.setdefault(n, set()).add(y)
    assert by_name["Adamczyk Piotr"] == {2024, 2025}
    assert by_name["Zyberyng Konrad"] == {2024, 2025}


def test_iter_declarations_absolute_pdf_and_landing_urls():
    rows = list(iter_declarations(_FakeClient()))
    # pdf_url absolutny pod /files/; landing_url to strona osoby /item/{id}
    assert all(u.startswith(f"{BASE}/files/") and u.endswith(".pdf") for _, _, u, _ in rows)
    assert all(land.startswith(f"{BASE}/") and "/item/" in land for _, _, _, land in rows)
    # konkretny radny: roczny 2024 Adamczyka to /files/adamczyk.pdf, landing to jego /item/
    adam = [r for r in rows if r[0] == "Adamczyk Piotr" and r[1] == 2024][0]
    assert adam[2] == f"{BASE}/files/adamczyk.pdf"
    assert adam[3].startswith(f"{BASE}/") and "/item/15111-" in adam[3]


def test_listing_url_is_category_18():
    # ponytail: kategoria K2 zahardcodowana = 18 (nowa kadencja -> nowe id)
    assert "/itemlist/category/18-" in LISTING_URL
