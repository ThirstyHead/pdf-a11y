"""Subplan 1 §1c — tagged-PDF render + self-audit gate tests (RED first).

Contract under test (subplan 1c):
  * render_pdf(html_doc, theme="light", out_path=None, *, lang="en",
               title=None) -> Path            (reports/__init__.py target)
  * PyMuPDF Story renders the 1b HTML body with a FIXED print stylesheet
    (decision D1: black on white, severity = weight/underline, not just color)
    so the output is theme-independent and self-auditable
  * post-process with DocModel (pikepdf): /Lang, /Title (from H1), /MarkInfo
    /Marked true, XMP dc:title + pdf:Producer; build_scaffold over the rendered
    text blocks creates the tag tree
  * output is a normal, text-extractable, selectable PDF
  * self-audit gate (the heart of 1c): audit_file on the report PDF itself ->
    PASS (0 blocking; no pdf-unmarked / language-missing / title-missing)
  * byte-deterministic (Story deterministic; /CreationDate not stamped, or
    stripped)
  * CLI: --format pdf writes <stem>.report.pdf; multi-format
    --format md,html,pdf,json writes all four (naming: <stem>-a11y-report.md /
    .json, <stem>.html, <stem>.report.pdf) via subprocess
"""
import subprocess
import sys
from pathlib import Path

import pikepdf
import pymupdf
import pytest

from pdf_a11y.audit import audit_file
from pdf_a11y.reports import render_pdf          # 1c target (RED: ImportError)
from pdf_a11y.reports.html import render_html
from pdf_a11y.reports.md import render_md

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "fixtures"


def _md_from_fixture(name: str) -> str:
    res = audit_file(str(FIX / name))
    return render_md(res, source_path=str(FIX / name))


def _report_pdf(name: str, tmp_path: Path, theme: str = "light",
                suffix: str = "report", md: str | None = None) -> Path:
    """Full 1c pipeline: audit -> md -> html -> tagged PDF. Returns the path."""
    if md is None:
        md = _md_from_fixture(name)
    html = render_html(md, theme=theme)
    out = tmp_path / f"{suffix}.report.pdf"
    return render_pdf(html, theme=theme, out_path=out)


def _doc_text(path: Path) -> str:
    with pymupdf.open(path) as d:
        return "".join(str(d.load_page(i).get_text("text"))
                       for i in range(len(d)))


def _catalog_facts(path: Path) -> dict:
    with pikepdf.open(path) as pdf:
        c = pdf.Root
        facts = {
            "lang": str(c.Lang) if "/Lang" in c else None,
            "marked": bool(c.MarkInfo.Marked) if "/MarkInfo" in c else False,
            "struct_tree": "/StructTreeRoot" in c,
            "info_title": "",
            "dc_title": "",
            "producer": "",
        }
        info = pdf.trailer.get("/Info")
        if info is not None and "/Title" in info:
            facts["info_title"] = str(info["/Title"])
        try:
            meta = pdf.open_metadata()
            facts["dc_title"] = str(meta.get("dc:title", ""))
            facts["producer"] = str(meta.get("pdf:Producer", ""))
        except Exception:
            pass
    return facts


# ---------------------------------------------------------------------------
# existence + text layer
# ---------------------------------------------------------------------------

def test_render_pdf_exists_returns_path(tmp_path):
    out = _report_pdf("violations.pdf", tmp_path)
    assert isinstance(out, Path)
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.suffix == ".pdf"


def test_render_pdf_text_extractable_selectable(tmp_path):
    out = _report_pdf("violations.pdf", tmp_path)
    text = _doc_text(out)
    assert "Perceivable" in text
    assert "1.3.1" in text, "SC numbers must survive into the PDF text layer"
    assert "Robust" in text


# ---------------------------------------------------------------------------
# metadata + tag tree (DocModel post-process)
# ---------------------------------------------------------------------------

def test_render_pdf_catalog_metadata(tmp_path):
    out = _report_pdf("violations.pdf", tmp_path)
    f = _catalog_facts(out)
    assert f["lang"], "/Lang must be set"
    assert f["info_title"], "/Info /Title must be non-empty (from H1)"
    assert f["dc_title"], "XMP dc:title must be non-empty"
    assert "pdf-a11y" in f["producer"], "pdf:Producer must name the tool"


def test_render_pdf_marked_and_tag_tree(tmp_path):
    out = _report_pdf("violations.pdf", tmp_path)
    f = _catalog_facts(out)
    assert f["marked"], "/MarkInfo /Marked must be true"
    assert f["struct_tree"], "/StructTreeRoot must exist (tag tree)"


# ---------------------------------------------------------------------------
# self-audit gate (the heart of 1c)
# ---------------------------------------------------------------------------

def test_render_pdf_self_audit_pass(tmp_path):
    out = _report_pdf("violations.pdf", tmp_path)
    res = audit_file(out)
    s = res["summary"]
    assert s["pass"] is True, f"self-audit must PASS, got {s}"
    assert s["blocking"] == 0, f"no blocking findings, got {s}"
    ids = {f["rule_id"] for f in res["findings"]}
    assert "pdf-unmarked" not in ids, "tag tree missing"
    assert "language-missing" not in ids, "/Lang missing"
    assert "title-missing" not in ids, "title missing"


# ---------------------------------------------------------------------------
# determinism + theme-independence (D1)
# ---------------------------------------------------------------------------

def test_render_pdf_byte_deterministic(tmp_path):
    md = _md_from_fixture("violations.pdf")
    a = _report_pdf("violations.pdf", tmp_path, suffix="a", md=md)
    b = _report_pdf("violations.pdf", tmp_path, suffix="b", md=md)
    assert a.read_bytes() == b.read_bytes(), (
        "two renders of the same report must be byte-identical "
        "(Story is deterministic; /CreationDate must not be stamped, or stripped)")


def test_render_pdf_theme_independent_d1(tmp_path):
    """D1: fixed print token set -> the PDF (text + audit) is theme-independent."""
    md = _md_from_fixture("violations.pdf")
    light = _report_pdf("violations.pdf", tmp_path, theme="light", suffix="l", md=md)
    dark = _report_pdf("violations.pdf", tmp_path, theme="dark", suffix="d", md=md)
    assert _doc_text(light) == _doc_text(dark), (
        "PDF text must not depend on the HTML theme (fixed print stylesheet, D1)")
    for p in (light, dark):
        assert audit_file(p)["summary"]["pass"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(*extra):
    # No explicit cwd: the package is editable-installed, so the subprocess
    # resolves it from any CWD and the CWD-relative reports land where the
    # test chdir'd it (tmp_path). violations.pdf FAILs the audit, so exit is 1
    # (0=PASS, 1=FAIL); reports are still written.
    return subprocess.run(
        [sys.executable, "-m", "pdf_a11y.cli",
         str(FIX / "violations.pdf"), *extra],
        capture_output=True, text=True, timeout=180)


def test_cli_pdf_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = _cli("--format", "pdf")
    assert r.returncode == 1, r.stderr
    out = Path("violations.report.pdf")
    assert out.exists(), "expected <stem>.report.pdf in CWD"
    assert out.stat().st_size > 0
    assert "Perceivable" in _doc_text(out)


def test_cli_multi_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = _cli("--format", "md,html,pdf,json")
    assert r.returncode == 1, r.stderr  # FAIL verdict, not a usage error (2)
    for name in ("violations-a11y-report.md", "violations-a11y-report.json",
                 "violations.html", "violations.report.pdf"):
        p = Path(name)
        assert p.exists(), f"expected {name}; stderr={r.stderr!r}"
    assert "Perceivable" in _doc_text(Path("violations.report.pdf"))
