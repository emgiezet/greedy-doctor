from pathlib import Path

from greedy_doctor.sources.gdansk import parse_listing, pick_declaration

FIX = Path(__file__).parent / "fixtures"


def test_listing_finds_only_councilors():
    rows = parse_listing((FIX / "gdansk_listing_2024.html").read_text(encoding="utf-8"))
    # 45 radnych w buforze 2024 (rok wyboru — z dojsciami/odejsciami), zero pozycji menu/kategorii
    assert len(rows) == 45
    names = {n for n, _ in rows}
    assert "Banach Jolanta Maria" in names  # <span> jest juz 'Nazwisko Imie [Imie2]'
    assert "Ważny Karol" in names
    # kafle kategorii i menu boczne (ta sama struktura <a><span>) NIE wpadaja
    assert not any(
        bad in names
        for bad in (
            "Prezydent Miasta Gdańska",
            "Radni Miasta Gdańska",
            "Oświadczenia majątkowe",
            "Akty Prawne",
        )
    )
    # kazdy link to podstrona radnego (prawo-lokalne/...,a,id), absolutny
    assert all(
        u.startswith("https://bip.gdansk.pl/prawo-lokalne/") and ",a," in u
        for _, u in rows
    )


def test_pick_declaration_simple_profile():
    # Banach: dokladnie jedno 'Oswiadczenie' (+ stopkowy PDF dostepnosci, ktory pomijamy)
    pdf = pick_declaration((FIX / "gdansk_banach.html").read_text(encoding="utf-8"))
    assert (
        pdf
        == "https://download.cloudgdansk.pl/gdansk-pl/d/202408235425/oswiadczenie.pdf"
    )


def test_pick_declaration_skips_snapshots_and_corrections():
    # Bejm: 'Oswiadczenie', 'Oswiadczenie 2/3/4' (snapshoty) i kilka 'Korekta'.
    # Bierzemy DOKLADNIE 'Oswiadczenie' — nie numerowany snapshot, nie korekte.
    pdf = pick_declaration((FIX / "gdansk_bejm.html").read_text(encoding="utf-8"))
    assert (
        pdf
        == "https://download.cloudgdansk.pl/gdansk-pl/d/202405230141/oswiadczenie.pdf"
    )
    assert "korekta" not in pdf.lower()
    assert "oswiadczenie-2" not in pdf and "oswiadczenie-3" not in pdf


def test_pick_declaration_excludes_footer_accessibility_pdf():
    # Stopkowy PDF deklaracji dostepnosci ma class="h-100", nie 'article-file' -> nie lapiemy go.
    bejm = (FIX / "gdansk_bejm.html").read_text(encoding="utf-8")
    assert "informacja-o-urzedzie" in bejm  # stopka jest w HTML...
    assert "informacja-o-urzedzie" not in (
        pick_declaration(bejm) or ""
    )  # ...ale nie w wyniku


def test_pick_declaration_returns_none_when_no_declaration():
    assert pick_declaration("<html><body>brak zalacznikow</body></html>") is None
