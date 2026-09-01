"""Per-page text-spacing measurements for the ``text-spacing`` rule (SC 1.4.12).

WCAG 1.4.12 (Text Spacing) is an *override* criterion: the user must be able to
*set* line height to 1.5x, word spacing to 0.26em (0.12em for CJK), and letter
spacing to 0.05em without loss of content. Those are targets the user can reach,
NOT minimums that as-rendered content must meet — virtually all normal text
renders with line height ~1.2-1.5x and word spacing ~0.2em, so a literal
"flag if below 1.5x" rule would flag every ordinary document.

This module therefore measures the three spacings and reports the *minimum*
(observed) value on each page plus the offending text, so the rule can flag
only **genuinely cramped** rendering (conservative lower bounds, see
``AuditContext.text_spacing_*``):

  * ``line height``  - baseline gap / font size (dimensionless ratio)
  * ``word spacing`` - gap between adjacent words / font size (em)
  * ``letter spacing``- gap between adjacent letters within a word / font size
                       (em; normal kerning dips slightly negative)

All measurements are deterministic pure geometry over PyMuPDF text extraction
(no network, no AI).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

# Default conservative lower bounds (see module docstring for why these are far
# below the WCAG 1.4.12 override targets). A page is only flagged when its
# minimum observed spacing falls below the matching bound.
DEFAULT_LINE_MIN = 1.0     # flag line height tighter than 1.0x font size
DEFAULT_WORD_MIN = 0.08    # flag word gaps tighter than 0.08em
DEFAULT_LETTER_MIN = -0.12  # flag letter overlap beyond normal kerning (-0.12em)


@dataclass
class PageSpacing:
    """Minimum observed spacing metrics for one page.

    ``None`` in any field means the metric could not be measured on that page
    (fewer than two lines, no words, or no within-word letter pairs).
    """
    page_no: int
    min_line_height: Optional[float] = None
    line_height_text: str = ""
    min_word_gap: Optional[float] = None
    word_gap_text: str = ""
    min_letter_gap: Optional[float] = None
    letter_gap_text: str = ""


def _line_heights(page) -> Tuple[Optional[float], str]:
    """Return ``(min_ratio, text_of_that_line)`` across all lines that have a
    preceding line in the same block (ratio = baseline gap / current line size).
    """
    best: Optional[float] = None
    best_text = ""
    d = page.get_text("dict")
    blocks = d.get("blocks") or [] if isinstance(d, dict) else []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != 0:
            continue
        lines = block.get("lines") or []
        prev_y: Optional[float] = None
        for ln in lines:
            spans = ln.get("spans") or []
            if not spans:
                continue
            spans = [s for s in spans if isinstance(s, dict)]
            if not spans:
                continue
            oy = spans[0].get("origin", (0, 0))[1]
            size = max(s.get("size", 0) for s in spans)
            text = "".join(s.get("text", "") for s in spans).strip()
            if prev_y is not None and size > 0:
                gap = oy - prev_y
                if gap > 0:
                    ratio = gap / size
                    if best is None or ratio < best:
                        best = ratio
                        best_text = text
            prev_y = oy
    return best, best_text


def _word_and_letter_gaps(page) -> Tuple[Optional[float], str, Optional[float], str]:
    """Return ``(min_word_gap, word_text, min_letter_gap, letter_text)`` using
    character-level bboxes from the raw text dict.
    """
    min_word: Optional[float] = None
    word_text = ""
    min_letter: Optional[float] = None
    letter_text = ""
    rd = page.get_text("rawdict")
    blocks = rd.get("blocks") or [] if isinstance(rd, dict) else []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != 0:
            continue
        for ln in block.get("lines") or []:
            if not isinstance(ln, dict):
                continue
            for span in ln.get("spans") or []:
                if not isinstance(span, dict):
                    continue
                chars = span.get("chars") or []
                fs = span.get("size", 0)
                if not chars or fs <= 0:
                    continue
                chars = sorted(chars, key=lambda c: c["bbox"][0])
                text = "".join(c.get("c", "") for c in chars)
                if not text.strip():
                    continue
                # --- word gaps: segment into words (breaks on spaces) ---
                words: List[List[dict]] = []
                cur: List[dict] = []
                for c in chars:
                    if c.get("c") == " ":
                        if cur:
                            words.append(cur)
                            cur = []
                    else:
                        cur.append(c)
                if cur:
                    words.append(cur)
                for i in range(len(words) - 1):
                    a = words[i][-1]["bbox"][2]
                    b = words[i + 1][0]["bbox"][0]
                    gap = (b - a) / fs
                    if min_word is None or gap < min_word:
                        min_word = gap
                        word_text = text
                # --- letter gaps: adjacent non-space chars within a word ---
                for i in range(len(chars) - 1):
                    c1, c2 = chars[i], chars[i + 1]
                    if c1.get("c") == " " or c2.get("c") == " ":
                        continue
                    gap = (c2["bbox"][0] - c1["bbox"][2]) / fs
                    if min_letter is None or gap < min_letter:
                        min_letter = gap
                        letter_text = text
    return min_word, word_text, min_letter, letter_text


def spacing_report(path: str) -> List[PageSpacing]:
    """Measure per-page minimum spacings for the PDF at ``path``.

    Returns one :class:`PageSpacing` per page. Raises on an unreadable PDF; the
    caller (the rule) is expected to degrade gracefully.
    """
    import fitz  # PyMuPDF (local import keeps module import cheap/testable)

    doc = fitz.open(path)
    try:
        out: List[PageSpacing] = []
        for pno in range(doc.page_count):
            page = doc[pno]
            lh, lh_text = _line_heights(page)
            wg, wg_text, lg, lg_text = _word_and_letter_gaps(page)
            out.append(PageSpacing(
                page_no=pno,
                min_line_height=lh,
                line_height_text=lh_text,
                min_word_gap=wg,
                word_gap_text=wg_text,
                min_letter_gap=lg,
                letter_gap_text=lg_text,
            ))
        return out
    finally:
        doc.close()


def measure(page) -> PageSpacing:
    """Measure spacing for a single open PyMuPDF ``page`` (test helper)."""
    lh, lh_text = _line_heights(page)
    wg, wg_text, lg, lg_text = _word_and_letter_gaps(page)
    return PageSpacing(
        page_no=0,
        min_line_height=lh,
        line_height_text=lh_text,
        min_word_gap=wg,
        word_gap_text=wg_text,
        min_letter_gap=lg,
        letter_gap_text=lg_text,
    )
