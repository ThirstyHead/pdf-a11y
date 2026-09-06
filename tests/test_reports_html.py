"""Subplan 1 §1b — HTML render + SMACSS theme system tests (RED first).

Contract under test (subplan 1b):
  * render_html(md_text, theme, lang, config_dir) -> self-contained HTML5 doc
  * accessible: doctype, <html lang>, meta charset, <title>=H1, <main>,
    skip-to-content link, TOC nav, exactly one <h1>, no heading-level skips,
    zero <script>, CSS inlined (no external stylesheet links)
  * every w3.org link has non-empty text
  * byte-deterministic
  * theme system: 5 bundled themes (light/dark/high-contrast/ocean/forest),
    theme_css = tokens → layout → units → overrides with marker comment,
    available_themes merges user <config_dir>/themes first (user wins),
    contrast gate: fg/bg + every severity color ≥ 4.5:1 against bg
  * CLI: --format html writes <stem>.html; --theme unknown → exit 2 + list
"""
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pdf_a11y.audit import audit_file
from pdf_a11y.contrast import contrast_ratio, hex_to_rgb
from pdf_a11y.reports import html as html_mod
from pdf_a11y.reports.html import render_html
from pdf_a11y.reports.md import render_md
from pdf_a11y.reports.theme import (
    BUNDLED_THEMES,
    available_themes,
    theme_css,
)

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "fixtures"
BUNDLED = ["light", "dark", "high-contrast", "ocean", "forest"]

SAMPLE_MD = "\n".join([
    "# Accessibility Audit Report — sample.pdf",
    "",
    "- **File:** sample.pdf",
    "- **Audited:** 2026-09-06T00:00:00Z",
    "- **Standard:** WCAG 2.2 AA (subset applicable to PDF structure; PDF/UA-1 target)",
    "- **WCAG quick reference:** https://www.w3.org/WAI/WCAG22/quickref/",
    "",
    "## Summary",
    "",
    "This document has **2** digital accessibility barriers. **Verdict:** FAIL.",
    "",
    "## 1. Perceivable",
    "",
    "Intro text.",
    "",
    "### SC 1.3.1 — Info and Relationships (Level A)",
    "",
    "[WCAG 2.2 SC 1.3.1 — Info and Relationships (official W3C Understanding docs)]"
    "(https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html)",
    "",
    "- **Severity:** serious",
    "",
    "## 4. Robust",
    "",
    "No barriers found in this principle.",
    "",
    "## Re-verify",
    "",
    "```bash",
    "pdf-a11y audit sample.pdf.fixed.pdf --json reaudit.json",
    "```",
    "",
])


def _md_from_fixture(name: str) -> str:
    res = audit_file(str(FIX / name))
    return render_md(res, source_path=str(FIX / name))


class DocScan(HTMLParser):
    """Collects the accessibility-relevant facts of a document."""

    HEADING_RE = re.compile(r"^h([1-6])$")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1_count = 0
        self.headings = []          # list of levels in document order
        self.scripts = 0
        self.style_tags = 0
        self.external_css = 0       # <link rel=stylesheet>
        self.html_lang = None
        self.has_doctype = False
        self.has_charset = False
        self.has_main = False
        self.title = ""
        self.w3c_links = []         # (href, text)
        self.skip_target = None     # href of a.skip
        self.in_title = False
        self._link_stack = []       # (href, [text])
        self.in_pre = False
        self.attrs_seen = []

    def handle_decl(self, decl):
        self.has_doctype = decl.lower().startswith("doctype")

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.attrs_seen.append((tag, a))
        if tag == "meta":
            if "charset" in a:
                self.has_charset = True
        elif tag == "html":
            self.html_lang = a.get("lang")
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if "stylesheet" in rel.split():
                self.external_css += 1
        elif tag == "style":
            self.style_tags += 1
        elif tag == "script":
            self.scripts += 1
        elif tag == "main":
            self.has_main = True
        elif tag == "title":
            self.in_title = True
        elif re.match(r"h[1-6]$", tag):
            self.headings.append(int(tag[1]))
            if tag == "h1":
                self.h1_count += 1
        elif tag == "a":
            self._link_stack.append((a.get("href", ""), []))
            if "skip" in (a.get("class") or "").split():
                self.skip_target = a.get("href")
        elif tag == "pre" or tag == "code":
            self.in_pre = True

    def handle_endtag(self, tag):
        if tag in ("pre", "code"):
            self.in_pre = False
        if tag == "title":
            self.in_title = False
        if tag == "a" and self._link_stack:
            href, parts = self._link_stack.pop()
            text = "".join(parts).strip()
            if href.startswith("https://www.w3.org"):
                self.w3c_links.append((href, text))

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self._link_stack:
            self._link_stack[-1][1].append(data)


def _scan(doc: str) -> DocScan:
    s = DocScan()
    s.feed(doc)
    s.close()
    return s


# ---------------------------------------------------------------------------
# Document accessibility shape
# ---------------------------------------------------------------------------

def test_accessible_document_skeleton():
    doc = render_html(SAMPLE_MD, theme="light")
    s = _scan(doc)
    assert s.has_doctype, "missing <!doctype html>"
    assert s.html_lang == "en"
    assert s.has_charset
    assert s.has_main, "missing <main>"
    assert s.h1_count == 1, f"exactly one <h1> required, got {s.h1_count}"
    assert "sample.pdf" in s.title
    assert doc.lstrip().lower().startswith("<!doctype html>")


def test_lang_param():
    doc = render_html(SAMPLE_MD, theme="light", lang="de")
    assert _scan(doc).html_lang == "de"


def test_no_heading_level_skips():
    doc = render_html(_md_from_fixture("violations.pdf"), theme="light")
    s = _scan(doc)
    prev = 1  # h1 exists by construction
    for lvl in s.headings:
        assert lvl <= prev + 1, f"heading level skips h{prev} -> h{lvl}"
        prev = lvl


def test_no_script_tags_and_css_inlined():
    doc = render_html(SAMPLE_MD, theme="light")
    s = _scan(doc)
    assert s.scripts == 0, "zero <script> tags allowed"
    assert s.style_tags >= 1, "theme CSS must be inlined in <style>"
    assert s.external_css == 0, "single self-contained file: no external css"


def test_w3c_links_have_nonempty_text():
    doc = render_html(_md_from_fixture("violations.pdf"), theme="light")
    s = _scan(doc)
    assert s.w3c_links, "expected w3.org links in a real report"
    for href, text in s.w3c_links:
        assert text, f"link with empty text: {href}"


def test_skip_link_and_toc_nav():
    doc = render_html(_md_from_fixture("violations.pdf"), theme="light")
    s = _scan(doc)
    assert s.skip_target == "#main", "skip-to-content link must target #main"
    # TOC nav: links to the POUR sections exist
    hrefs = {h for h, _ in s.w3c_links}
    nav_hrefs = [a.get("href") for t, a in s.attrs_seen if t == "a"]
    assert any(h and h.startswith("#1-perceivable") for h in nav_hrefs), \
        "TOC nav must link the POUR section ids"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_byte_deterministic():
    a = render_html(_md_from_fixture("violations.pdf"), theme="dark")
    b = render_html(_md_from_fixture("violations.pdf"), theme="dark")
    assert a == b


def test_theme_switch_changes_output():
    light = render_html(SAMPLE_MD, theme="light")
    dark = render_html(SAMPLE_MD, theme="dark")
    assert light != dark
    assert "/* pdf-a11y theme: light */" in light
    assert "/* pdf-a11y theme: dark */" in dark


# ---------------------------------------------------------------------------
# Theme system
# ---------------------------------------------------------------------------

def test_bundled_theme_set():
    assert sorted(BUNDLED_THEMES) == sorted(BUNDLED)


def test_available_themes_shapes_and_default():
    themes = available_themes()
    names = [t["name"] for t in themes]
    assert set(BUNDLED) <= set(names)
    by_name = {t["name"]: t for t in themes}
    assert by_name["light"]["default"] is True
    for t in themes:
        assert t["mode"] in ("light", "dark")
        assert t["label"]


def test_theme_css_layer_order_and_marker():
    css = theme_css("ocean")
    assert css.startswith("/* pdf-a11y theme: ocean */")
    # order: tokens (--bg first appearance) → layout/units → overrides
    assert "--bg:" in css
    assert css.index("--bg:") < css.index(".report"), \
        "tokens layer must precede unit/component layers"


def test_theme_css_missing_theme_raises():
    with pytest.raises(KeyError):
        theme_css("does-not-exist")


def test_user_theme_override_wins(tmp_path):
    cfg = tmp_path / "config"
    (cfg / "themes" / "light").mkdir(parents=True)
    (cfg / "themes" / "light" / "tokens.css").write_text(
        ":root { --accent: #123456; }\n")
    (cfg / "themes" / "light" / "theme.json").write_text(json.dumps(
        {"name": "light", "label": "User Light", "mode": "light",
         "default": True}))
    themes = available_themes(config_dir=cfg)
    names = [t["name"] for t in themes]
    assert names[0] == "light"
    assert themes[0]["label"] == "User Light"
    css = theme_css("light", config_dir=cfg)
    assert "--accent: #123456" in css
    # user tokens replace bundled tokens for the same variable
    assert css.count("--accent:") == 1


def test_user_theme_new_name_available(tmp_path):
    cfg = tmp_path / "config"
    d = cfg / "themes" / "sunset"
    d.mkdir(parents=True)
    (d / "tokens.css").write_text(
        ":root {\n  --bg: #fff8f0;\n  --fg: #2b1d0e;\n  --muted: #6b543c;\n"
        "  --accent: #c2571a;\n  --link: #8a3c0f;\n  --code-bg: #f3e4d3;\n"
        "  --sev-critical: #a3132f;\n  --sev-serious: #9c3d00;\n"
        "  --sev-moderate: #7a5a00;\n  --sev-minor: #4a5568;\n}\n")
    (d / "theme.json").write_text(json.dumps(
        {"name": "sunset", "label": "Sunset", "mode": "light",
         "default": False}))
    names = [t["name"] for t in available_themes(config_dir=cfg)]
    assert "sunset" in names
    assert theme_css("sunset", config_dir=cfg).startswith(
        "/* pdf-a11y theme: sunset */")


def _tokens_of(css: str) -> dict:
    out = {}
    for m in re.finditer(r"-\-(bg|fg|muted|accent|link|code-bg|"
                         r"sev-critical|sev-serious|sev-moderate|sev-minor)"
                         r"\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", css):
        out[m.group(1)] = m.group(2)
    return out


def test_contrast_gate_all_bundled_themes():
    for name in BUNDLED:
        css = theme_css(name)
        tok = _tokens_of(css)
        assert len(tok) == 10, f"{name}: expected 10 tokens, got {sorted(tok)}"
        bg = hex_to_rgb(tok["bg"])
        assert contrast_ratio(hex_to_rgb(tok["fg"]), bg) >= 4.5, \
            f"{name}: fg/bg contrast below 4.5"
        for sev in ("sev-critical", "sev-serious", "sev-moderate", "sev-minor"):
            ratio = contrast_ratio(hex_to_rgb(tok[sev]), bg)
            assert ratio >= 4.5, f"{name}: {sev} contrast {ratio:.2f} < 4.5"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(*extra):
    return subprocess.run(
        [sys.executable, "-m", "pdf_a11y.cli", "audit",
         str(FIX / "violations.pdf"), *extra],
        capture_output=True, text=True, cwd=str(REPO), timeout=120)


def test_cli_html_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = _cli("--format", "html")
    assert r.returncode == 0, r.stderr
    out = Path("violations.html")
    assert out.exists(), "expected <stem>.html in CWD"
    doc = out.read_text()
    s = _scan(doc)
    assert s.h1_count == 1 and s.scripts == 0
    assert "/* pdf-a11y theme: light */" in doc


def test_cli_html_with_theme(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = _cli("--format", "html", "--theme", "ocean")
    assert r.returncode == 0, r.stderr
    assert "/* pdf-a11y theme: ocean */" in Path("violations.html").read_text()


def test_cli_unknown_theme_exit2_lists_themes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = _cli("--format", "html", "--theme", "nonexistent")
    assert r.returncode == 2
    for name in BUNDLED:
        assert name in (r.stderr + r.stdout)
