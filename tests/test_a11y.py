"""End-to-end tests for pdf-a11y (committed fixtures under tests/fixtures/)."""
from pathlib import Path

import pytest

from pdf_a11y.audit import audit_file
from pdf_a11y.contrast import contrast_ratio, hex_to_rgb

FIX = Path(__file__).resolve().parent / "fixtures"


def _ids(result):
    return {f["rule_id"] for f in result["findings"]}


# -- contrast math -----------------------------------------------------------

def test_contrast_black_on_white():
    assert contrast_ratio(hex_to_rgb("000000"), hex_to_rgb("FFFFFF")) == pytest.approx(21.0, abs=0.05)


def test_contrast_e8e8e8_on_white_fails():
    r = contrast_ratio(hex_to_rgb("E8E8E8"), hex_to_rgb("FFFFFF"))
    assert r < 4.5 and r == pytest.approx(1.23, abs=0.05)


def test_contrast_red_on_white_fails_45():
    r = contrast_ratio(hex_to_rgb("FF0000"), hex_to_rgb("FFFFFF"))
    assert r == pytest.approx(4.0, abs=0.05) and r < 4.5


# -- characterization: exact finding sets on committed fixtures --------------

def test_clean_passes():
    res = audit_file(FIX / "clean.pdf")
    assert res["summary"]["pass"] is True
    assert res["summary"]["total"] == 0


def test_fixable_finding_set():
    res = audit_file(FIX / "fixable.pdf")
    # Unmarked-but-treeless is reported once, by pdf-unmarked (not twice).
    assert _ids(res) == {"image-alt-missing", "pdf-unmarked",
                         "language-missing", "title-missing", "display-doctitle-off",
                         "outline-missing"}
    assert res["summary"]["pass"] is False


def test_untagged_single_131_finding():
    res = audit_file(FIX / "fixable.pdf")
    c131 = [f for f in res["findings"] if f["sc"] == "1.3.1"]
    assert len(c131) == 1
    assert c131[0]["rule_id"] == "pdf-unmarked"


def test_marked_notree_single_131():
    res = audit_file(FIX / "marked-notree.pdf")
    assert _ids(res) == {"image-alt-missing", "tag-tree-missing",
                         "language-missing", "title-missing",
                         "display-doctitle-off", "outline-missing"}
    c131 = [f for f in res["findings"] if f["sc"] == "1.3.1"]
    assert len(c131) == 1
    assert c131[0]["rule_id"] == "tag-tree-missing"


def test_violations_weak_tree():
    res = audit_file(FIX / "violations.pdf")
    assert _ids(res) <= {"tag-tree-weak"}
    assert len(res["findings"]) == 2  # heading level skip + table without TH
    assert res["summary"]["pass"] is False


# -- Phase 3: honest fixable flag for outline-missing -------------------------

def test_outline_missing_unfixable_by_default():
    """No tag tree, no --outline-map: the fix cannot succeed, so the finding
    must report fixable=False (previously True, silently left unfixed)."""
    res = audit_file(FIX / "fixable.pdf")
    om = [f for f in res["findings"] if f["rule_id"] == "outline-missing"]
    assert len(om) == 1
    assert om[0]["fixable"] is False


def test_outline_missing_fixable_with_tree():
    """Tagged doc with headings but no outline: derivable from the tag tree."""
    res = audit_file(FIX / "tagged-nooutline.pdf")
    assert _ids(res) == {"outline-missing"}
    assert res["findings"][0]["fixable"] is True


def test_outline_missing_fixable_with_outline_map():
    from pdf_a11y.rules import AuditContext
    res = audit_file(FIX / "fixable.pdf",
                     AuditContext(source_name="fixable.pdf",
                                  outline_map=[(1, "Big Title", 0)]))
    om = [f for f in res["findings"] if f["rule_id"] == "outline-missing"]
    assert om[0]["fixable"] is True


def test_fix_one_tagged_nooutline_reaches_pass(tmp_path):
    """A doc whose only finding is outline-missing (derivable from its tag
    tree) must reach PASS with default (no-knob) fix."""
    from pdf_a11y.remediate import fix_one
    fr = fix_one(FIX / "tagged-nooutline.pdf", tmp_path / "t.fixed.pdf")
    assert fr["status"] == "pass"
    assert fr["findings_before"] == 1
    assert fr["reaudit"]["summary"]["total"] == 0


# -- e2e fix + CLI exit codes ------------------------------------------------

def test_fix_one_fixable_still_fails_without_scaffold(tmp_path):
    """In 0.1.0 the untagged root cause (pdf-unmarked) is
    unfixable, so even with alt-map + outline-map the doc still FAILs after
    fix: 6 -> 1 finding, the single 1.3.1. (Phase 5 --scaffold will make
    this reach pass.)"""
    from pdf_a11y.remediate import fix_one
    from pdf_a11y.rules import AuditContext
    out = tmp_path / "fixable.fixed.pdf"
    ctx = AuditContext(source_name="fixable.pdf",
                       alt_map={(0, "Im1"): "A square"},
                       outline_map=[(1, "Big Title", 0)])
    fr = fix_one(FIX / "fixable.pdf", out, ctx)
    assert fr["status"] == "fail"
    assert fr["findings_before"] == 6
    after = fr["reaudit"]
    assert after["summary"]["total"] == 1
    assert {f["rule_id"] for f in after["findings"]} == {"pdf-unmarked"}


def test_cli_exit_codes(tmp_path):
    from pdf_a11y.cli import main
    assert main(["audit", str(FIX / "clean.pdf")]) == 0
    assert main(["audit", str(FIX / "fixable.pdf")]) == 1
    assert main(["audit", str(tmp_path / "nope.pdf")]) == 2
    assert main(["rules"]) == 0