"""Tests for the geometric reading-order rule (SC 1.3.1).

Layered:
  * pure-geometry unit tests on synthetic ``Line`` tuples (no PDF needed);
  * PDF-level tests that build real fixtures with PyMuPDF in ``tmp_path``
    (hermetic; nothing committed);
  * rule-integration tests that run the full audit and assert the new
    ``reading-order-broken`` finding fires on a scrambled document and does
    NOT fire on in-order or legitimate two-column documents.
"""
import fitz  # PyMuPDF

from pdf_a11y import readingorder as ro
from pdf_a11y.audit import audit_file
from pdf_a11y.rules import AuditContext

# Lines are plain (text, x0, x1, y) tuples.


# ---------------------------------------------------------------------------
# pure geometry: inversions
# ---------------------------------------------------------------------------

def test_inversions_identity_zero():
    assert ro.count_inversions([0, 1, 2, 3], [0, 1, 2, 3]) == 0


def test_inversions_single_adjacent_swap_is_one():
    # one adjacent swap => exactly 1 inversion (the tolerated amount)
    assert ro.count_inversions([0, 2, 1, 3], [0, 1, 2, 3]) == 1


def test_inversions_three_way_scramble():
    # visual 0,1,2,3 ; stream 2,0,3,1 -> pairs inverted: (2,0),(2,1),(3,1) = 3
    assert ro.count_inversions([2, 0, 3, 1], [0, 1, 2, 3]) == 3


def test_inversions_full_reverse():
    n = 5
    assert ro.count_inversions(list(range(n - 1, -1, -1)), list(range(n))) == n * (n - 1) // 2


def test_inversions_symmetric_under_visual_ordering():
    # inversions are about the *relative* order; permuting both the same way
    # (i.e. re-indexing) must not change the count.
    stream = [2, 0, 3, 1]
    visual = [1, 3, 0, 2]
    assert ro.count_inversions(stream, visual) == ro.count_inversions(
        [visual.index(s) for s in stream], list(range(4)))


# ---------------------------------------------------------------------------
# pure geometry: visual order / column bands
# ---------------------------------------------------------------------------

def test_visual_order_single_column_top_to_bottom():
    lines = [("a", 50, 120, 100), ("b", 50, 120, 40), ("c", 50, 120, 70)]
    assert ro.visual_order(lines) == [1, 2, 0]   # b(40), c(70), a(100)


def test_visual_order_two_columns_left_to_right():
    # left column x~50, right column x~300
    lines = [
        ("L1", 50, 120, 40), ("R1", 300, 370, 40),
        ("L2", 50, 120, 70), ("R2", 300, 370, 70),
    ]
    assert ro.visual_order(lines) == [0, 2, 1, 3]   # L1, L2, R1, R2 (col-aware)


def test_visual_order_two_columns_column_aware_not_y_aware():
    # Right column's top line is HIGHER than the left column's bottom line.
    # A naive y-sort would interleave the columns; column-aware must read the
    # whole left column before the whole right column.
    lines = [
        ("L1", 50, 120, 40),    # left top
        ("R1", 300, 370, 30),   # right top (higher than L2)
        ("L2", 50, 120, 90),    # left bottom (lower than R1)
        ("R2", 300, 370, 60),
    ]
    assert ro.visual_order(lines) == [0, 2, 1, 3]   # L1, L2, R1, R2


def test_column_bands_single():
    lines = [("a", 50, 120, 40), ("b", 55, 130, 70)]
    assert len(ro.column_bands(lines)) == 1


def test_column_bands_two():
    lines = [("a", 50, 120, 40), ("b", 300, 370, 40),
             ("c", 52, 122, 70), ("d", 302, 372, 70)]
    assert len(ro.column_bands(lines)) == 2


# ---------------------------------------------------------------------------
# PDF-level: real fixtures, content-stream order vs visual
# ---------------------------------------------------------------------------

def test_extract_lines_returns_stream_order(tmp_path):
    p = str(tmp_path / "s.pdf")
    # write "First" at y=10, "Second" at y=40, but write Second FIRST in the
    # content stream so stream order != visual order.
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    page.insert_text((20, 40), "Second")
    page.insert_text((20, 10), "First")
    d.save(p); d.close()
    lines = ro.extract_lines(p, 0)
    assert [t for t, *_ in lines] == ["Second", "First"]


def test_in_order_document_zero_inversions(tmp_path):
    p = str(tmp_path / "ok.pdf")
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    for i, y in enumerate((10, 40, 70, 100)):
        page.insert_text((20, y), f"Line {i}")
    d.save(p); d.close()
    rep = ro.reading_order_report(p, tolerance=1)
    assert rep and rep[0].inversions == 0 and rep[0].streams_ok


def test_scrambled_document_fires(tmp_path):
    p = str(tmp_path / "bad.pdf")
    # visual order (by y): A(10) B(40) C(70) D(100)
    # write in scrambled stream order C, A, D, B  -> >= 2 inversions
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    for (text, y) in [("C", 70), ("A", 10), ("D", 100), ("B", 40)]:
        page.insert_text((20, y), text)
    d.save(p); d.close()
    rep = ro.reading_order_report(p, tolerance=1)
    assert rep and rep[0].inversions >= 2 and not rep[0].streams_ok


def test_table_row_not_misread_as_columns(tmp_path):
    # Single-column doc containing a two-cell "row" (Cell one ... Cell two)
    # with a wide inter-cell gap, plus a full-width line above it. The full
    # line bridges the gap, so the union is continuous -> ONE band, 0
    # inversions (no false positive from the column detector).
    p = str(tmp_path / "table.pdf")
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    page.insert_text((20, 10), "Body paragraph text.")   # full-width-ish
    page.insert_text((20, 60), "Cell one")              # left cell
    page.insert_text((160, 60), "Cell two")             # right cell (gap>18)
    d.save(p); d.close()
    rep = ro.reading_order_report(p, tolerance=1)
    assert rep and rep[0].inversions == 0 and rep[0].streams_ok


def test_two_column_in_reading_order_not_false_positive(tmp_path):
    # A correctly-authored two-column doc: left column top->bottom, then right
    # column top->bottom. Must measure 0 inversions (no false positive).
    p = str(tmp_path / "cols.pdf")
    d = fitz.open()
    page = d.new_page(width=612, height=792)
    for i, y in enumerate((30, 60, 90)):
        page.insert_text((50, y), f"L{i}")     # left column
    for i, y in enumerate((30, 60, 90)):
        page.insert_text((320, y), f"R{i}")    # right column
    d.save(p); d.close()
    rep = ro.reading_order_report(p, tolerance=1)
    assert rep and rep[0].inversions == 0 and rep[0].streams_ok


# ---------------------------------------------------------------------------
# rule integration: full audit
# ---------------------------------------------------------------------------

def test_audit_scrambled_reports_reading_order(tmp_path):
    p = str(tmp_path / "bad.pdf")
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    for (text, y) in [("C", 70), ("A", 10), ("D", 100), ("B", 40)]:
        page.insert_text((20, y), text)
    d.save(p); d.close()
    result = audit_file(p, AuditContext())
    ro = [f for f in result["findings"] if f["rule_id"] == "reading-order"]
    assert len(ro) == 1, f"expected exactly 1 reading-order finding, got {len(ro)}"
    assert ro[0]["location"] == "page[0]", f"wrong page: {ro[0]['location']}"
    assert ro[0]["sc"] == "1.3.1"


def test_audit_in_order_does_not_report_reading_order(tmp_path):
    p = str(tmp_path / "ok.pdf")
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    for i, y in enumerate((10, 40, 70, 100)):
        page.insert_text((20, y), f"Line {i}")
    d.save(p); d.close()
    result = audit_file(p, AuditContext())
    rules = {f["rule_id"] for f in result["findings"]}
    assert "reading-order" not in rules


def test_reading_order_is_deterministic(tmp_path):
    # Same input -> byte-identical finding set (rule is pure geometry).
    p = str(tmp_path / "bad.pdf")
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    for (text, y) in [("C", 70), ("A", 10), ("D", 100), ("B", 40)]:
        page.insert_text((20, y), text)
    d.save(p); d.close()
    a = audit_file(p, AuditContext())
    b = audit_file(p, AuditContext())
    fa = sorted((f for f in a["findings"] if f["rule_id"] == "reading-order"),
                key=lambda f: f["location"])
    fb = sorted((f for f in b["findings"] if f["rule_id"] == "reading-order"),
                key=lambda f: f["location"])
    assert fa and fa == fb


def test_tolerance_zero_fires_on_single_swap(tmp_path):
    # A single adjacent swap = 1 inversion: tolerated at the default tolerance
    # (1) but reported when tolerance is tightened to 0.
    p = str(tmp_path / "swap.pdf")
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    # visual order (by y): A(10) B(40) C(70); write A, C, B (one adjacent swap)
    page.insert_text((20, 10), "A")
    page.insert_text((20, 70), "C")
    page.insert_text((20, 40), "B")
    d.save(p); d.close()
    lax = audit_file(p, AuditContext(reading_order_tolerance=1))
    strict = audit_file(p, AuditContext(reading_order_tolerance=0))
    assert not any(f["rule_id"] == "reading-order" for f in lax["findings"])
    assert any(f["rule_id"] == "reading-order" for f in strict["findings"])


def test_audit_two_column_in_order_not_reported(tmp_path):
    p = str(tmp_path / "cols.pdf")
    d = fitz.open()
    page = d.new_page(width=612, height=792)
    for i, y in enumerate((30, 60, 90)):
        page.insert_text((50, y), f"L{i}")
    for i, y in enumerate((30, 60, 90)):
        page.insert_text((320, y), f"R{i}")
    d.save(p); d.close()
    result = audit_file(p, AuditContext())
    rules = {f["rule_id"] for f in result["findings"]}
    assert "reading-order" not in rules
