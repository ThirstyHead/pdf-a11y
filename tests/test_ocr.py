"""OCR of text-less pages (Phase A). Pluggable, opt-in, graceful.

The graceful-degradation test ALWAYS runs (no tesseract needed) by monkeypatching
ocr_available(). The real text-layer test skips when tesseract is absent so CI
stays hermetic.
"""
from pathlib import Path

import fitz
import pytest

from pdf_a11y import ocr
from pdf_a11y.ocr import _render_dpi

FIXTURES = Path(__file__).parent / "fixtures"


def test_ocr_available_is_bool(monkeypatch):
    assert ocr.ocr_available() in (True, False)


def test_ocr_prepare_degrades_when_unavailable(monkeypatch):
    src = FIXTURES / "scan.pdf"
    monkeypatch.setattr(ocr, "ocr_available", lambda: False)
    path, n, note = ocr.ocr_prepare(src)
    assert path == src          # original file used, no OCR'd copy
    assert n == 0
    assert "OCR unavailable" in note


def test_ocr_noop_when_all_pages_have_text(monkeypatch):
    src = FIXTURES / "clean.pdf"        # has extractable text
    monkeypatch.setattr(ocr, "ocr_available", lambda: True)
    path, n, note = ocr.ocr_prepare(src)
    assert n == 0 and "no OCR needed" in note


def _fullbleed_scan(dpi: float):
    """1-page doc: single full-bleed raster at native `dpi` (no text).

    Raster is built with a PyMuPDF Pixmap — the most direct way to make a
    full-bleed image (and avoids a PIL encode round-trip)."""
    w, h = int(612 * dpi // 72), int(792 * dpi // 72)
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    pm = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, w, h), 0)
    pm.clear_with(255)
    p.insert_image(p.rect, pixmap=pm)
    return doc[0]


def test_render_dpi_never_exceeds_native_raster():
    """Regression: upsampling a scan's raster softens it and breaks tesseract.

    The render dpi clamps to the full-bleed raster's native density: no
    upscaling below 300, no pointless 3x render above 300, 300 target when the
    page has no raster (vector content)."""
    assert _render_dpi(_fullbleed_scan(72)) == 72      # no 4.2x upscale (the bug)
    assert _render_dpi(_fullbleed_scan(150)) == 150
    assert _render_dpi(_fullbleed_scan(600)) == 300    # hi-dpi: capped, not upscaled
    assert _render_dpi(fitz.open().new_page()) == 300  # no raster -> target

TESS = pytest.mark.skipif(not ocr.ocr_available(),
                          reason="tesseract/pytesseract not installed")


def _make_scan_in_text_image(tmp_path):
    """A 1-page PDF whose single page is an *image* of the words 'hello world'
    (no extractable text). Hermetic: built from vector text, rendered to a raster."""
    src = fitz.open()
    p = src.new_page()
    p.insert_text((72, 72), "hello world", fontsize=48)
    pix = p.get_pixmap(dpi=200)
    scan = fitz.open()
    sp = scan.new_page(width=pix.width, height=pix.height)
    sp.insert_image(sp.rect, stream=pix.tobytes("png"))
    path = tmp_path / "scanned-in.pdf"
    scan.save(str(path)); src.close(); scan.close()
    return path


@TESS
def test_ocr_adds_invisible_text_layer(tmp_path):
    src = _make_scan_in_text_image(tmp_path)
    path, n, note = ocr.ocr_prepare(src, workdir=tmp_path)
    assert n == 1
    out = fitz.open(str(path))
    recovered = out[0].get_text().lower()
    out.close()
    assert "hello" in recovered and "world" in recovered
