"""Report engine package (v0.5.0).

Shared API target (subplan 1):

    render_md(result, remediation=None, source_path=None, enrichment=None,
              stats=None, regulatory_context=False) -> str        # 1a
    render_html(md_text, theme="light", lang="en") -> str         # 1b
    render_pdf(html_doc, theme="light", out_path=None, *, lang="en",
               title=None) -> Path                                # 1c
    report_json(result, remediation=None, stats=None) -> str      # 1a
    available_themes(config_dir=None) -> list[dict]               # 1b
    theme_css(name, config_dir=None) -> str                       # 1b

1a lands the Markdown source of truth + deterministic JSON. HTML (1b) and
tagged PDF (1c) build on ``render_md``.
"""
from .md import (
    POUR_INTROS,
    RULE_NOTES,
    RULE_TONES,
    SC_META,
    WHO_MAP,
    W3C_QUICKREF,
    W3C_UNDERSTANDING,
    compute_stats,
    render_md,
    report_json,
)

__all__ = [
    "POUR_INTROS",
    "RULE_NOTES",
    "RULE_TONES",
    "SC_META",
    "WHO_MAP",
    "W3C_QUICKREF",
    "W3C_UNDERSTANDING",
    "compute_stats",
    "render_md",
    "report_json",
]
