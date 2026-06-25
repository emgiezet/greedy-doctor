from pathlib import Path

from greedy_doctor.extract import needs_ocr, pdf_text

FIX = Path(__file__).parent / "fixtures"


def test_extracts_text_layer_from_kielce_pdf():
    data = (FIX / "kielce_sample.pdf").read_bytes()
    text = pdf_text(data)
    # PDF Kielc ma warstwe tekstowa (zero OCR) -> czytelny tekst oswiadczenia
    assert "OŚWIADCZENIE" in text.upper()
    assert len(text) > 500


def test_needs_ocr_detects_empty_or_scan():
    assert needs_ocr("") is True
    assert needs_ocr("   \n  ") is True
    assert needs_ocr("krotko") is True  # <50 znakow = skan/pusta warstwa
    assert needs_ocr("OŚWIADCZENIE MAJĄTKOWE " * 5) is False  # realny tekst
