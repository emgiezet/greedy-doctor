# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Greedy Doctor crawls Polish municipal councilor ("radny") asset declarations, identifies which councilors are practising doctors, and computes an **implied-working-hours** metric: how many hours/month they'd need to work to earn their declared income at realistic medical pay rates. Implausibly high implied hours flag suspect declarations. A Python pipeline produces the data; a FastAPI + React frontend serves the results read-only. Code comments and domain terms are in Polish.

## Commands

```bash
# Setup
uv sync                                  # install Python deps into .venv
docker compose up -d                     # Postgres 17 on localhost:5544

# Pipeline — each is an independent worker draining a Postgres queue; run in order
.venv/bin/python -m greedy_doctor.crawl --source kielce   # any key from SOURCES (23 total)
.venv/bin/python -m greedy_doctor.extract
.venv/bin/python -m greedy_doctor.classify --limit 50     # --limit optional
.venv/bin/python -m greedy_doctor.analyze
.venv/bin/python -m greedy_doctor.enrich                  # out-of-band; fills doctor_profile

# Serve
.venv/bin/uvicorn greedy_doctor.api:app --port 8011       # frontend hardcodes :8011
cd frontend && npm install && npm run dev                 # Vite dev server on :5173

# Tests — Postgres must be up; conftest auto-creates a separate greedy_doctor_test DB
.venv/bin/python -m pytest                                # full suite
.venv/bin/python -m pytest tests/test_analyze.py::test_name   # single test
```

No linter or formatter is configured.

## Architecture

A stateless multi-stage pipeline where **Postgres is the queue**: `declaration.status`
is the pipeline state, and workers claim rows with `FOR UPDATE SKIP LOCKED`
(`queue.py` → `claim`/`advance`) so two workers never grab the same row — no Redis,
no broker. A worker claims one row, processes it, commits, and repeats until the
queue is empty.

Status flow:
```
crawl    → downloaded
extract  → text_extracted     (pdfplumber for text PDFs; scans → OCR)
classify → classified         (LLM extracts income lines)   ⟂  classify_failed (poison pill, isolated)
analyze  → analyzed           (writes an `analysis` row only if the councilor is a doctor)
```
`enrich` is **not** a status stage — it runs on its own and populates `doctor_profile`.
`analyze` treats a councilor as a doctor via `doctor_profile`, the classifier's
`mentions_medical` flag, or medical keywords in the income titles.

Tables (`db.py`): `radny` (councilor) → `declaration` (1:N; holds pdf/raw_text/parsed/status)
; `doctor_profile` (radny_id → specializations, tier) ; `analysis` (radny_id+year →
total_income, implied_h_etat, implied_h_b2b, flag).

### Modules
- `crawl.py` + `sources/*.py` — one adapter per source, each exposing `CITY` and `iter_declarations(client) → (name, year, pdf_url)`. **Adding a source = adding a `sources/` module** — auto-discovered via `pkgutil`. Sources with broken TLS declare `VERIFY = False`; `crawl.py` reads `getattr(src, "VERIFY", True)`. 23 sources: all 16 voivodeship sejmiks + 7 city councils (Gdańsk, Gdynia, Kielce, Nowy Tomyśl, Poznań, Skierniewice, Sopot). CMS engines: Madkom REST, SmartSite/BIT, Joomla/K2, Joomla+Phoca Download, Joomla com\_govarticle, WordPress WP REST API, TYPO3 Bootstrap accordion, static HTML/Yii2, Drupal 7, RBIP v4, SystemDoBIP/E-LINE.
- `extract.py` — pdfplumber for text PDFs; scans go to `tesseract -l pol`; if tesseract returns too little, falls back to an Ollama vision model.
- `classify.py` — httpx → Ollama `/api/generate` with a Pydantic schema as the `format`; default model Bielik-Minitron-7B (Polish). Returns `ParsedDeclaration{income: [IncomeEntry], mentions_medical}`.
- `analyze.py` — `implied_monthly_hours` + `classify_hours` against `norms.py`. Dedups income lines by amount because the LLM lists the same sum under multiple titles.
- `enrich.py` — drives Playwright/Chromium to scrape ZnanyLekarz (Algolia) and confirm doctors; plain httpx gets rate-limited (403), so it uses a real browser.
- `norms.py` — **all tunable thresholds and pay rates live here**: `MIN_INCOME` (listing/ranking cutoff), salaried (`ETAT_*`) and B2B hourly ranges, and the `THRESHOLD_HEAVY`/`THRESHOLD_IMPLAUSIBLE` flag bands.
- `api.py` — read-only; candidates are `total_income > MIN_INCOME`, ranked by `implied_h_b2b` descending (most "greedy" first).

## Runtime services (not in pyproject.toml)

The OCR, LLM, and enrich stages need external services that are **not** Python deps:
- **Ollama** at `OLLAMA_URL` (default `localhost:11434`) with the Bielik model (classify) and a vision model (OCR fallback).
- **tesseract** with Polish language data (`-l pol`) on `PATH`.
- **Playwright + Chromium** for `enrich`. The Chromium binary path is hardcoded via `CHROME_PATH` because the host OS is too new for Playwright's auto-download — set this to your local Chromium.

Env vars: `DATABASE_URL`, `OLLAMA_URL`, `OLLAMA_MODEL`, `CHROME_PATH`.

## Gotchas
- Postgres runs on the non-standard port **5544** (avoids clashing with a local pg).
- The frontend (`frontend/src/App.jsx`) hardcodes `http://localhost:8011/api` — run the API on **8011** or edit that constant.
- Tests require a running Postgres; `tests/conftest.py` points `DATABASE_URL` at a separate `greedy_doctor_test` DB **before** importing `db`, so crawled dev data is never truncated by test runs.
