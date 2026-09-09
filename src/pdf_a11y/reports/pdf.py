"""Tagged PDF report engine (v0.5.0, subplan 1c).

Pipeline tail: render_md (1a) -> render_html (1b) -> render_pdf (1c).

The 1b HTML report body is rendered with PyMuPDF Story against the FIXED
``print`` theme — decision D1: black on white, severity conveyed by weight +
underline (not color), theme-independent — then post-processed with
DocModel (pikepdf):

  * ``/Lang`` (deterministic BCP-47)
  * ``/Info /Title`` + XMP ``dc:title`` (from the H1, or ``title=``)
  * ``/MarkInfo /Marked`` true + XMP ``pdf:Producer`` (via build_scaffold)
  * a deterministic tag tree over the rendered text (scaffold.build_plan +
    DocModel.build_scaffold — the 1c.0 blocker fix)

Ground truth (PyMuPDF 1.28.2, probe-verified in tools/spike_story.py /
/tmp/1c-spike/probe_css.py):

  * ``fitz.Story(html=..., user_css=...)`` — the CSS kwarg is ``user_css``.
  * Story honors font-weight (bold), pt sizes, table cells — but does NOT
    resolve CSS custom properties (``var()``). The token set is therefore
    resolved to explicit values before ``user_css`` is passed.
"""
import html as _html
import re
import tempfile
from pathlib import Path

import pymupdf as fitz

from ..docmodel import DocModel
from ..scaffold import build_plan
from .theme import theme_css

#: A4 print margins in points (0.75 in).
_MARGIN = 54.0

_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)
_BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.DOTALL)
_SKIP_RE = re.compile(r'<a class="skip"[^>]*>.*?</a>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_VAR_RE = re.compile(r"var\((--[a-zA-Z0-9-]+)\)")
_TOKEN_RE = re.compile(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);")


def _resolve_var(css: str) -> str:
    """Replace ``var(--token)`` with the value from the leading ``:root``.

    Story (1.28.2) does not resolve custom properties, so the theme's token
    set is inlined to explicit values. Deterministic.
    """
    root_block = css.split("}", 1)[0]
    tokens = {k: v.strip() for k, v in _TOKEN_RE.findall(root_block)}

    def _sub(m):
        return tokens.get(m.group(1), m.group(0))

    return _VAR_RE.sub(_sub, css)


def _print_css() -> str:
    """The fixed print token set + shared layout/component layers."""
    return _resolve_var(theme_css("print"))


def _extract_body(html_doc: str) -> str:
    """Just the <body> content, minus the HTML-only skip link."""
    m = _BODY_RE.search(html_doc)
    body = m.group(1) if m else html_doc
    return _SKIP_RE.sub("", body)


def _extract_h1(html_doc: str) -> str:
    m = _H1_RE.search(html_doc)
    if not m:
        return ""
    return _html.unescape(_TAG_RE.sub("", m.group(1))).strip()


def _story_to_pdf(body_html: str, user_css: str, out_path: Path) -> None:
    """Render HTML to a multi-page A4 PDF via Story (deterministic)."""
    story = fitz.Story(html=body_html, user_css=user_css)
    writer = fitz.DocumentWriter(str(out_path))
    page_rect = fitz.paper_rect("A4")
    where = fitz.Rect(_MARGIN, _MARGIN,
                      page_rect.width - _MARGIN,
                      page_rect.height - _MARGIN)
    more = True
    while more:
        dev = writer.begin_page(page_rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()


def render_pdf(html_doc: str, theme: str = "light", out_path=None, *,
               lang: str = "en", title=None) -> Path:
    """Render the 1b HTML report as an accessible, tagged PDF.

    ``theme`` is accepted for API symmetry with render_html but has NO
    effect on the PDF: the render always uses the fixed black/white
    ``print`` token set (decision D1), so the output is theme-independent
    and self-auditable.

    Returns the output path. The PDF is text-extractable/selectable,
    ``/Lang`` + ``/Title`` (+ XMP) set, and carries a deterministic tag
    tree (``/MarkInfo /Marked`` true, ``/StructTreeRoot`` present).
    """
    if out_path is None and (isinstance(theme, Path) or (isinstance(theme, str) and theme.endswith(".pdf"))):
        out_path = theme
        theme = "light"
    out_path = Path(out_path) if out_path else Path("report.pdf")
    body = _extract_body(html_doc)
    css = _print_css()
    doc_title = (title or _extract_h1(html_doc)
                 or "Accessibility Report")

    fd, tmp_name = tempfile.mkstemp(suffix=".pdf", prefix="pdf-a11y-")
    import os
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        _story_to_pdf(body, css, tmp)

        dm = DocModel.open(tmp)
        try:
            dm.set_lang(lang)
            dm.set_title(doc_title)
            plan = build_plan(tmp)
            dm.build_scaffold(plan.blocks_by_page())
            with dm.doc.open_metadata(set_pikepdf_as_editor=False) as meta:
                meta["pdf:Producer"] = "pdf-a11y accessible PDF engine"
                if "xmp:MetadataDate" in meta:
                    del meta["xmp:MetadataDate"]
                if "xmp:ModifyDate" in meta:
                    del meta["xmp:ModifyDate"]
                if "xmp:CreateDate" in meta:
                    del meta["xmp:CreateDate"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            dm.save(out_path)
        finally:
            dm.close()
    finally:
        tmp.unlink(missing_ok=True)
    return out_path
