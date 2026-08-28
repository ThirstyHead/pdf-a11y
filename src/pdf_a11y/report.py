"""Markdown report generator: audit result JSON -> accessibility-audit-report.md.

Deterministic: same input JSON (+ same enrichment source) -> byte-identical output.

Enrichment: when ``enrichment`` is provided (a {sc: parsed-criterion} dict,
see pdf_a11y.enrich), each finding is followed by a normative-text block
sourced from the official WCAG Understanding documentation (bundled cache or
live wcag-guidelines-mcp).
"""
from pathlib import Path
from typing import Optional

SC_NAMES = {
    "1.1.1": ("Non-text Content", "A", "1 Perceivable / 1.1 Text Alternatives"),
    "1.3.1": ("Info and Relationships", "A", "1 Perceivable / 1.3 Adaptable"),
    "1.4.3": ("Contrast (Minimum)", "AA", "1 Perceivable / 1.4 Distinguishable"),
    "2.4.1": ("Bypass Blocks", "A", "2 Operable / 2.4 Navigable (applied to the PDF outline)"),
    "2.4.2": ("Page Titled", "A", "2 Operable / 2.4 Navigable (applied by convention to document title metadata)"),
    "2.4.4": ("Link Purpose (In Context)", "A", "2 Operable / 2.4 Navigable (applied to link annotation names)"),
    "3.1.1": ("Language of Page", "A", "3 Understandable / 3.1 Readable"),
}

RULE_NOTES = {
    "language-missing": "Set /Lang in the catalog (default en-US).",
    "language-malformed": "Replace /Lang with a valid BCP-47 tag.",
    "title-missing": "Set /Info /Title and XMP dc:title from the first H1, the first "
                     "outline entry, or the filename stem.",
    "display-doctitle-off": "Set /ViewerPreferences /DisplayDocTitle true.",
    "pdf-unmarked": "Set /MarkInfo /Marked true (only when a tag tree already exists). "
                    "Untagged documents need the tag tree built from the source (manual).",
    "tag-tree-missing": "Only fires when /Marked is true but the structure tree is "
                       "missing; untagged documents are reported under pdf-unmarked.",
    "tag-tree-weak": "Repair the tag tree's quality (headings, figures, table headers, "
                     "marked-content association) in a tag editor or by re-exporting.",
    "image-alt-missing": "Alt text is human content. The auto-fix inserts an "
                         "[ALT-NOT-PROVIDED: ...] marker (or applies --alt-map text) so "
                         "the location stays tracked; replace with a real description.",
    "image-alt-tiny": "Tiny image: decide whether it is decorative (declare /Type /Metadata) "
                      "or meaningful (give it /Alt).",
    "decorative-undeclared": "If the image is decorative, declare it with /Type /Metadata "
                             "so AT can skip it.",
    "outline-missing": "Build the outline from H1/H2 headings (--outline-map) or the tag "
                       "tree (deterministic when headings exist).",
    "link-text-vague": "Rename the link to describe its purpose (manual content).",
    "pdf-encrypted": "Save an unencrypted copy for distribution (manual decision).",
    "color-contrast": "Choose text colors meeting 4.5:1 (3:1 large text) against the "
                      "assumed page background.",
}


def _normative_block(sc: str, enrichment: dict) -> list:
    """Render the normative-text block for one SC (from enrichment dict)."""
    crit = enrichment.get(sc)
    if not crit:
        return []
    L = []
    L.append(f"<details><summary>Normative text — SC {sc} (official W3C Understanding docs)</summary>")
    L.append("")
    if crit.get("in_brief"):
        L.append(crit["in_brief"])
        L.append("")
    if crit.get("description"):
        L.append("**Description:**")
        L.append("")
        L.append(crit["description"])
        L.append("")
    if crit.get("intent"):
        L.append("**Intent:**")
        L.append("")
        intent_lines = crit["intent"].splitlines()
        L.extend(intent_lines[:160])
        if len(intent_lines) > 160:
            L.append(f"_(truncated: {len(intent_lines) - 160} more lines)_")
        L.append("")
    L.append("</details>")
    L.append("")
    return L


def render_report(result: dict, remediation=None, source_path=None,
                  enrichment: Optional[dict] = None,
                  enrichment_source: Optional[str] = None) -> str:
    src = source_path or result.get("file", "document.pdf")
    summary = result["summary"]
    findings = result["findings"]
    enrichment = enrichment or {}
    L = []
    L.append(f"# Accessibility Audit Report — {src}")
    L.append("")
    L.append(f"- **File:** {src}")
    L.append(f"- **Audited:** {result.get('audited_at', 'n/a')}")
    L.append(f"- **Tool:** {result.get('tool', 'pdf-a11y')}")
    L.append("- **Standard:** WCAG 2.1 AA (PDF/UA-1 target)")
    L.append("- **Verdict:** " + ("PASS" if summary["pass"] else "FAIL (blocking violations)"))
    L.append(f"- **Findings:** {summary['total']} "
             f"(critical={summary['by_severity']['critical']}, "
             f"serious={summary['by_severity']['serious']}, "
             f"moderate={summary['by_severity']['moderate']}, "
             f"minor={summary['by_severity']['minor']})")
    if enrichment_source:
        L.append(f"- **Normative text source:** {enrichment_source}")
    L.append("")
    L.append("## Scope note")
    L.append("")
    L.append("Keyboard/interaction criteria (2.x) are largely N/A for static PDFs; 2.4.1 "
             "(bypass blocks) and 2.4.4 (link purpose) are applied to the PDF outline and "
             "link annotations, which are the PDF equivalents. 2.4.2 is applied by "
             "convention to document title metadata. 3.1.1 covers the document's "
             "declared language (/Lang).")
    L.append("")

    if findings:
        L.append("## Findings")
        L.append("")
        for n, f in enumerate(findings, 1):
            name, level, guide = SC_NAMES.get(f["sc"], ("", f["sc"], ""))
            L.append(f"### {n}. {f['severity'].upper()} — SC {f['sc']} {name} (Level {level})")
            L.append(f"- **Rule:** `{f['rule_id']}`")
            L.append(f"- **Guideline:** {guide}")
            L.append(f"- **Location:** {f['location']}")
            L.append(f"- **Description:** {f['description']}")
            if f.get("evidence"):
                L.append(f"- **Evidence:** `{f['evidence']}`")
            L.append(f"- **Action:** {'Programmatically fixable' if f['fixable'] else 'Manual review required'}")
            fix_text = f.get("fix") or RULE_NOTES.get(f["rule_id"], "")
            if fix_text:
                L.append(f"- **Fix:** {fix_text}")
            L.append("")
            L.extend(_normative_block(f["sc"], enrichment))
    else:
        L.append("## Findings")
        L.append("")
        L.append("None. All rules passed.")
        L.append("")

    if remediation is not None:
        rr = remediation if isinstance(remediation, dict) else {}
        L.append("## Remediation")
        L.append("")
        if rr.get("output_path"):
            L.append(f"- **Output:** {rr['output_path']}")
        applied = rr.get("applied", [])
        skipped = rr.get("skipped", [])
        L.append(f"- **Applied fixes:** {len(applied)}")
        for a in applied:
            L.append(f"  - `{a[0]}` @ {a[1]}")
        L.append(f"- **Skipped (manual):** {len(skipped)}")
        for s in skipped:
            reason = s[2] if len(s) > 2 else ""
            L.append(f"  - `{s[0]}` @ {s[1]}" + (f" — {reason}" if reason else ""))
        L.append("")

    manual = [f for f in findings if not f["fixable"]]
    if manual:
        L.append("## Residual manual work")
        L.append("")
        for f in manual:
            note = RULE_NOTES.get(f["rule_id"]) or f.get("fix", f["description"])
            L.append(f"- **{f['rule_id']}** @ {f['location']}: {note}")
        L.append("")

    L.append("## Re-verify")
    L.append("")
    L.append("```bash")
    L.append(f"pdf-a11y audit {Path(src).stem}.fixed.pdf --json reaudit.json")
    L.append("```")
    L.append("")
    return "\n".join(L)


def write_report(result: dict, path, remediation=None, source_path=None,
                 enrichment: Optional[dict] = None,
                 enrichment_source: Optional[str] = None):
    text = render_report(result, remediation, source_path,
                         enrichment=enrichment, enrichment_source=enrichment_source)
    Path(path).write_text(text)
    return path