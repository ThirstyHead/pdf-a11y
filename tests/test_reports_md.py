"""Subplan 1 §1a — report content engine tests.

Covers the 1a contract:
  * POUR section order + presence (all 4 always), friendly intros
  * header says WCAG 2.2, links the W3C quickref
  * per-finding canonical W3C URL (SC -> slug table)
  * social-model tone: WHO_MAP lines + banned-phrase scan
  * summary banner: stats math (3 synthetic cases incl. 0-before -> 100.0)
    and the backward-compatible no-stats variant
  * report_json: schema_version 2, per-finding w3c_url, stats, determinism
  * CLI wiring: --format {md,json}, --report as md alias, fix flow stats
"""
import json
import re
from pathlib import Path
import pytest

from pdf_a11y.audit import audit_file
from pdf_a11y.reports import (
    POUR_INTROS,
    RULE_NOTES,
    RULE_TONES,
    SC_META,
    WHO_MAP,
    W3C_QUICKREF,
    compute_stats,
    render_md,
    report_json,
)

FIX = Path(__file__).parent / "fixtures"
FIXTURES = ["violations.pdf", "clean.pdf", "table-noactualtext.pdf"]

SLUGS = {
    "1.1.1": "non-text-content",
    "1.2.1": "audio-only-and-video-only-prerecorded",
    "1.3.1": "info-and-relationships",
    "1.4.3": "contrast-minimum",
    "1.4.12": "text-spacing",
    "2.4.1": "bypass-blocks",
    "2.4.2": "page-titled",
    "2.4.4": "link-purpose-in-context",
    "3.1.1": "language-of-page",
}

BANNED = [
    "suffer from", "suffers", "handicapped", "normal users",
    "is broken", "inaccessible to disabled",
]

EXPECTED_RULE_IDS = {
    "language-missing", "language-malformed", "title-missing",
    "display-doctitle-off", "pdf-unmarked", "tag-tree-missing",
    "tag-tree-weak", "image-alt-missing", "image-alt-tiny",
    "decorative-undeclared", "media-no-alt", "outline-missing",
    "link-text-vague", "pdf-encrypted", "color-contrast",
    "reading-order", "text-spacing", "actualtext-missing",
    "xmp-docprops-missing", "parenttree-mcid-integrity",
}


def _result(name):
    return audit_file(FIX / name)


def _section(text, title):
    m = re.search(rf"## {re.escape(title)}\n(.*?)(?=\n## |\Z)", text, re.S)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# POUR structure
# ---------------------------------------------------------------------------

def test_pour_sections_order_and_presence():
    text = render_md(_result("violations.pdf"), source_path="violations.pdf")
    heads = ["## 1. Perceivable", "## 2. Operable",
             "## 3. Understandable", "## 4. Robust"]
    pos = [text.index(h) for h in heads]
    assert pos == sorted(pos), "POUR sections out of order"
    for intro in POUR_INTROS.values():
        assert intro in text


def test_clean_pdf_empty_principle_wording():
    text = render_md(_result("clean.pdf"), source_path="clean.pdf")
    assert text.count("No barriers found in this principle.") == 4
    assert "No 4.x criteria are applicable to static PDF structure." in text


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def test_header_says_wcag_22_with_quickref():
    text = render_md(_result("violations.pdf"), source_path="violations.pdf")
    assert "WCAG 2.2" in text
    assert "WCAG 2.1" not in text
    assert "PDF/UA-1 target" in text
    assert W3C_QUICKREF in text
    assert "- **File:** violations.pdf" in text
    assert "- **Tool:**" in text
    assert "- **Audited:**" in text


def test_finding_heading_shape():
    text = render_md(_result("violations.pdf"), source_path="violations.pdf")
    name, level, _, _ = SC_META["1.3.1"]
    assert f"### SC 1.3.1 — {name} (Level {level})" in text


# ---------------------------------------------------------------------------
# W3C URLs
# ---------------------------------------------------------------------------

def test_w3c_url_table_matches_slugs():
    for sc, slug in SLUGS.items():
        assert sc in SC_META, f"SC_META missing {sc}"
        assert SC_META[sc][3] == (
            f"https://www.w3.org/WAI/WCAG22/Understanding/{slug}.html")


def test_w3c_url_per_finding():
    res = _result("violations.pdf")
    text = render_md(res, source_path="violations.pdf")
    for f in res["findings"]:
        assert SC_META[f["sc"]][3] in text


def test_json_report_has_w3c_url_per_finding():
    res = _result("violations.pdf")
    data = json.loads(report_json(res))
    assert data["schema_version"] == 2
    for f in data["findings"]:
        assert f["w3c_url"] == SC_META[f["sc"]][3]


# ---------------------------------------------------------------------------
# Social-model tone
# ---------------------------------------------------------------------------

def test_no_banned_phrases_any_fixture():
    for name in FIXTURES:
        text = render_md(_result(name), source_path=name)
        low = text.lower()
        for phrase in BANNED:
            assert phrase not in low, f"{name}: banned phrase {phrase!r}"


def test_who_benefits_line_per_finding():
    res = _result("violations.pdf")
    text = render_md(res, source_path="violations.pdf")
    for f in res["findings"]:
        assert WHO_MAP[f["sc"]] in text
        assert "- **Who benefits:**" in text


def test_tone_and_notes_cover_every_rule_id():
    assert set(RULE_TONES) == EXPECTED_RULE_IDS
    assert set(RULE_NOTES) == EXPECTED_RULE_IDS


# ---------------------------------------------------------------------------
# Summary banner + stats math
# ---------------------------------------------------------------------------

def test_stats_math_three_cases():
    s = compute_stats(10, 3)
    assert (s["found_before"], s["remaining_after"], s["corrected"]) == (10, 3, 7)
    assert s["improvement_pct"] == 70.0

    s = compute_stats(0, 0)
    assert s["corrected"] == 0
    assert s["improvement_pct"] == 100.0

    s = compute_stats(5, 5)
    assert s["improvement_pct"] == 0.0


def test_banner_with_stats():
    res = _result("violations.pdf")
    sec = _section(render_md(res, source_path="violations.pdf",
                             stats=compute_stats(10, 3)), "Summary")
    assert "**10**" in sec and "**7**" in sec and "**3**" in sec
    assert "70.0%" in sec
    assert "Verdict" in sec


def test_banner_zero_before():
    res = _result("clean.pdf")
    sec = _section(render_md(res, source_path="clean.pdf",
                             stats=compute_stats(0, 0)), "Summary")
    assert "100.0%" in sec
    assert "no barriers found" in sec


def test_banner_without_stats_is_backward_compatible():
    res = _result("violations.pdf")
    sec = _section(render_md(res, source_path="violations.pdf"), "Summary")
    assert "remain" not in sec.lower()
    assert "improvement" not in sec.lower()
    assert "Verdict" in sec
    assert "**2**" in sec  # found count only


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def test_json_report_round_trips_and_is_deterministic():
    res = _result("table-noactualtext.pdf")
    a = report_json(res)
    b = report_json(res)
    assert a == b
    data = json.loads(a)
    assert data["schema_version"] == 2
    assert data["summary"]["total"] == res["summary"]["total"]


def test_json_report_includes_stats_when_given():
    res = _result("violations.pdf")
    stats = compute_stats(10, 3)
    data = json.loads(report_json(res, stats=stats))
    assert data["stats"]["improvement_pct"] == 70.0
    assert data["stats"]["corrected"] == 7


def test_json_report_without_stats_has_no_stats_key():
    res = _result("violations.pdf")
    data = json.loads(report_json(res))
    assert "stats" not in data


# ---------------------------------------------------------------------------
# Enrichment (existing machinery, unchanged)
# ---------------------------------------------------------------------------

def test_enrichment_block_under_finding():
    res = _result("violations.pdf")
    enrichment = {"1.3.1": {
        "in_brief": "A short criterion summary.",
        "description": "The description text.",
        "intent": "The intent text.",
    }}
    text = render_md(res, source_path="violations.pdf", enrichment=enrichment,
                     enrichment_source="test-cache")
    assert "Normative text — SC 1.3.1" in text
    assert "A short criterion summary." in text
    assert "- **Normative text source:** test-cache" in text


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def test_cli_format_md_with_report_path(tmp_path):
    from pdf_a11y.cli import main
    with pytest.raises(SystemExit) as exc:
        main([str(FIX / "violations.pdf"), "--format", "md", "--output-dir", str(tmp_path)])
    assert exc.value.code == 1  # violations -> fail exit code
    out = tmp_path / "violations-a11y-report.md"
    assert "WCAG 2.2" in out.read_text()


def test_cli_report_flag_is_md_alias(tmp_path):
    from pdf_a11y.cli import main
    with pytest.raises(SystemExit) as exc:
        main([str(FIX / "clean.pdf"), "--format", "md", "--output-dir", str(tmp_path)])
    assert exc.value.code == 0
    out = tmp_path / "clean-a11y-report.md"
    assert "WCAG 2.2" in out.read_text()


def test_cli_format_json_default_name(tmp_path, monkeypatch):
    from pdf_a11y.cli import main
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main([str(FIX / "clean.pdf"), "--format", "json", "--output-dir", str(tmp_path)])
    assert exc.value.code == 0
    data = json.loads((tmp_path / "clean-audit.json").read_text())
    assert data["findings"] == []


def test_cli_fix_report_uses_new_engine(tmp_path):
    from pdf_a11y.cli import main
    out_pdf = tmp_path / "fixed.pdf"
    with pytest.raises(SystemExit) as exc:
        main([
            str(FIX / "fixable.pdf"),
            "--fix",
            "--out-pdf", str(out_pdf),
            "--format", "md",
            "--output-dir", str(tmp_path),
        ])
    assert exc.value.code in (0, 1)
    text = (tmp_path / "fixable-a11y-report.md").read_text()
    assert "WCAG 2.2" in text
    assert "Remediation" in text
