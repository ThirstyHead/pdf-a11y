"""Tests for deterministic tag-tree scaffolding (src/pdf_a11y/scaffold.py)."""
from pathlib import Path

from pdf_a11y.scaffold import (build_plan, extract_units, split_text_units,
                               unit_device_size)

FIX = Path(__file__).resolve().parent / "fixtures"
BREAD = FIX / "bread.pdf"


# -- BT/ET splitter (pure) ----------------------------------------------------

def test_split_simple():
    data = b"BT /F1 12 Tf (hi) Tj ET Q BT /F1 10 Tf (yo) Tj ET"
    units = split_text_units(data)
    assert len(units) == 2
    assert data[units[0]].startswith(b"BT") and data[units[0]].endswith(b"ET")


def test_split_ignores_bt_inside_string():
    data = b"BT /F1 12 Tf (ET BT ET) Tj ET"
    units = split_text_units(data)
    assert len(units) == 1


def test_split_escapes():
    data = b"BT (a\\) b) Tj ET"
    assert len(split_text_units(data)) == 1


def test_split_no_et_yields_nothing():
    assert split_text_units(b"BT /F1 12 Tf (x) Tj") == []


def test_split_ignores_hex_and_comment():
    data = b"BT <4554> (x) Tj % ET in comment\n ET"
    assert len(split_text_units(data)) == 1


def test_split_nested_parens():
    data = b"BT (a (b) c) Tj ET"
    assert len(split_text_units(data)) == 1


# -- unit metadata (size/Tm/cm + fitz Alt) -------------------------------------

def test_bread_units_have_sizes():
    units = extract_units(BREAD)
    assert units, "expected text units on bread p1"
    assert all(unit_device_size(u) > 0 for u in units)


def test_bread_headings_have_alt():
    plan = build_plan(BREAD)
    heads = [b for b in plan.blocks if b.role.startswith("H")]
    assert heads and all(b.unit.alt.strip() for b in heads)


def test_unit_size_math_scaled():
    """Tf=1, Tm scale 83, cm scale 0.24 -> 19.92 device pts (bread title)."""
    import pytest
    from pdf_a11y.scaffold import TextUnit
    u = TextUnit(page=0, start=0, end=0,
                 ctm=(0.24, 0, 0, 0.24, 18, 583.92),
                 tm=(83, 0, 0, 83, 225, 414), tf=1.0)
    assert unit_device_size(u) == pytest.approx(19.92, abs=1e-9)


# -- plan builder ---------------------------------------------------------------

def test_plan_roles_on_bread():
    plan = build_plan(BREAD)
    roles = {b.role for b in plan.blocks}
    assert "P" in roles and any(r.startswith("H") for r in roles)
    assert len({b.role for b in plan.blocks if b.role.startswith("H")}) <= 6


def test_plan_deterministic():
    p1 = build_plan(BREAD)
    p2 = build_plan(BREAD)
    assert [(b.role, b.unit.alt) for b in p1.blocks] == \
        [(b.role, b.unit.alt) for b in p2.blocks]


def test_plan_flat_all_same_size_is_all_p():
    data = (b"BT /F1 12 Tf 72 700 Td (a) Tj ET "
            b"BT /F1 12 Tf 72 680 Td (b) Tj ET")
    from pdf_a11y.scaffold import _assign_roles, TextUnit
    units = [TextUnit(page=0, start=0, end=0, ctm=(1, 0, 0, 1, 0, 0),
                      tm=(12, 0, 0, 12, 72, y), tf=1.0) for y in (700, 680)]
    roles = [b.role for b in _assign_roles(units)]
    assert roles == ["P", "P"]


# -- DocModel.build_scaffold -----------------------------------------------------

def test_build_scaffold_writes_tree_and_marked(tmp_path):
    from pdf_a11y.docmodel import DocModel
    src = BREAD
    dm = DocModel.open(src)
    plan = build_plan(src)
    by_page = plan.blocks_by_page()
    n = dm.build_scaffold(by_page)
    out = tmp_path / "scaffolded.pdf"
    dm.save(out)
    dm2 = DocModel.open(out)
    assert dm2.struct_tree() is not None and dm2.is_marked()
    bdc, emc, _ = dm2.content_bdc_counts()
    assert bdc == emc == n and n > 0
    dm2.close()
    dm.close()


# -- e2e: fix with --scaffold -----------------------------------------------------

def test_fix_bread_with_scaffold_reaches_pass(tmp_path):
    from pdf_a11y.remediate import fix_one
    from pdf_a11y.rules import AuditContext
    fr = fix_one(BREAD, tmp_path / "bread.pdf",
                 AuditContext(source_name="bread.pdf", scaffold=True))
    assert fr["status"] == "pass"
    assert fr["reaudit"]["summary"]["blocking"] == 0
    # title picked from first H1, outline derived from headings
    assert all(not f["fixable"] for f in fr["reaudit"]["findings"])


def test_fix_bread_without_scaffold_unchanged(tmp_path):
    """Library default ctx (scaffold=False) preserves pre-0.3.0 behavior:
    the untagged root cause stays unfixed, so the doc still FAILs. (The
    on-by-default decision is a CLI-level default for `fix`, not a library
    default — see the CLI tests below.)"""
    from pdf_a11y.remediate import fix_one
    fr = fix_one(BREAD, tmp_path / "b.pdf")
    assert fr["status"] == "fail"  # tag-tree finding remains manual


# -- e2e: CLI flag wiring (default-on + opt-out + back-compat) ------------------

def test_cli_fix_default_scaffolds(tmp_path):
    """CLI: `fix` with no flags scaffolds an untagged doc by default."""
    from pdf_a11y.cli import main
    out = tmp_path / "default.pdf"
    rc = main(["fix", str(BREAD), "--out", str(out)])
    assert rc == 0
    from pdf_a11y.docmodel import DocModel
    dm = DocModel.open(out)
    try:
        assert dm.struct_tree() is not None and dm.is_marked()
    finally:
        dm.close()


def test_cli_fix_no_scaffold_opt_out(tmp_path):
    """CLI: --no-scaffold preserves the opt-in (manual) behavior."""
    from pdf_a11y.cli import main
    out = tmp_path / "noscaffold.pdf"
    rc = main(["fix", str(BREAD), "--no-scaffold", "--out", str(out)])
    assert rc == 1  # untagged doc still fails (no tree built)
    from pdf_a11y.docmodel import DocModel
    dm = DocModel.open(out)
    try:
        assert dm.struct_tree() is None
    finally:
        dm.close()


def test_cli_fix_scaffold_backcompat_alias(tmp_path):
    """CLI: --scaffold still accepted (back-compat; scaffold stays on)."""
    from pdf_a11y.cli import main
    out = tmp_path / "alias.pdf"
    rc = main(["fix", str(BREAD), "--scaffold", "--out", str(out)])
    assert rc == 0
    from pdf_a11y.docmodel import DocModel
    dm = DocModel.open(out)
    try:
        assert dm.struct_tree() is not None
    finally:
        dm.close()


# -- Story-compat (1c.0 spike): per-text-object units + persistent Tf ----------
# PyMuPDF Story (and WeasyPrint) write several text objects per BT..ET and set
# the font once, then reuse it (Tf persists across BT/ET). The old one-unit-
# per-BT..ET model lost lines and defaulted inherited fonts to tf=1.0. The
# scanner must emit one unit per text-drawing op with the font in effect at
# that op. bread (1 Tm + 1 Tf per BT..ET) must come out unchanged.

def test_scan_units_splits_multiple_tm_in_one_block():
    from pdf_a11y.scaffold import _scan_units
    data = (b"BT /F0 22 Tf 1 0 0 -1 67 90 Tm (H1) Tj "
            b"/F0 16 Tf 1 0 0 -1 67 126 Tm (H2) Tj "
            b"/F1 11 Tf 1 0 0 -1 67 154 Tm (Body) Tj ET "
            b"BT 1 0 0 -1 170 321 Tm (Cell) Tj ET")
    units = _scan_units(data)
    assert len(units) == 4, units
    # font in effect at each draw op; the 4th (no Tf in its block) inherits 11
    assert [u["tf"] for u in units] == [22.0, 16.0, 11.0, 11.0]
    assert units[0]["tm"] == (1.0, 0.0, 0.0, -1.0, 67.0, 90.0)
    assert units[3]["tm"] == (1.0, 0.0, 0.0, -1.0, 170.0, 321.0)


def test_scan_units_font_persists_across_blocks():
    from pdf_a11y.scaffold import _scan_units
    data = (b"BT /F0 13 Tf 1 0 0 1 72 700 Tm (a) Tj ET "
            b"BT 1 0 0 1 72 680 Tm (b) Tj ET")
    units = _scan_units(data)
    assert [u["tf"] for u in units] == [13.0, 13.0]


def test_scan_units_bread_shape_unchanged():
    """bread writes 1 Tm + 1 Tf per BT..ET -> one unit per block, same as
    the historical BT..ET granularity (parity guard for the scanner change)."""
    from pdf_a11y.scaffold import _scan_units
    data = (b"BT /F0 2 Tf 1 0 0 83 225 414 Tm (x) TJ ET "
            b"BT /F1 1 Tf 1 0 0 50 225 311 Tm (y) Tj ET")
    units = _scan_units(data)
    assert len(units) == 2
    assert [u["tf"] for u in units] == [2.0, 1.0]


def test_bread_unit_count_parity():
    """The per-text-object scanner must not change bread's unit count."""
    units = extract_units(BREAD)
    assert len(units) == 75
    assert all(unit_device_size(u) > 0 for u in units)


def test_story_pdf_build_plan(tmp_path):
    """End-to-end: a real PyMuPDF Story PDF scaffolds with the H1 detected as
    a headed block (alt filled) and body as P, and no 1.0pt phantom units."""
    import pymupdf as fitz
    out = tmp_path / "story.pdf"
    A4 = fitz.paper_rect("a4")
    html = ("<h1>Report Title</h1>"
            "<p>Some body text here for the perceivable section.</p>")
    css = ("body{font-family:sans-serif;font-size:11pt;color:#000}"
           "h1{font-size:22pt}")
    story = fitz.Story(html=html, user_css=css)
    writer = fitz.DocumentWriter(str(out))
    more = 1
    while more:
        dev = writer.begin_page(A4)
        more, _ = story.place(A4)
        story.draw(dev)
        writer.end_page()
    writer.close()
    plan = build_plan(out)
    heads = [b for b in plan.blocks if b.role.startswith("H")]
    assert heads, "expected a heading from the <h1>"
    assert any("Report Title" in b.unit.alt for b in heads)
    assert any(b.role == "P" for b in plan.blocks)
    assert all(unit_device_size(b.unit) > 0.5 for b in plan.blocks)