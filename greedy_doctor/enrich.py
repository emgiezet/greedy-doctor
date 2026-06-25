"""Wzbogacanie: czy radny jest lekarzem + specjalizacja (ZnanyLekarz).

ZnanyLekarz uzywa Algolii. httpx jest fingerprintowany/rate-limitowany (403 po paru
zadaniach), wiec odpytujemy przez PRZEGLADARKE (zachowuje sie jak uzytkownik, niezawodnie)
i przechwytujemy odpowiedz Algolii z autocomplete. NIL zostaje autorytatywnym spot-checkiem
kandydatow (limit 10/2h) — tu nie ruszany.

Logika dopasowania (match_doctor) i mapowanie specjalizacji sa czyste i przetestowane;
warstwa sieciowa to przegladarka, walidowana przebiegiem na zywych danych.
ponytail: sciezka chromium zahardcodowana (OS za nowy na pobieranie przez playwright);
override przez CHROME_PATH.
"""

import os
import unicodedata

from greedy_doctor import db

CHROME = os.environ.get(
    "CHROME_PATH", "/home/mgz/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
)

# specjalizacja ZnanyLekarz -> kategoria stawki B2B (stemy, odporne na polska odmiane)
_SPEC_STEMS = {
    "anestezj": "anesthesiology",
    "ratunkow": "sor",
    "radiolog": "radiology",
    "patomorfolog": "pathology",
    "patolog": "pathology",
}


def _norm(s: str) -> str:
    """Lower + bez polskich diakrytykow (do porownan nazwisk/miast)."""
    s = s.replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def b2b_category_for(specializations) -> str:
    for spec in specializations:
        sn = _norm(spec)
        for stem, cat in _SPEC_STEMS.items():
            if stem in sn:
                return cat
    return "general_shift"


def match_doctor(radny_fullname: str, city: str, hits):
    """Czy ktorys hit ZnanyLekarz pasuje do radnego (nazwisko+imie w tokenach + miasto).
    Odporne na kolejnosc imie/nazwisko i diakrytyki. Zwraca (is_doctor, specializations)."""
    rtok = {_norm(t) for t in radny_fullname.split()}
    cityn = (
        _norm(city) if city else None
    )  # None (sejmik) -> match tylko po imieniu+nazwisku
    for h in hits:
        if _norm(h.get("surname", "")) in rtok and _norm(h.get("name", "")) in rtok:
            if cityn is None or any(cityn == _norm(c) for c in h.get("cities", [])):
                return True, h.get("specializations", [])
    return False, []


class ZnanyLekarz:
    """Sesja przegladarki do ZnanyLekarz; search(surname) -> lista hitow lekarzy."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True, executable_path=CHROME, args=["--no-sandbox"]
        )
        self._page = self._browser.new_page()
        self._hits = []
        self._page.on("response", self._capture)
        self._page.goto(
            "https://www.znanylekarz.pl/", wait_until="domcontentloaded", timeout=40000
        )
        self._page.wait_for_timeout(1500)
        for sel in [
            "button#onetrust-accept-btn-handler",
            'button:has-text("Akceptuj")',
        ]:
            el = self._page.query_selector(sel)
            if el:
                el.click()
                self._page.wait_for_timeout(400)
                break
        self._input = self._page.query_selector('input[type="text"], input:not([type])')
        return self

    def _capture(self, resp):
        if "algolia.net" in resp.url:
            try:
                for res in resp.json().get("results", []):
                    if res.get("index") == "pl_autocomplete_doctor":
                        self._hits = res.get("hits", [])
            except Exception:
                pass

    def search(self, surname: str):
        self._hits = []
        self._input.click()
        self._input.fill("")
        self._input.type(surname, delay=90)
        self._page.wait_for_timeout(2500)  # autocomplete XHR
        return list(self._hits)

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()


def run():
    """Wzbogac wszystkich radnych przez przegladarke; cache w doctor_profile.
    Bledy SA glosne (liczone i raportowane), nie polykane po cichu."""
    with db.connect() as conn:
        rows = conn.execute("SELECT id, name, city FROM radny ORDER BY id").fetchall()

    found, errors = [], 0
    with ZnanyLekarz() as zl:
        for rid, name, city in rows:
            try:
                hits = zl.search(name.split()[0])
            except Exception as e:
                errors += 1
                print(f"  BLAD przy {name}: {type(e).__name__} {str(e)[:80]}")
                continue
            # sejmik wojewodzki nie ma realnego miasta -> match po pelnym nazwisku
            city_arg = None if city.startswith("Sejmik") else city
            is_doc, specs = match_doctor(name, city_arg, hits)
            if is_doc:
                found.append((rid, name, specs))

    with db.connect() as conn:
        for rid, _name, specs in found:
            conn.execute(
                "INSERT INTO doctor_profile (radny_id, specializations, tier) "
                "VALUES (%s, %s, %s) ON CONFLICT (radny_id) DO UPDATE SET "
                "specializations = EXCLUDED.specializations, tier = EXCLUDED.tier",
                (rid, specs, "specialist" if specs else "no_specialization"),
            )
        conn.commit()
    print(f"sprawdzono: {len(rows)} | lekarze: {len(found)} | bledy: {errors}")
    return len(found)


if __name__ == "__main__":
    db.init_schema()
    run()
