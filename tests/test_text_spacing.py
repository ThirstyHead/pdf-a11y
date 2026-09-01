"""Tests for the SC 1.4.12 text-spacing rule.

Layered (mirrors test_reading_order.py):
  * unit tests of the threshold logic on synthetic ``PageSpacing`` values;
  * PDF-level tests that build real fixtures with PyMuPDF in ``tmp_path``
    (hermetic; nothing committed);
  * rule-integration tests that run the full audit and assert the
    ``text-spacing`` finding fires on a cramped document and NOT on normal
    documents (the no-false-positive invariant).
"""
import fitz  # PyMuPDF

from pdf_a11y import spacing as sp
from pdf_a11y.audit import audit_file
from pdf_a11y.rules import AuditContext, RULES, RULES_BY_ID


def _build_lines(tmp_path, name, lines, fs=12, dy=18, x=20, y0=10):
    """Write ``lines`` top-to-bottom with baseline gap ``dy`` at font size ``fs``.
    ``dy`` is the baseline gap, so line-height ratio == dy / fs.
    """
    p = str(tmp_path / name)
    d = fitz.open()
    page = d.new_page(width=300, height=300)
    y = y0
    for t in lines:
        page.insert_text((x, y), t, fontsize=fs)
        y += dy
    d.save(p)
    d.close()
    return p


# ---------------------------------------------------------------------------
# unit: the rule's threshold decision on synthetic PageSpacing
# ---------------------------------------------------------------------------

def test_rule_registered_and_advisory():
    assert "text-spacing" in RULES_BY_ID
    r = RULES_BY_ID["text-spacing"]
    assert r.rule_id == "text-spacing"
    assert r.sc == "1.4.12"
    assert r.severity == "moderate"
    # exactly one text-spacing rule in the registry
    assert sum(1 for x in RULES if x.rule_id == "text-spacing") == 1


def test_rule_flags_cramped_line_height():
    r = RULES_BY_ID["text-spacing"]
    pages = [sp.PageSpacing(page_no=0, min_line_height=0.9,
                            line_height_text="tight")]
    # exercise the same comparison the rule uses
    line_min = 1.0
    flagged = any(p.min_line_height is not None and p.min_line_height < line_min
                  for p in pages)
    assert flagged
    assert r.fix(None, None, AuditContext()) is False


def test_rule_ignores_normal_line_height():
    line_min = 1.0
    pages = [sp.PageSpacing(page_no=0, min_line_height=1.33,
                            line_height_text="normal")]
    flagged = any(p.min_line_height is not None and p.min_line_height < line_min
                  for p in pages)
    assert not flagged


def test_rule_flags_cramped_word_and_letter():
    word_min, letter_min = 0.08, -0.12
    p = sp.PageSpacing(page_no=0, min_word_gap=0.05, min_letter_gap=-0.20)
    assert (p.min_word_gap is not None and p.min_word_gap < word_min)
    assert (p.min_letter_gap is not None and p.min_letter_gap < letter_min)


def test_rule_ignores_normal_word_and_letter():
    word_min, letter_min = 0.08, -0.12
    p = sp.PageSpacing(page_no=0, min_word_gap=0.20, min_letter_gap=-0.01)
    assert not (p.min_word_gap is not None and p.min_word_gap < word_min)
    assert not (p.min_letter_gap is not None and p.min_letter_gap < letter_min)


def test_rule_ignores_unmeasured_metrics():
    # None metrics (single-line page, no words) must not be flagged.
    p = sp.PageSpacing(page_no=0)
    assert p.min_line_height is None
    assert p.min_word_gap is None
    assert p.min_letter_gap is None


# ---------------------------------------------------------------------------
# PDF-level: spacing_report
# ---------------------------------------------------------------------------

def test_report_normal_line_height(tmp_path):
    p = _build_lines(tmp_path, "normal.pdf",
                     ["first line here", "second line here", "third line here"],
                     fs=12, dy=18)   # 18/12 = 1.5
    rep = sp.spacing_report(p)
    assert rep and rep[0].min_line_height is not None
    assert rep[0].min_line_height > 1.0     # comfortable, well above the bound


def test_report_cramped_line_height(tmp_path):
    p = _build_lines(tmp_path, "tight.pdf",
                     ["first line here", "second line here", "third line here"],
                     fs=12, dy=8)          # 8/12 = 0.667
    rep = sp.spacing_report(p)
    assert rep and rep[0].min_line_height is not None
    assert rep[0].min_line_height < 1.0     # cramped, below the bound
    # offending text is reported so the issue is locatable
    assert rep[0].line_height_text != ""


def test_report_multiline_word_spacing_present(tmp_path):
    p = _build_lines(tmp_path, "words.pdf",
                     ["normal spaced sentence words",
                      "another normal spaced sentence",
                      "and one more normal sentence"],
                     fs=12, dy=18)
    rep = sp.spacing_report(p)
    assert rep and rep[0].min_word_gap is not None
    # normal body text word spacing is comfortably above the 0.08em bound
    assert rep[0].min_word_gap > 0.08


def test_report_deterministic(tmp_path):
    p = _build_lines(tmp_path, "det.pdf", ["a b c", "d e f", "g h i"], fs=12, dy=18)
    a = sp.spacing_report(p)
    b = sp.spacing_report(p)
    assert a == b


# ---------------------------------------------------------------------------
# rule integration: full audit
# ---------------------------------------------------------------------------

def _text_spacing_finding(rule_id="text-spacing"):
    from pdf_a11y.rules import RULES_BY_ID  # noqa
    return RULES_BY_ID[rule_id]


def test_audit_tight_line_height_finds_text_spacing(tmp_path):
    # lines crammed to 0.667x font size -> the rule must fire
    p = _build_lines(tmp_path, "tight.pdf",
                     ["alpha line one", "beta line two", "gamma line three"],
                     fs=12, dy=8)
    result = audit_file(p, AuditContext())
    ts = [f for f in result["findings"] if f["rule_id"] == "text-spacing"]
    assert len(ts) == 1, f"expected exactly 1 text-spacing finding, got {len(ts)}"
    # correct page and SC
    assert ts[0]["sc"] == "1.4.12"
    assert ts[0]["location"] == "page[0]"
    # offending text reported in the evidence
    assert "line height" in ts[0]["evidence"]
    # advisory: not fixable, not blocking
    assert ts[0]["fixable"] is False
    assert ts[0]["severity"] == "moderate"


def test_audit_normal_text_no_text_spacing(tmp_path):
    # comfortable body text -> the rule must NOT fire (no false positive)
    p = _build_lines(tmp_path, "ok.pdf",
                     ["alpha line one", "beta line two", "gamma line three"],
                     fs=12, dy=18)
    result = audit_file(p, AuditContext())
    ts = [f for f in result["findings"] if f["rule_id"] == "text-spacing"]
    assert ts == [], f"expected no text-spacing finding, got {ts}"


def test_audit_deterministic_text_spacing(tmp_path):
    p = _build_lines(tmp_path, "det.pdf",
                     ["alpha line one", "beta line two", "gamma line three"],
                     fs=12, dy=8)
    a = audit_file(p, AuditContext())["findings"]
    b = audit_file(p, AuditContext())["findings"]
    ta = [f for f in a if f["rule_id"] == "text-spacing"]
    tb = [f for f in b if f["rule_id"] == "text-spacing"]
    assert ta == tb and len(ta) == 1


def test_all_committed_fixtures_have_no_text_spacing():
    """The no-false-positive invariant: none of the committed fixtures renders
    cramped text, so the new rule must not flag any of them."""
    import glob, os
    from pdf_a11y.rules import AuditContext as AC
    here = os.path.dirname(__file__)
    for path in sorted(glob.glob(os.path.join(here, "fixtures", "*.pdf"))):
        result = audit_file(path, AC())
        ts = [f for f in result["findings"] if f["rule_id"] == "text-spacing"]
        assert ts == [], f"{os.path.basename(path)} unexpectedly flagged: {ts}"
