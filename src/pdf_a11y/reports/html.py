"""HTML report engine (v0.5.0, subplan 1b).

Markdown (1a — source of truth) -> self-contained accessible HTML5 document:
doctype, <html lang>, meta charset, <title> from the H1, skip-to-content
link, TOC nav (deterministic ``toc`` slugs), theme CSS inlined (single file,
zero <script>), W3C links same-tab (no target=). Byte-deterministic.
"""
import html as _html
import re

import markdown

from .theme import theme_css

_MD_EXTENSIONS = ["tables", "fenced_code", "toc", "sane_lists"]

_H2_RE = re.compile(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>')


def _convert(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=_MD_EXTENSIONS)


def _extract_title(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Accessibility Report"


def _wrap_summary_banner(body: str) -> str:
    """Wrap the Summary section's paragraphs in .summary-banner."""
    m = re.search(r'(<h2 id="summary"[^>]*>.*?</h2>)(.*?)(?=<h2 )',
                  body, re.DOTALL)
    if not m:
        return body
    inner = m.group(2).strip("\n")
    if not inner:
        return body
    wrapped = (m.group(1) + "\n"
               + '<div class="summary-banner">\n' + inner + "\n</div>")
    return body[:m.start()] + wrapped + body[m.end():]


def _wrap_findings(body: str) -> str:
    """Wrap each finding (H3 block) in <section class="finding">."""
    pattern = re.compile(r'(<h3 [^>]*>.*?</h3>.*?)(?=<h3 |<h2 |$)', re.DOTALL)

    def _repl(m):
        block = m.group(1).strip("\n")
        return '<section class="finding">\n' + block + "\n</section>\n"

    return pattern.sub(_repl, body)


def _toc_nav(body: str) -> str:
    """TOC from the H2 entries (deterministic toc slugs)."""
    items = [f'    <li><a href="#{hid}">{text}</a></li>'
             for hid, text in _H2_RE.findall(body)]
    if not items:
        return ""
    return ('<nav class="toc" aria-label="Table of contents">\n'
            "  <ul>\n" + "\n".join(items) + "\n  </ul>\n"
            "</nav>\n")


def render_html(md_text: str, theme: str = "light", lang: str = "en",
                config_dir=None) -> str:
    """Render the Markdown report as a self-contained accessible HTML5 doc."""
    body = _convert(md_text)
    body = _wrap_summary_banner(body)
    body = _wrap_findings(body)
    nav = _toc_nav(body)
    title = _html.escape(_extract_title(md_text))
    css = theme_css(theme, config_dir=config_dir)
    return (
        "<!doctype html>\n"
        f'<html lang="{lang}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{css}</style>\n"
        "</head>\n"
        "<body>\n"
        '<a class="skip" href="#main">Skip to content</a>\n'
        '<div class="layout">\n'
        f"{nav}"
        '<main id="main" class="report">\n'
        f"{body}"
        "</main>\n"
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )
