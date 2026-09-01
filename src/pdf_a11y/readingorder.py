"""Geometric reading-order validation for the reading-order rule (SC 1.3.1).

This module answers one question with pure, unit-testable geometry: does the
order in which text is written into the PDF content stream match the order a
reader would expect to see it (left-to-right, top-to-bottom, column-aware)?

Design
------
* **Stream order** is read straight from the content stream via PyMuPDF
  ``page.get_text("dict")``: the blocks come back in content-stream (draw)
  order. This is the side the old stream-order assumption got wrong — it never
  actually asked what order the text was *written* in.
* **Visual order** is computed geometrically: the page is split into left-to-
  right *column bands* (a band boundary is a horizontal "gutter" — a strip no
  line of text spans, found as a gap in the union of the lines' x-spans), and
  within each band lines are ordered top-to-bottom. Bands are then read left
  to right. A single-column page collapses to plain top-to-bottom. The union
  test (rather than a raw gap between line left-edges) means a table row's
  inter-cell gap is bridged by a full-width line and not mistaken for columns.
* The **divergence** between the two orders is an **inversion count**: how
  many pairs of lines appear in the opposite relative order in stream vs
  visual. A document that writes text in reading order has 0 inversions.

Why PyMuPDF (fitz) for both sides: a single library yields both the stream
order and the geometry in the *same* coordinate system, so the two line lists
are trivially aligned (same index set, same page). pdfplumber remains a
declared dependency for the text-spacing rule (Step 3); the plan permits
"pdfplumber/fitz" for this geometric check and fitz is the more robust choice
here (it reports draw order directly, while pdfplumber normalizes to visual
order and would hide the very thing we are measuring).

Everything in this module is deterministic and free of network/AI. The rule
itself (in ``rules.py``) decides *whether* a divergence is a finding, using a
configurable **tolerance** (default 1, i.e. one adjacent swap is tolerated so
benign micro-reordering does not flag).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

# A "line" as seen by this module: a piece of text with its geometry.
# ``y`` is the top of the line in PDF points (origin top-left, y increasing
# downward) as returned by PyMuPDF's text dict; ``x0``/``x1`` are the left and
# right edges of the line's bounding box.
Line = Tuple[str, float, float, float]   # (text, x0, x1, y)


@dataclass
class ReadingPage:
    """One page's reading-order measurement."""
    page_no: int          # 0-based
    n_lines: int
    inversions: int       # 0 = stream order already matches visual order
    streams_ok: bool      # inversions <= tolerance


def _to_line_tuple(block_lines: Sequence) -> List[Line]:
    """Flatten a PyMuPDF line entry into our (text, x0, x1, y) Line."""
    out: List[Line] = []
    for ln in block_lines:
        spans = ln.get("spans") or []
        text = "".join(s.get("text", "") for s in spans).strip()
        if not text:
            continue
        bbox = ln.get("bbox") or (0, 0, 0, 0)
        out.append((text, float(bbox[0]), float(bbox[2]), float(bbox[1])))
    return out


def _lines_from_dict(d) -> List[Line]:
    """Flatten a PyMuPDF ``get_text("dict")`` result into ``Line`` tuples in
    content-stream (draw) order. Non-text blocks (images, etc.) are skipped.
    """
    blocks = d.get("blocks") or [] if isinstance(d, dict) else []
    lines: List[Line] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type", 0) != 0:      # 0 = text block; skip images etc.
            continue
        lines.extend(_to_line_tuple(block.get("lines") or []))
    return lines


def extract_lines(path: str, page_no: int = 0) -> List[Line]:
    """Return the text lines of ``page_no`` in **content-stream order**.

    Each line is ``(text, x0, x1, y)``. Text order follows the order the
    producer wrote the text operators into the content stream (PyMuPDF
    reports blocks in draw order), NOT geometric order — that is exactly the
    axis we validate.
    """
    import fitz  # local import: PyMuPDF is already a hard dependency
    doc = fitz.open(str(path))
    try:
        if page_no < 0 or page_no >= doc.page_count:
            return []
        return _lines_from_dict(doc[page_no].get_text("dict"))
    finally:
        doc.close()


def column_bands(lines: Sequence[Line],
                 gap: float = 18.0) -> List[Tuple[float, float]]:
    """Cluster lines into left-to-right column bands.

    A *column gutter* is a horizontal strip that no line of text spans — i.e. a
    gap in the **union** of the lines' horizontal spans. We merge all line
    spans into union intervals, then any gap between consecutive intervals that
    is at least ``gap`` points wide is a gutter; the bands are the text regions
    between gutters. A single-column page yields one band.

    This is deliberately more conservative than "split on a big x-gap between
    line left-edges": a table row such as ``Cell one … Cell two`` has a wide
    gap between the two cells, but the full-width line above or below it
    *bridges* that gap, so the union is continuous and no gutter is detected.
    Only a genuine vertical clear strip (real columns) produces a gutter.

    Returns a list of ``(band_x0, band_x1)`` sorted left to right.
    """
    if not lines:
        return []
    # Merge all line spans into union intervals along x (y is irrelevant here).
    spans = sorted((l[1], l[2]) for l in lines)          # (x0, x1)
    merged: List[List[float]] = []
    for x0, x1 in spans:
        if not merged or x0 > merged[-1][1]:             # disjoint (allow touching)
            merged.append([x0, x1])
        else:
            merged[-1][1] = max(merged[-1][1], x1)
    if not merged:
        return []

    # Build bands: group consecutive union segments, cutting wherever a gutter
    # (a >= gap gap between two adjacent segments) occurs.
    bands: List[Tuple[float, float]] = []
    cur = [merged[0]]
    for i in range(len(merged) - 1):
        if merged[i + 1][0] - merged[i][1] >= gap:     # gutter -> cut
            bands.append((cur[0][0], cur[-1][1]))
            cur = [merged[i + 1]]
        else:
            cur.append(merged[i + 1])
    bands.append((cur[0][0], cur[-1][1]))
    return bands


def _band_of(x_center: float, bands: Sequence[Tuple[float, float]]) -> int:
    """Index of the band whose span contains ``x_center`` (nearest if none)."""
    best, bestd = 0, float("inf")
    for i, (b0, b1) in enumerate(bands):
        if b0 <= x_center <= b1:
            return i
        d = min(abs(x_center - b0), abs(x_center - b1))
        if d < bestd:
            bestd, best = d, i
    return best


def visual_order(lines: Sequence[Line]) -> List[int]:
    """Indices of ``lines`` in reading (visual) order.

    Reading order = for each column band left-to-right, lines in that band
    top-to-bottom (by y, ties broken by x). This is the order a sighted
    reader expects.
    """
    n = len(lines)
    if n <= 1:
        return list(range(n))
    bands = column_bands(lines)
    if not bands:
        # Fallback: plain top-to-bottom.
        return sorted(range(n), key=lambda i: (lines[i][3], lines[i][1]))
    # Bucket line indices by band (by horizontal center).
    by_band: dict = {i: [] for i in range(len(bands))}
    for i, (_t, x0, x1, y) in enumerate(lines):
        by_band[_band_of((x0 + x1) / 2.0, bands)].append(i)
    order: List[int] = []
    for bi in range(len(bands)):            # left -> right
        order.extend(sorted(by_band[bi],
                            key=lambda i: (lines[i][3], lines[i][1])))   # top -> bottom
    return order


def count_inversions(stream: Sequence[int], visual: Sequence[int]) -> int:
    """Number of pairs of lines whose relative order differs between
    ``stream`` (content-stream order) and ``visual`` (reading order).

    0 means the content stream already presents the lines in reading order.
    Both inputs are permutations of the same index set.
    """
    pos = {idx: rank for rank, idx in enumerate(visual)}
    a = [pos[i] for i in stream]
    return _count_inv(a)


def _count_inv(a: Sequence[int]) -> int:
    """Inversion count via merge sort (O(n log n), deterministic)."""
    def sort_count(seq):
        if len(seq) <= 1:
            return seq, 0
        mid = len(seq) // 2
        left, lc = sort_count(seq[:mid])
        right, rc = sort_count(seq[mid:])
        merged, inv = [], 0
        i = j = 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                merged.append(left[i]); i += 1
            else:
                merged.append(right[j]); j += 1
                inv += len(left) - i
        merged.extend(left[i:]); merged.extend(right[j:])
        return merged, inv + lc + rc
    _, inv = sort_count(list(a))
    return inv


def reading_order_report(path: str, tolerance: int = 1,
                         pages: Optional[Sequence[int]] = None,
                         max_pages: int = 200) -> List[ReadingPage]:
    """Measure reading-order divergence for the given pages (all by default).

    ``tolerance`` is the maximum inversion count considered acceptable
    (default 1 = one adjacent swap tolerated). A page is ``streams_ok`` when
    its inversion count is <= tolerance.
    """
    import fitz  # local import
    doc = fitz.open(str(path))
    try:
        total = doc.page_count
    except Exception:
        return []
    if pages is None:
        idxs = list(range(total))
    else:
        idxs = [p for p in pages if 0 <= p < total]
    out: List[ReadingPage] = []
    for p in idxs[:max_pages]:
        try:
            lines = _lines_from_dict(doc[p].get_text("dict"))
        except Exception:
            continue
        if len(lines) < 2:
            out.append(ReadingPage(p, len(lines), 0, True))
            continue
        stream = list(range(len(lines)))
        visual = visual_order(lines)
        inv = count_inversions(stream, visual)
        out.append(ReadingPage(p, len(lines), inv, inv <= tolerance))
    doc.close()
    return out
