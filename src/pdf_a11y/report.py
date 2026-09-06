"""Legacy report API (pre-0.5.0) — thin compat wrapper.

The engine moved to ``pdf_a11y.reports`` in v0.5.0 (subplan 1a):
WCAG 2.2 framing, POUR sections, social-model tone, W3C links, stats,
deterministic JSON. ``render_report``/``write_report`` now delegate to the
new Markdown engine (single-file legacy calls render without stats, which
the new engine treats as backward compatible).

Re-exports kept for any external importers: ``SC_NAMES``, ``RULE_NOTES``.
"""
from pathlib import Path
from typing import Optional

from .reports.md import (  # noqa: F401  (re-exported for compatibility)
    RULE_NOTES,
    RULE_TONES,
    SC_META,
    WHO_MAP,
    render_md,
    report_json,
)

# Legacy shape: sc -> (name, level, guide-string).
SC_NAMES = {
    sc: (name, level, pour)
    for sc, (name, level, pour, _url) in SC_META.items()
}


def render_report(result: dict, remediation=None, source_path=None,
                  enrichment: Optional[dict] = None,
                  enrichment_source: Optional[str] = None) -> str:
    """Legacy name for the new engine (no stats: single-file legacy call)."""
    return render_md(result, remediation=remediation, source_path=source_path,
                     enrichment=enrichment, enrichment_source=enrichment_source)


def write_report(result: dict, path, remediation=None, source_path=None,
                 enrichment: Optional[dict] = None,
                 enrichment_source: Optional[str] = None):
    text = render_report(result, remediation, source_path,
                         enrichment=enrichment,
                         enrichment_source=enrichment_source)
    Path(path).write_text(text)
    return path
