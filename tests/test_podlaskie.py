from pathlib import Path

import greedy_doctor.sources.podlaskie as mod
from greedy_doctor.sources.podlaskie import (
    BASE,
    LISTING_URL,
    annual_year,
    iter_declarations,
    parse_docs,
    parse_listing,
    parse_pdf_url,
    parse_year_links,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------- parse_listing (title= obecny i juz 'Nazwisko Imie', jak Slaski) ----------


def test_listing_lists_officials_surname_first():
    rows = parse_listing(_read("podlaskie_listing_p1.html"))
    assert len(rows) == 25  # 25 osob na stronie listingu (mieszane: radni + urzednicy)
    names = {n for n, _ in rows}
    # title= jest juz 'Nazwisko Imie' (kontrakt / jak Slaski) — nie odwracamy; PL znaki cale
    assert "Aleksiejuk Leon" in names
    assert "Augustyn Anna" in names
    assert "Bobrowska-Dąbrowska Krystyna" in names  # nazwisko dwuczlonowe
    assert "Bielecka Bożena Violetta" in names  # dwa imiona
    # kazdy link to bezstanowy deep-link osoby ?p=Nazwisko@Imie (bez '^' roku), absolutny
    assert all(u.startswith(LISTING_URL + "?p=") for _, u in rows)
    assert all("%40" in u and "%5E" not in u for _, u in rows)


def test_listing_page5_contains_test_people():
    rows = dict((n, u) for n, u in parse_listing(_read("podlaskie_listing_p5.html")))
    # osoby, dla ktorych mamy pelne lancuchy fixtur (integracja nizej)
    assert rows["Olbryś Marek"].endswith("?p=Olbry%C5%9B%40Marek")
    assert rows["Prokorym Łukasz"].endswith("?p=Prokorym%40%C5%81ukasz")


# ---------- parse_year_links (jak Slaski; rok = numer wezla/rok zlozenia) ----------


def test_year_links_keeps_current_term_only():
    rows = parse_year_links(_read("podlaskie_olbrys_landing.html"))
    years = {y for y, _ in rows}
    assert years == {2024, 2025}  # archiwum 2020-2023 odsiane przez MIN_YEAR
    # url roku to deep-link ?p=...%5E2025, absolutny
    url_2025 = dict(rows)[2025]
    assert url_2025.startswith(LISTING_URL + "?p=")
    assert "%5E2025" in url_2025


def test_year_links_future_node_kept():
    # Prokorym ma wezel ^2026 (za 2025 r. lezy pod ^2026) -> MIN_YEAR=2024 go przepuszcza,
    # wiec przyszle roczniki wejda automatycznie.
    rows = parse_year_links(_read("podlaskie_prokorym_landing.html"))
    assert {y for y, _ in rows} == {2024, 2025, 2026}


# ---------- parse_docs (paruje link dokumentu z 'Okolicznosci zlozenia') ----------


def test_parse_docs_pairs_link_with_okolicznosci():
    docs = dict(parse_docs(_read("podlaskie_olbrys_2025.html")))
    # wezel ^2025 ma jeden dokument: roczne za 2024 r.
    assert len(docs) == 1
    (url, okol), = docs.items()
    assert url == (
        f"{BASE}/wojewodztwo/oswiadczenia/oswiadczenia_majatkowe_od_2009/"
        "oswiadczenie-majatkowe-marek-olbrys-27.html"
    )
    assert okol == "Oświadczenie majątkowe radnego województwa za 2024 rok"


def test_parse_docs_ignores_menu_noise():
    # strona roku ma w menu 'klauzula-informacyjna.html' i 'formul_oswiad_do_pobran.html'
    # — to NIE dokumenty (slug != 'oswiadczenie-majatkowe-'), parser ich nie bierze.
    docs = parse_docs(_read("podlaskie_olbrys_2025.html"))
    urls = {u for u, _ in docs}
    assert all("oswiadczenie-majatkowe-" in u.rsplit("/", 1)[-1] for u in urls)
    assert not any("klauzula-informacyjna" in u for u in urls)
    assert not any("formul_oswiad_do_pobran" in u for u in urls)


def test_parse_docs_multiple_on_snapshot_node():
    # wezel ^2024 Olbrysia miesza 5 typow (snapshoty + resztka VI kadencji 'za 2023 rok')
    docs = parse_docs(_read("podlaskie_olbrys_2024.html"))
    assert len(docs) == 5


# ---------- annual_year (rok FISKALNY z tytulu + filtr typu/korekty/urzednikow) ----------


def test_annual_year_extracts_fiscal_year_from_title():
    assert annual_year("Oświadczenie majątkowe radnego województwa za 2024 rok") == 2024
    # wariant zenski i funkcyjny (radna / Przewodniczacy) — tez radni sejmiku
    assert annual_year("Oświadczenie majątkowe radnej województwa za 2024 rok") == 2024
    assert (
        annual_year(
            "Oświadczenie majątkowe Przewodniczącego Sejmiku Województwa Podlaskiego za 2024 rok"
        )
        == 2024
    )
    # rok przyszly (za 2025) tez sie zlapie -> przyszle roczniki wchodza automatem
    assert (
        annual_year("Oświadczenie majątkowe radnego województwa podlaskiego za 2025 rok")
        == 2025
    )


def test_annual_year_rejects_korekta_even_with_year():
    # korekta NIESIE 'za 2024 rok' -> filtr 'korekt' musi wygrac (jak w Slaskim)
    assert annual_year("Oświadczenie majątkowe radnego województwa za 2024 rok- korekta") is None
    assert annual_year("korekta oświadczenia majątkowego") is None
    assert annual_year("Korekta oświadczenia majątkowego") is None


def test_annual_year_rejects_snapshots_and_generic():
    # snapshoty i generyczne 'oswiadczenie majatkowe roczne' (dyrektorzy ZOZ) nie maja
    # 'za YYYY rok' -> None (filtr radnych sejmiku jako efekt uboczny)
    assert annual_year("oświadczenie majątkowe roczne") is None
    assert (
        annual_year(
            "Oświadczenie majątkowe radnego województwa złożone po objęciu mandatu "
            "w kadencji 2024-2029 – Marek Olbryś"
        )
        is None
    )
    assert (
        annual_year(
            "Oświadczenie majątkowe radnego województwa złożone na 2 miesiące "
            "przed upływem kadencji"
        )
        is None
    )
    assert annual_year("w zw. z zakończeniem pełnienia funkcji Wicemarszałka") is None


# ---------- parse_pdf_url (href verbatim — podwojne kodowanie zostaje, jak Slaski) ----------


def test_pdf_url_extracted_verbatim_double_encoded():
    pdf = parse_pdf_url(_read("podlaskie_doc_annual.html"))
    assert pdf is not None
    assert pdf.startswith(f"{BASE}/resource/")
    assert pdf.lower().endswith(".pdf")
    assert "%25C5" in pdf  # podwojne kodowanie zachowane (%25.. = zakodowane %..)


def test_pdf_url_none_when_no_attachment():
    assert parse_pdf_url("<html><body>brak pliku</body></html>") is None


# ---------- iter_declarations (stub httpx mapujacy URL -> fixture; offline) ----------


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Minimalny stub httpx.Client: URL -> fixture HTML; brakujace URL-e => pusta strona
    (osoba bez wezlow rocznych nic nie wnosi, paginacja sie zatrzymuje)."""

    def __init__(self, by_url):
        self._by_url = by_url
        self.log = []

    def get(self, url):
        self.log.append(url)
        return _FakeResp(self._by_url.get(url, "<html></html>"))


def _fake_client():
    olb = LISTING_URL + "?p=Olbry%C5%9B%40Marek"
    pro = LISTING_URL + "?p=Prokorym%40%C5%81ukasz"
    docdir = (
        f"{BASE}/wojewodztwo/oswiadczenia/oswiadczenia_majatkowe_od_2009/"
    )
    return _FakeClient(
        {
            # listing: strona 1 = page5 (zawiera Olbrysia i Prokoryma); strona 2 pusta -> stop
            LISTING_URL: _read("podlaskie_listing_p5.html"),
            LISTING_URL + "?page=2": "<html></html>",
            # Olbrys: landing -> wezly 2024 (snapshoty) i 2025 (roczne za 2024) -> doc
            olb: _read("podlaskie_olbrys_landing.html"),
            olb + "%5E2024": _read("podlaskie_olbrys_2024.html"),
            olb + "%5E2025": _read("podlaskie_olbrys_2025.html"),
            docdir + "oswiadczenie-majatkowe-marek-olbrys-27.html": _read(
                "podlaskie_doc_annual.html"
            ),
            # Prokorym: landing -> wezly 2024/2025/2026; tylko 2025 ma roczne za 2024 -> doc
            pro: _read("podlaskie_prokorym_landing.html"),
            pro + "%5E2025": _read("podlaskie_prokorym_2025.html"),
            docdir + "oswiadczenie-majatkowe-lukasz-prokorym-6.html": _read(
                "podlaskie_doc_prokorym.html"
            ),
        }
    )


def test_iter_declarations_yields_fiscal_year_annuals_only():
    mod.time.sleep = lambda *_a, **_k: None  # bez opoznien w tescie
    rows = list(iter_declarations(_fake_client()))

    # Z calego listingu (25 osob) tylko Olbrys i Prokorym maja fixtury z rocznym za 2024.
    # Pozostali zwracaja pusta strone -> brak wezlow rocznych -> nic nie wnosza.
    assert {(n, y) for n, y, *_ in rows} == {
        ("Olbryś Marek", 2024),
        ("Prokorym Łukasz", 2024),
    }
    # rok WYNIKOWY to rok FISKALNY z tytulu (wezel ^2025 -> 2024), nie numer wezla
    assert all(y == 2024 for _, y, *_ in rows)


def test_iter_declarations_pdf_urls_absolute_double_encoded():
    mod.time.sleep = lambda *_a, **_k: None
    rows = list(iter_declarations(_fake_client()))
    by_name = {n: (y, pdf, landing) for n, y, pdf, landing in rows}

    pdf_olb = by_name["Olbryś Marek"][1]
    assert pdf_olb == (
        f"{BASE}/resource/48467/150845/O%25C5%259Bwiadczenie+maj%25C4%2585tkowe+"
        "radnego+wojew%25C3%25B3dztwa+podlaskiego+-+Marek+Olbry%25C5%259B.pdf"
    )
    # wszystkie pdf_url absolutne, .pdf, z zachowanym podwojnym kodowaniem
    assert all(
        pdf.startswith(f"{BASE}/resource/") and pdf.lower().endswith(".pdf") and "%25C5" in pdf
        for _, pdf, _ in by_name.values()
    )
    # landing_url = strona osoby (4-tuple), absolutny deep-link ?p=...
    assert all(landing.startswith(LISTING_URL + "?p=") for _, _, landing in by_name.values())


def test_iter_declarations_dedup_and_skips_korekta_snapshot():
    mod.time.sleep = lambda *_a, **_k: None
    client = _fake_client()
    rows = list(iter_declarations(client))

    # dedup per (name, year): klucz unikalny mimo wielu dokumentow pod wezlami
    assert len(rows) == len({(n, y) for n, y, *_ in rows})

    # Prokorym ma pod ^2025 trzy dokumenty (roczne + korekta 'za 2024 rok' + generyczne) —
    # wynik to JEDEN roczny; korekta i generyczne pominiete. Wiec pobieramy doc tylko dla
    # rocznego (prokorym-6), nigdy dla korekty (prokorym-7) ani generycznego (prokorym-5).
    assert any("oswiadczenie-majatkowe-lukasz-prokorym-6.html" in u for u in client.log)
    assert not any("oswiadczenie-majatkowe-lukasz-prokorym-7.html" in u for u in client.log)
    assert not any("oswiadczenie-majatkowe-lukasz-prokorym-5.html" in u for u in client.log)

    # Olbrys: resztka 'za 2023 rok' pod ^2024 odpada (fiscal < MIN_YEAR) PRZED pobraniem
    # podstrony -> zaden doc z wezla ^2024 nie jest pobierany.
    olb_2024_docs = [
        u for u in client.log if "marek-olbrys-2" in u and u.endswith(".html") and "%5E" not in u
    ]
    # tylko -27 (z ^2025) powinien byc pobrany sposrod podstron Olbrysia
    assert any(u.endswith("oswiadczenie-majatkowe-marek-olbrys-27.html") for u in olb_2024_docs)
    assert not any(
        u.endswith(("marek-olbrys-22.html", "marek-olbrys-23.html", "marek-olbrys-24.html",
                    "marek-olbrys-25.html", "marek-olbrys-26.html"))
        for u in client.log
    )
