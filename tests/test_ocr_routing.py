"""OCR engine-selection logic and the PDF text-layer probe (no network)."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.services import ocr


@pytest.mark.parametrize(
    "mime_type, has_layer, expected",
    [
        (ocr.PDF_MIME, True, ocr.ENGINE_PDF_TEXT),
        (ocr.PDF_MIME, False, ocr.ENGINE_VISION),
        (ocr.DOCX_MIME, False, ocr.ENGINE_DOCX),
        (ocr.DOCX_MIME, True, ocr.ENGINE_DOCX),
        ("image/png", False, ocr.ENGINE_VISION),
        ("image/jpeg", False, ocr.ENGINE_VISION),
    ],
)
def test_choose_engine(mime_type, has_layer, expected) -> None:
    assert ocr.choose_engine(mime_type, has_layer) == expected


def test_choose_engine_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        ocr.choose_engine("application/zip", False)


def _text_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "This is a clearly readable text layer with plenty of characters "
        "so the probe recognizes it as a real, extractable PDF text layer.",
    )
    doc.save(str(path))
    doc.close()


def _imageonly_pdf(path: Path) -> None:
    # A page with no inserted text → no usable text layer.
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


def test_probe_detects_text_layer(tmp_path: Path) -> None:
    pdf = tmp_path / "text.pdf"
    _text_pdf(pdf)
    page_texts, page_count, has_layer = ocr.probe_pdf_text_layer(pdf)
    assert page_count == 1
    assert has_layer is True
    assert "text layer" in "".join(page_texts)


def test_probe_rejects_empty_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    _imageonly_pdf(pdf)
    _, page_count, has_layer = ocr.probe_pdf_text_layer(pdf)
    assert page_count == 1
    assert has_layer is False


def test_extension_for() -> None:
    assert ocr.extension_for(ocr.PDF_MIME) == ".pdf"
    assert ocr.extension_for(ocr.DOCX_MIME) == ".docx"
    assert ocr.extension_for("image/jpeg") == ".jpg"


def test_detect_language_english() -> None:
    text = "The quick brown fox jumps over the lazy dog near the river bank today."
    assert ocr.detect_language(text) == "en"


def test_detect_language_too_short() -> None:
    assert ocr.detect_language("hi") is None


# --- Vision partial tolerance (per-page; seam stubbed, no network) ----------
def _blank_pdf(path, pages: int) -> None:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()


def test_pdf_vision_skips_a_failed_page(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "scan.pdf"
    _blank_pdf(pdf, 3)
    # Pin concurrency to 1 so call order == page order, making "page 2 fails"
    # deterministic; the concurrency cap itself is covered in test_concurrency.py.
    monkeypatch.setattr(ocr.get_settings(), "max_parallel_calls", 1)
    calls = {"n": 0}

    def stub(content):
        calls["n"] += 1
        if calls["n"] == 2:  # page 2 persistently fails
            raise ValueError("transient-ish but non-retryable here")
        return ("page text", [], ["en"])

    monkeypatch.setattr(ocr, "_vision_ocr_image_bytes", stub)
    result = ocr.ocr_pdf_via_vision(str(pdf))

    assert result.page_count == 3
    assert result.failed_pages == [2]
    assert len(result.pages) == 3
    assert result.pages[1].text == ""  # the dropped page is empty
    assert result.pages[0].text == "page text"


def test_pdf_vision_all_pages_fail_raises(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "scan.pdf"
    _blank_pdf(pdf, 2)
    monkeypatch.setattr(ocr, "_vision_ocr_image_bytes", lambda content: (_ for _ in ()).throw(ValueError("boom")))

    with pytest.raises(RuntimeError, match="all 2 page"):
        ocr.ocr_pdf_via_vision(str(pdf))


def test_failed_pages_round_trips_through_cache() -> None:
    result = ocr.OcrResult(
        engine=ocr.ENGINE_VISION, page_count=2, language="en", text="x",
        pages=[ocr.OcrPage(page=1, text="x")], failed_pages=[2],
    )
    assert ocr.OcrResult.from_cache(result.to_cache()).failed_pages == [2]


# --- native-PDF block bboxes (text-layer path; no network) ------------------
def test_text_layer_pdf_emits_block_bboxes(tmp_path) -> None:
    pdf = tmp_path / "text.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Invoice total 1240 USD due 2025-04-01. " + ("filler " * 10))
    doc.save(pdf)
    doc.close()

    result = ocr.ocr_document(ocr.PDF_MIME, str(pdf))

    assert result.engine == ocr.ENGINE_PDF_TEXT
    assert result.pages[0].blocks  # native PDF now carries blocks
    bbox = result.pages[0].blocks[0].bbox
    assert len(bbox) == 4 and all(len(v) == 2 for v in bbox)  # 4 (x, y) vertices
    assert "Invoice total 1240" in result.pages[0].blocks[0].text
