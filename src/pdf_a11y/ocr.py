"""Optional OCR of scanned (text-less) pages. Pluggable, opt-in, file-level.

Operates on a PDF *file* (via PyMuPDF) and, when a backend is present and some page
lacks extractable text, writes an OCR'd copy (invisible text layer, render_mode=3) to a
temp path. `fix --ocr` calls ``ocr_prepare(src)`` and runs the rest of the pipeline on the
returned path. Keeping OCR file-level and orthogonal to the pikepdf remediation engine
keeps it deterministic given a backend and makes graceful degradation trivial.

Contract (mirrors the opt-in/oracle graceful-degradation pattern):
  * ``ocr_available()`` False  -> callers print an actionable note and continue WITHOUT OCR.
    Never a traceback.
  * OCR is marked OCR-derived by the caller (the fix result gains ``"ocr": true``).
"""
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Optional, Tuple


def ocr_available() -> bool:
    """True when the default backend (tesseract + pytesseract + Pillow) is usable."""
    if not shutil.which("tesseract"):
        return False
    try:
        import pytesseract  # noqa: F401
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def _page_has_text(page) -> bool:
    return bool(page.get_text().strip())


def _render_dpi(page, target: float = 300.0) -> int:
    """Render dpi that never upsamples the page's raster.

    A scanned page is normally one full-bleed image whose pixel density IS the
    document's native resolution. Rendering above that only interpolates
    (softens) the image, which measurably degrades OCR accuracy (tesseract 5.5.3
    misread 'hello' as 'nello' at a 4.17x upsample vs. clean at native). Vector
    or image-less pages have no raster to protect: render at the target.
    Deterministic: derived purely from document geometry.
    """
    try:
        rect = page.rect
        if rect.is_empty or rect.width <= 0 or rect.height <= 0:
            return int(target)
        best = None
        for img in page.get_images(full=True):
            xref = img[0]
            pw, ph = img[2], img[3]
            if pw <= 0 or ph <= 0:
                continue
            for r in page.get_image_rects(xref):
                if r.width <= 0 or r.height <= 0:
                    continue
                # Only images that cover (most of) the page set the native dpi.
                if r.width * r.height < 0.5 * rect.width * rect.height:
                    continue
                dpi = 72.0 * pw / r.width
                if best is None or dpi > best:
                    best = dpi
        if best is None:
            return int(target)
        return int(round(min(target, max(72.0, best))))
    except Exception:
        return int(target)


def _ocr_page(page) -> int:
    """Add an invisible text layer to one text-less page. Returns chars inserted."""
    from PIL import Image
    import pytesseract

    dpi = _render_dpi(page)
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    lines = defaultdict(list)
    for i, word in enumerate(d["text"]):
        if not word.strip():
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        lines[key].append((d["left"][i], d["top"][i], word.strip()))
    scale = 72.0 / dpi
    n = 0
    for _, words in sorted(lines.items()):
        words.sort()
        x = min(w[0] for w in words) * scale
        y = min(w[1] for w in words) * scale
        text = " ".join(w[2] for w in words)
        page.insert_text((x, y + 4), text, fontsize=9, render_mode=3, fontname="helv")
        n += len(text)
    return n


def ocr_prepare(src, workdir: Optional[Path] = None) -> Tuple[Path, int, str]:
    """Return ``(path_to_audit, n_pages_ocrd, note)``.

    - backend unavailable            -> ``(src, 0, "OCR unavailable: ...")``
    - available, no text-less pages  -> ``(src, 0, "no OCR needed ...")``
    - available, some text-less      -> ``(tmp_copy, n, "OCR added ... n page(s)")``
    """
    import fitz
    src = Path(src)
    if not ocr_available():
        return src, 0, ("OCR unavailable: install `tesseract` (apt/brew) and "
                        "`pip install pdf-a11y[ocr]`; continuing without OCR.")
    doc = fitz.open(str(src))
    try:
        textless = [i for i in range(doc.page_count) if not _page_has_text(doc[i])]
        if not textless:
            return src, 0, "no OCR needed (every page already has extractable text)"
        for i in textless:
            _ocr_page(doc[i])
        wd = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="pdf-a11y-ocr-"))
        wd.mkdir(parents=True, exist_ok=True)
        out = wd / (src.stem + ".ocr.pdf")
        doc.save(str(out))
        return out, len(textless), f"OCR added a text layer to {len(textless)} page(s)"
    finally:
        doc.close()
