"""ISO 14289-1 structural rules (Phase C): actualtext, XMP docprops, ParentTree/MCID.

Scope notes (deviations from the plan's literal code, documented in the PR):
* ``xmp-docprops-missing`` applies to TAGGED documents only (PDF/UA is a spec
  for tagged PDFs). Untagged fixtures carry no XMP block at all; firing the
  rule on them would add a finding to every untagged oracle (fixable.pdf is
  pinned at exactly 6 findings) and break the Phase C acceptance gate.
* ``parenttree-mcid-integrity``'s fix is gated on ``ctx.scaffold and
  ctx.repair`` — the plan's own fix text says "automatic via fix --repair";
  an ungated fix would mutate trees on default (non-repair) runs, violating
  the Phase B opt-in invariant.
"""
from pathlib import Path

from pdf_a11y.audit import audit_file
from pdf_a11y.remediate import fix_one
from pdf_a11y.rules import AuditContext, RULES, RULES_BY_ID

FIXTURES = Path(__file__).parent / "fixtures"


def test_registry_is_18():
    assert len(RULES) == 18
    for rid in ("actualtext-missing", "xmp-docprops-missing", "parenttree-mcid-integrity"):
        assert rid in RULES_BY_ID, rid


def test_actualtext_table_without_actualtext():
    res = audit_file(FIXTURES / "table-noactualtext.pdf")
    at = [f for f in res["findings"] if f["rule_id"] == "actualtext-missing"]
    assert len(at) == 1
    assert at[0]["fixable"] is False          # actual text is human content


def test_actualtext_clean_when_present():
    res = audit_file(FIXTURES / "table-actualtext.pdf")
    at = [f for f in res["findings"] if f["rule_id"] == "actualtext-missing"]
    assert at == []


def test_xmp_missing_then_fixed(tmp_path):
    res = audit_file(FIXTURES / "xmp-incomplete.pdf")
    xmp = [f for f in res["findings"] if f["rule_id"] == "xmp-docprops-missing"]
    assert len(xmp) == 1
    assert "pdf:Producer" in xmp[0]["description"]
    assert xmp[0]["fixable"] is True
    fr = fix_one(FIXTURES / "xmp-incomplete.pdf", tmp_path / "out.pdf",
                 ctx=AuditContext())
    after = fr["reaudit"]
    assert not any(f["rule_id"] == "xmp-docprops-missing" for f in after["findings"])
    assert fr["status"] == "pass", fr


def test_parenttree_integrity_clean_on_good_fixtures():
    for name in ("clean.pdf", "violations.pdf"):
        res = audit_file(FIXTURES / name)
        pt = [f for f in res["findings"] if f["rule_id"] == "parenttree-mcid-integrity"]
        assert pt == [], (name, pt)


def test_parenttree_opt_in_like_phase_b(tmp_path):
    """weak-repairable.pdf (orphaned /P) now also trips the parenttree rule.
    Default fix (scaffold on, repair off) must leave BOTH findings in place —
    repair stays opt-in; --repair clears both in one pass."""
    src = FIXTURES / "weak-repairable.pdf"
    res = audit_file(src)
    rules = {f["rule_id"] for f in res["findings"]}
    assert "parenttree-mcid-integrity" in rules

    fr = fix_one(src, tmp_path / "a.pdf", ctx=AuditContext(scaffold=True))
    after_rules = {f["rule_id"] for f in fr["reaudit"]["findings"]}
    assert {"tag-tree-weak", "parenttree-mcid-integrity"} <= after_rules
    assert fr["status"] == "fail"

    fr = fix_one(src, tmp_path / "b.pdf",
                 ctx=AuditContext(scaffold=True, repair=True))
    assert fr["status"] == "pass", fr
    assert fr["reaudit"]["summary"]["total"] == 0
