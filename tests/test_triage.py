"""Tests for interactive triage workflow and TriageSession."""
from pathlib import Path
import shutil
import pytest

from pdf_a11y.audit import audit_file
from pdf_a11y.docmodel import DocModel
from pdf_a11y.immutability import sha256_file
from pdf_a11y.triage import TriageItem, TriageSession, run_interactive_triage

FIXTURES = Path(__file__).parent / "fixtures"
MINIMAL = FIXTURES / "minimal_tagged.pdf"
VIOLATIONS = FIXTURES / "violations.pdf"


def test_triage_session_models():
    item = TriageItem(
        rule_id="title-missing",
        location="catalog",
        description="Missing title",
        prompt="Enter title:",
        action="input",
    )
    assert item.rule_id == "title-missing"
    assert item.action == "input"
    assert item.resolved_value is None

    session = TriageSession(
        findings=[
            {"rule_id": "title-missing", "location": "catalog", "message": "Missing title"},
            {"rule_id": "language-missing", "location": "catalog", "message": "Missing lang"},
        ]
    )
    pending = session.get_pending_items()
    assert len(pending) == 2
    assert pending[0].rule_id == "title-missing"

    session.resolve_item(0, "My Accessible Document")
    session.resolve_item(1, "fr-FR")
    assert session.items[0].resolved_value == "My Accessible Document"

    overrides = session.to_context_overrides()
    assert overrides.get("title") == "My Accessible Document"
    assert overrides.get("default_language") == "fr-FR"


def test_interactive_triage_flow(tmp_path: Path):
    src = tmp_path / "triage_input.pdf"
    prep = tmp_path / "prep.pdf"

    with DocModel.open(VIOLATIONS) as dm:
        if "/Info" in dm.doc.trailer and "/Title" in dm.doc.trailer["/Info"]:
            del dm.doc.trailer["/Info"]["/Title"]
        meta = dm.doc.open_metadata()
        with meta:
            meta["dc:title"] = ""
        dm.save(prep)

    shutil.move(prep, src)
    orig_hash = sha256_file(src)

    out = tmp_path / "triaged_output.pdf"

    responses = iter(["Annual Financial Report", "en-GB", "y"])
    messages = []

    def mock_input(prompt=""):
        return next(responses, "")

    def mock_print(*args, **kwargs):
        messages.append(" ".join(str(a) for a in args))

    count = run_interactive_triage(
        in_path=src,
        out_path=out,
        input_func=mock_input,
        print_func=mock_print,
    )

    assert out.exists()
    assert sha256_file(src) == orig_hash

    # Verify remediated PDF has the triaged properties
    with DocModel.open(out) as dm:
        # Title was set
        assert dm.title() is not None
        assert "Annual Financial Report" in (dm.title() or "")
