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
    from pdf_a11y.remediate import fix_one
    fr = fix_one(BREAD, tmp_path / "b.pdf")
    assert fr["status"] == "fail"  # opt-in: default behavior untouched