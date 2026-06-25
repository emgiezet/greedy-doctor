"""Worker extract: pdf_data -> raw_text. status -> text_extracted.

Warstwa tekstowa (Kielce) -> pdfplumber. Skan -> OCR: **tesseract `pol`** (szybko, CPU,
kompletnie dla druku); jesli tesseract zwraca za malo (nieczytelne) -> **fallback gemma4**
(Ollama vision). PyMuPDF renderuje strony. olmocr w Ollamie jest text-only (bez vision).
"""

import base64
import io
import os
import subprocess

import fitz  # pymupdf
import httpx
import pdfplumber

from greedy_doctor import db
from greedy_doctor.queue import advance, claim

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OCR_MODEL = os.environ.get("OCR_MODEL", "gemma4:latest")
OCR_PROMPT = (
    "Przepisz dokladnie caly tekst z tej strony polskiego oswiadczenia majatkowego. "
    "Zwroc wylacznie tekst dokumentu, bez komentarzy."
)
_MIN_LEGIBLE = (
    200  # ponytail: ponizej tylu znakow OCR uznajemy za nieczytelny -> fallback
)


def pdf_text(pdf_bytes):
    out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    return "\n".join(out)


def needs_ocr(text):
    """Pusta/znikoma warstwa tekstowa => skan => OCR."""
    return len(text.strip()) < 50


def _pages_png(pdf_bytes, dpi):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        yield page.get_pixmap(dpi=dpi).tobytes("png")


def ocr_tesseract(pdf_bytes, dpi=300):
    out = []
    for png in _pages_png(pdf_bytes, dpi):
        r = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "pol"],
            input=png,
            capture_output=True,
            timeout=120,
        )
        out.append(r.stdout.decode("utf-8", "ignore"))
    return "\n".join(out)


def ocr_gemma(pdf_bytes, dpi=150):
    out = []
    for png in _pages_png(pdf_bytes, dpi):
        b64 = base64.b64encode(png).decode()
        r = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OCR_MODEL,
                "prompt": OCR_PROMPT,
                "images": [b64],
                "stream": False,
                "options": {"temperature": 0, "num_predict": 2048},
            },
            timeout=600,
        )
        r.raise_for_status()
        out.append(r.json().get("response", ""))
    return "\n".join(out)


def ocr_pdf(pdf_bytes):
    """tesseract pol; fallback gemma4 gdy tesseract zwraca za malo (nieczytelny skan)."""
    text = ocr_tesseract(pdf_bytes)
    if len(text.strip()) < _MIN_LEGIBLE:
        text = ocr_gemma(pdf_bytes)
    return text


def run_once(conn):
    cid = claim(conn, "downloaded")
    if cid is None:
        return False
    (data,) = conn.execute(
        "SELECT pdf_data FROM declaration WHERE id = %s", (cid,)
    ).fetchone()
    data = bytes(data)
    text = pdf_text(data)
    if needs_ocr(text):  # skan -> OCR (tesseract, fallback gemma4)
        text = ocr_pdf(data)
    conn.execute("UPDATE declaration SET raw_text = %s WHERE id = %s", (text, cid))
    advance(conn, cid, "text_extracted")
    conn.commit()
    return True


def run():
    n = 0
    with db.connect() as conn:
        while run_once(conn):
            n += 1
    return n


if __name__ == "__main__":
    db.init_schema()
    print(f"przetworzono: {run()}")
