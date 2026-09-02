"""Weak-tag-tree repair (Phase B): --scaffold --repair on already-tagged docs.

The fixture (weak-repairable.pdf, built in B4) is clean.pdf's tree with the
Paragraph element's /P dropped -> exactly one tag-tree-weak finding. With
ctx(scaffold=True, repair=True) the orphan is repointed and the re-audit is
clean; without the repair flag the finding must persist (opt-in).
"""
from pathlib import Path

from pdf_a11y.audit import audit_file
from pdf_a11y.remediate import fix_one
from pdf_a11y.rules import AuditContext

FIXTURES = Path(__file__).parent / "fixtures"
SRC = FIXTURES / "weak-repairable.pdf"


def test_fixture_reports_exactly_one_orphan():
    res = audit_file(SRC)
    weak = [f for f in res["findings"] if f["rule_id"] == "tag-tree-weak"]
    assert len(weak) == 1
    assert "parent pointer" in weak[0]["description"]


def test_repair_repoints_orphan_and_reaudits_clean():
    ctx = AuditContext(scaffold=True, repair=True)
    fr = fix_one(SRC, ctx=ctx)
    assert fr["status"] == "pass", fr
    weak = [f for f in fr["reaudit"]["findings"] if f["rule_id"] == "tag-tree-weak"]
    assert weak == []          # the orphan finding is gone


def test_repair_is_noop_without_flag():
    ctx = AuditContext(scaffold=True)          # scaffold but NOT repair
    fr = fix_one(SRC, ctx=ctx)
    weak = [f for f in fr["reaudit"]["findings"] if f["rule_id"] == "tag-tree-weak"]
    assert len(weak) == 1          # repair is opt-in; finding persists
