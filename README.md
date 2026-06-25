<div align="center">

# 🩺 Greedy Doctor

**Ile godzin w miesiącu musiałby przepracować radny-lekarz, żeby uczciwie zarobić to, co wpisał w oświadczeniu majątkowym?**

Czasem wychodzi 160. Czasem wychodzi 700 — a miesiąc ma najwyżej 720.

![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791?logo=postgresql&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/frontend-React%2018%20%2B%20Vite-61DAFB?logo=react&logoColor=black)
![LLM](https://img.shields.io/badge/LLM-Ollama%20·%20Bielik%207B-000000?logo=ollama&logoColor=white)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

<br/>

![Greedy Doctor — ranking radnych-lekarzy wg implied working hours](docs/assets/frontend.png)

</div>

---

## Co to jest

Greedy Doctor czyta jawne oświadczenia majątkowe radnych, wyłapuje wśród nich
praktykujących lekarzy i sprawdza jedną rzecz: **czy zadeklarowany dochód da się
przepracować.** Bierze zadeklarowaną kwotę, dzieli ją przez realne rynkowe stawki
lekarskie i wylicza, ile godzin w miesiącu trzeba by spędzić przy łóżku pacjenta,
żeby tyle zarobić. Kiedy wynik przekracza liczbę godzin, jaką da się fizycznie
przepracować, deklaracja trafia na listę do sprawdzenia.

To narzędzie śledcze, nie wyrok. Wysokie „implied hours" nie dowodzą niczego poza
tym, że liczby się nie spinają i ktoś powinien na nie spojrzeć — niedoszacowana
stawka, dochód z innego źródła niż medycyna, błąd w odczycie skanu. Greedy Doctor
zawęża stos oświadczeń do tych, które warto przeczytać oczami.

Dane robi pythonowy pipeline; wyniki pokazuje read-only frontend (FastAPI + React).

## Jak liczymy „implied working hours"

Sednem jest jeden iloraz:

```
godziny/miesiąc = (roczny dochód / 12) / stawka godzinowa
```

Stawkę bierzemy **najhojniejszą realną** — kontraktową (B2B), liczoną od mediany
rynkowych widełek dla danej specjalizacji. Logika jest celowo życzliwa dla radnego:
jeśli dochód nie spina się nawet przy stawce topowego kontraktowca, to przy pensji
etatowej nie spina się tym bardziej.

> **Przykład.** Radny deklaruje **720 000 zł/rok** z praktyki, czyli 60 000 zł/mc.
> - Jako etatowy specjalista (≈ 70 zł/h) → **≈ 850 h/mc** — trzeba by pracować 28 h
>   na dobę. Niemożliwe.
> - Jako kontraktowy anestezjolog (mediana 375 zł/h) → **160 h/mc** — to realny,
>   pełny etat.
>
> Ten sam dochód, dwie różne historie. Dlatego ranking idzie po stawce B2B.

Progi (do wyregulowania w [`norms.py`](greedy_doctor/norms.py)):

| Próg | Wartość | Znaczenie |
|---|---|---|
| Pełny etat | **168 h/mc** | punkt odniesienia |
| `THRESHOLD_HEAVY` | **300 h/mc** | ciężkie dyżury, ale wciąż możliwe |
| `THRESHOLD_IMPLAUSIBLE` | **400 h/mc** | ponad 13 h każdego dnia miesiąca — czerwona flaga |
| `MIN_INCOME` | **300 000 zł/rok** | poniżej tej sumy radny nie wchodzi na listę (ścigamy nadużycia, nie drobnicę) |

## Architektura w pigułce

Pipeline jest bezstanowy i wieloetapowy, a **kolejką jest sam Postgres**: kolumna
`declaration.status` to stan, a workery zgarniają wiersze przez `FOR UPDATE SKIP
LOCKED`, więc dwa procesy nigdy nie złapią tego samego rekordu. Żadnego Redisa,
żadnego brokera — worker bierze wiersz, przetwarza, commituje i leci po następny,
aż kolejka pusta.

```mermaid
flowchart LR
    crawl["crawl<br/>(I/O)"] -->|downloaded| extract["extract<br/>(pdfplumber / OCR)"]
    extract -->|text_extracted| classify["classify<br/>(LLM)"]
    classify -->|classified| analyze["analyze"]
    classify -.->|poison pill| failed["classify_failed"]
    analyze -->|analyzed| out(["wynik<br/>(API + frontend)"])
    enrich["enrich<br/>(Playwright)"] -.->|doctor_profile| analyze
```

`enrich` stoi z boku — nie jest etapem statusu, biega własnym rytmem i dolewa do
tabeli `doctor_profile` (potwierdza, kto faktycznie jest lekarzem, scrapując
ZnanyLekarz). `analyze` uznaje radnego za lekarza na podstawie `doctor_profile`,
flagi `mentions_medical` z klasyfikatora albo medycznych słów w tytułach dochodu.

Pełny opis modułów i tabel jest w [`CLAUDE.md`](CLAUDE.md).

## Wymagania sprzętowe

Pipeline dzieli się na dwie ligi. **Etapy lekkie** (`crawl`, `extract` dla PDF-ów
z warstwą tekstową, `analyze`, API) to czyste I/O i CPU — pójdą na dowolnym laptopie.
**Etapy ciężkie** (`classify` oraz fallback OCR w `extract`) odpalają lokalny LLM
przez Ollamę i to one wyznaczają poprzeczkę.

| Konfiguracja | Co uciągnie | Uwagi |
|---|---|---|
| **Minimum** — CPU only, ~16 GB RAM | całość | `classify` i OCR-wizyjny działają, ale wolno (model 7B na CPU) |
| **Zalecane** — GPU NVIDIA ≥ 8 GB VRAM, 16 GB RAM | całość komfortowo | 12 GB VRAM pomieści model Bielik **i** wizyjny naraz |
| **Dysk** | ~10–15 GB | modele Ollamy (Bielik 7B Q8 ≈ 8 GB + model wizyjny) + miejsce na PDF-y i wolumen Postgresa |

Do tego, niezależnie od GPU:
- **PostgreSQL 17** (kontener z `docker compose`, ~lekki),
- **tesseract** z danymi językowymi `pol` — OCR skanów,
- **Chromium** sterowany przez **Playwright** — tylko etap `enrich`, ~1 rdzeń na czas scrapowania.

> 💡 **ponytail:** dokładne zużycie VRAM zależy od wybranego modelu i kwantyzacji.
> Powyższe to rozsądny punkt startu — skalibruj pod swój sprzęt (mniejszy model lub
> niższy Q, jeśli VRAM-u brak).

## Instalacja

```bash
# 1. Zależności Pythona (uv tworzy .venv)
uv sync

# 2. Postgres 17 na porcie 5544 (nietypowy, żeby nie bić się z lokalnym pg)
docker compose up -d

# 3. Ollama + modele (LLM do klasyfikacji + wizyjny do OCR-fallbacku)
#    https://ollama.com — zainstaluj, potem:
ollama pull hf.co/SpeakLeash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q8_0
ollama pull gemma4

# 4. Tesseract z językiem polskim
#    Debian/Ubuntu:
sudo apt install tesseract-ocr tesseract-ocr-pol
#    macOS:  brew install tesseract tesseract-lang

# 5. Chromium dla Playwrighta (tylko jeśli używasz `enrich`)
#    Spróbuj auto-instalacji:
uv run playwright install chromium
#    Jeśli host jest zbyt nowy i auto-download zawiedzie — wskaż własny Chromium
#    przez CHROME_PATH (patrz sekcja Konfiguracja).

# 6. Frontend
cd frontend && npm install
```

Domyślna konfiguracja działa od ręki (Postgres na `localhost:5544`, Ollama na
`localhost:11434`). Cokolwiek innego nadpisujesz zmiennymi środowiskowymi — patrz
[Konfiguracja](#konfiguracja).

## Uruchomienie pipeline'u

Każdy etap to osobny worker drenujący kolejkę. Odpalaj **po kolei**:

```bash
.venv/bin/python -m greedy_doctor.crawl --source kielce   # kielce|poznan|nowytomysl|gdansk|gdynia|sopot|dolnoslaskie|pomorskie|wielkopolskie
.venv/bin/python -m greedy_doctor.extract
.venv/bin/python -m greedy_doctor.classify --limit 50     # --limit opcjonalny
.venv/bin/python -m greedy_doctor.analyze
.venv/bin/python -m greedy_doctor.enrich                  # poza kolejką; dolewa doctor_profile
```

A potem serwuj wyniki:

```bash
.venv/bin/uvicorn greedy_doctor.api:app --port 8011       # frontend wpisany na sztywno na :8011
cd frontend && npm run dev                                # Vite na :5173
```

Otwórz **http://localhost:5173**.

## ➕ Dodawanie nowego regionu

Dodanie miasta = **jeden nowy plik** w `greedy_doctor/sources/` + **jeden wpis**
w rejestrze. Cała reszta pipeline'u (OCR, LLM, analiza) działa dalej bez zmian —
nie musisz nigdzie flagować, czy PDF-y to skany; `extract` wykrywa to sam.

### Krok 1 — napisz adapter

Adapter wystawia dokładnie dwie rzeczy: stałą `CITY` i generator
`iter_declarations(client)`, który **yielduje krotki `(name, year, pdf_url)`**.
`client` to gotowy `httpx.Client` (timeout 60 s, śledzi redirecty) wstrzykiwany
przez crawler — sam nic nie otwierasz.

Najprostszy żywy wzorzec to [`sources/nowytomysl.py`](greedy_doctor/sources/nowytomysl.py).
Skopiuj go i przerób:

```python
# greedy_doctor/sources/mojemiasto.py
"""Adapter zrodla: Rada Miasta Moje Miasto. <opisz krotko: HTML czy REST API,
ukladzie strony/endpointow, czy PDF-y maja warstwe tekstowa czy to skany>.
"""

CITY = "Moje Miasto"            # trafia do kolumny radny.city
BASE = "https://bip.mojemiasto.pl"


def iter_declarations(client):
    """Yielduj (name, year, pdf_url) — po jednym oswiadczeniu na raz."""
    # 1. wejdz na liste/endpoint i znajdz oswiadczenia
    listing = client.get(f"{BASE}/oswiadczenia").text
    for ... in ...:                       # parsuj HTML albo JSON
        name = "Nazwisko Imie"            # KONWENCJA: nazwisko najpierw
        year = 2024                       # int
        pdf_url = f"{BASE}/pliki/xyz.pdf" # URL ABSOLUTNY
        yield name, year, pdf_url
```

Konwencje, których trzymają się pozostałe adaptery:

- ✅ **`yield`, nie `return` listy** — generator, leci po jednym.
- ✅ **`name` w formacie „Nazwisko Imię"** — jak w polskich BIP-ach (jeśli źródło
  daje „Imię Nazwisko", odwróć; patrz helpery `_surname_first` w `poznan`/`wielkopolskie`).
- ✅ **`pdf_url` absolutny** — sklej z `BASE`, jeśli strona daje ścieżki względne.
- ✅ **Skany? Nic nie rób** — `extract` sam wykryje brak warstwy tekstowej (< 50
  znaków) i puści OCR. Adapter zwraca taki sam URL co dla PDF-a tekstowego.
- ✅ **Dedup masz za darmo** — crawler pomija to, co już ma (klucz `radny + rok`),
  więc możesz puszczać go wielokrotnie bez duplikatów.
- 💡 **Parsowanie trzymaj czyste** (HTML/JSON → dane, bez sieci w środku), żeby dało
  się je przetestować na fixturze offline — tak są zrobione istniejące adaptery.

### Krok 2 — zarejestruj go

W [`greedy_doctor/crawl.py`](greedy_doctor/crawl.py) dorzuć import i wpis do dicta
`SOURCES` (linie ~15–31):

```python
from greedy_doctor.sources import (
    dolnoslaskie,
    kielce,
    mojemiasto,        # ← nowy
    ...
)

SOURCES = {
    "kielce": kielce,
    "mojemiasto": mojemiasto,   # ← klucz = wartość flagi --source
    ...
}
```

### Krok 3 — odpal

```bash
.venv/bin/python -m greedy_doctor.crawl --source mojemiasto
# ...a potem extract / classify / analyze jak zwykle
```

Tyle. Gotowe.

### Obecnie wspierane źródła

| `--source` | Region | BIP | Pobieranie | PDF-y | Radnych |
|---|---|---|---|---|---|
| `kielce` | Kielce | bipum.kielce.eu | HTML | tekst | 25 |
| `poznan` | Poznań | bip.poznan.pl | HTML (profile radnych) | skan → OCR | 33 |
| `nowytomysl` | Nowy Tomyśl | bip.nowytomysl.pl | REST API (Madkom) | skan → OCR | 23 |
| `gdansk` | Gdańsk | bip.gdansk.pl | HTML (CMS eUrząd) | skan → OCR | 47 |
| `gdynia` | Gdynia | bip.um.gdynia.pl | JSON API | skan → OCR | 28 |
| `sopot` | Sopot | bip.sopot.pl | REST API (Madkom) | skan → OCR | 21 |
| `dolnoslaskie` | Sejmik Dolnośląski | bip.dolnyslask.pl | REST API (Madkom) | skan → OCR | 38 |
| `pomorskie` | Sejmik Pomorski | bip.pomorskie.eu | REST API (Madkom) | skan → OCR | 33 |
| `wielkopolskie` | Sejmik Wielkopolski | bip.umww.pl | HTML (CMS HSI) | skan → OCR | 30 |

**Łącznie: 9 źródeł, 278 radnych** — 6 rad miast + 3 sejmiki wojewódzkie. Każdy adapter
to ~30–60 linii; trzy z nich (`gdansk`, `sopot`, `gdynia`) powstały równolegle przez subagenty.

## Konfiguracja

Wszystko ma sensowne domyślne wartości; nadpisujesz przez zmienne środowiskowe.

| Zmienna | Domyślnie | Do czego |
|---|---|---|
| `DATABASE_URL` | `postgresql://greedy:greedy@localhost:5544/greedy_doctor` | połączenie z Postgresem |
| `OLLAMA_URL` | `http://localhost:11434` | endpoint Ollamy |
| `OLLAMA_MODEL` | `hf.co/SpeakLeash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q8_0` | polski LLM do klasyfikacji |
| `OCR_MODEL` | `gemma4:latest` | model wizyjny — fallback OCR, gdy tesseract zwróci za mało |
| `CHROME_PATH` | ścieżka do Chromium z Playwrighta | binarka Chromium dla `enrich` (ustaw, jeśli auto-download nie działa) |

## Strojenie

Wszystkie pokrętła są w jednym pliku — [`greedy_doctor/norms.py`](greedy_doctor/norms.py).
Tam zmienisz próg wejścia na listę (`MIN_INCOME`), stawki godzinowe per
specjalizacja (`B2B_RATES`, `ETAT_*`) i progi flagowania
(`THRESHOLD_HEAVY`, `THRESHOLD_IMPLAUSIBLE`). Kwota bazowa etatu zmienia się
1 lipca każdego roku — to jedyna rzecz warta corocznej aktualizacji.

## Testy

```bash
.venv/bin/python -m pytest                                  # cała sucha
.venv/bin/python -m pytest tests/test_analyze.py::test_name # pojedynczy test
```

Testy wymagają działającego Postgresa. `conftest.py` przekierowuje `DATABASE_URL`
na osobną bazę `greedy_doctor_test`, **zanim** zaimportuje `db`, więc Twoje
crawlowane dane deweloperskie są bezpieczne — testy ich nie ruszą.

---

<div align="center">

**Disclaimer.** Greedy Doctor liczy prawdopodobieństwo, nie winę. Wysokie „implied
hours" to sygnał do sprawdzenia jawnego dokumentu, nie zarzut. Wszystkie dane
pochodzą z publicznych oświadczeń majątkowych (BIP).

Licencja: [Apache 2.0](LICENSE).

</div>
