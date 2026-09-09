"""Markdown report engine (v0.5.0, subplan 1a).

Content source of truth for all report artifacts: WCAG 2.2 framing, POUR
sections, social-model tone, canonical W3C links, summary stats, and the
deterministic JSON report. HTML (1b) and tagged-PDF (1c) rendering build
on this Markdown.

Determinism: same input (+ same enrichment) -> byte-identical output.

Tone (decision D3): social model of disability. Barriers belong to the
document, never to people. Banned: "suffer from", "suffers", "handicapped",
"normal users", "this document is broken/inaccessible to disabled users".
"""
import json
from typing import Any, Optional, Set

from .meta import (
    POUR_INTROS,
    POUR_ORDER,
    PRINCIPLES,
    SC_META,
    W3C_QUICKREF,
    W3C_UNDERSTANDING,
)
from .stats import compute_stats
from .tone import ACROBAT_ASSISTANT_NOTES, SC_WHO_MAP, WHO_MAP

# Approved wording (subplan 1a step 4) — person-first, social model.
WHO_MAP = {
    "1.1.1": ("People who are blind or have low vision and rely on screen "
              "readers or magnification can now perceive this content."),
    "1.2.1": ("People who are deaf or hard of hearing (captions/transcripts) "
              "and people who are blind or deafblind (audio descriptions) "
              "can now access this media content."),
    "1.3.1": ("People who use screen readers, or who rely on a clear, "
              "predictable structure to read (including many people with "
              "cognitive disabilities), can now follow this document."),
    "1.4.3": ("People with low vision or color vision differences — "
              "especially in bright light, on low-quality displays, or with "
              "glare — can now read this text."),
    "1.4.12": ("People with dyslexia or other reading disabilities who need "
               "expanded line, word, or letter spacing can now read this "
               "text comfortably."),
    "2.4.1": ("People who navigate by structure — screen reader users, "
              "switch users, and anyone who skips to content — can now "
              "bypass repeated material."),
    "2.4.2": ("People who rely on document titles to find and identify "
              "materials can now tell this document apart from others."),
    "2.4.4": ("People who choose links from a list — including screen "
              "reader users — can now tell what each link will do before "
              "following it."),
    "3.1.1": ("People who use speech-recognition input, automatic "
              "translation, or screen readers with correct pronunciation "
              "can now process this document's language."),
}

# Barrier sentences (social model): what the document is missing and who is
# blocked as a result. Barriers belong to the document, never the person.
RULE_TONES = {
    "language-missing": ("The document does not declare its language, so "
                         "screen readers and speech technology may read it "
                         "in the wrong voice or pronunciation."),
    "language-malformed": ("The document declares a language that assistive "
                           "technologies may not recognize, so it may be "
                           "read incorrectly."),
    "title-missing": ("The document has no title, so people who browse "
                      "documents by title cannot tell this one apart from "
                      "the others."),
    "display-doctitle-off": ("Readers' PDF viewer will not show the document "
                             "title, so people who rely on the title to "
                             "confirm they have the right document must open "
                             "it to check."),
    "pdf-unmarked": ("The document is not marked up for assistive "
                     "technology, so people who use screen readers get "
                     "little or no structure to read by."),
    "tag-tree-missing": ("The document says it is tagged, but the tag tree "
                         "is missing, so assistive technology cannot follow "
                         "a reading order."),
    "tag-tree-weak": ("The document's tag tree is incomplete, so assistive "
                      "technology may present this content out of order or "
                      "with missing meaning."),
    "image-alt-missing": ("This image has no text alternative, so people "
                          "who rely on assistive technology to perceive "
                          "images cannot get its content."),
    "image-alt-tiny": ("This very small image may be decorative or "
                       "meaningful; without a decision about it, screen "
                       "readers either announce noise or miss content."),
    "decorative-undeclared": ("This decorative image is not marked as "
                              "decorative, so screen readers announce it as "
                              "content, interrupting the reading flow for "
                              "people who rely on them."),
    "media-no-alt": ("This media has no caption or transcript, so people "
                     "who are deaf, hard of hearing, blind, or deafblind "
                     "cannot access its content."),
    "outline-missing": ("The document has no outline, so people who "
                        "navigate by structure cannot jump to sections."),
    "link-text-vague": ("This link's name does not say what it leads to, so "
                        "people choosing links from a list — including "
                        "screen reader users — cannot tell what it will do "
                        "before following it."),
    "pdf-encrypted": ("The document is encrypted, so assistive technologies "
                      "that cannot handle the encryption cannot read it."),
    "color-contrast": ("This text's color contrast is below the minimum, so "
                       "people with low vision — especially in bright light "
                       "or on low-quality displays — may not be able to "
                       "read it."),
    "reading-order": ("The content is written out of visual reading order, "
                      "so people who rely on a predictable reading order "
                      "may encounter it in a confusing sequence."),
    "text-spacing": ("This text is rendered more tightly than comfortable "
                     "minimums, so people who need expanded line, word, or "
                     "letter spacing cannot read it comfortably."),
    "actualtext-missing": ("The table does not expose its actual text, so "
                           "assistive technology cannot convey the table's "
                           "meaning to people who rely on it."),
    "xmp-docprops-missing": ("The document's metadata is missing properties "
                             "(title, producer) that assistive technology "
                             "uses to identify and present it."),
    "parenttree-mcid-integrity": ("The structure tree's parent references "
                                  "are inconsistent, so assistive technology "
                                  "may present elements without their proper "
                                  "context."),
}

# Machine facts: what to change. (Legacy RULE_NOTES, extended to cover every
# rule_id.)
RULE_NOTES = {
    "language-missing": "Set /Lang in the catalog (default en-US).",
    "language-malformed": "Replace /Lang with a valid BCP-47 tag.",
    "title-missing": ("Set /Info /Title and XMP dc:title from the first H1, "
                      "the first outline entry, or the filename stem."),
    "display-doctitle-off": "Set /ViewerPreferences /DisplayDocTitle true.",
    "pdf-unmarked": ("Set /MarkInfo /Marked true (only when a tag tree "
                     "already exists). Untagged documents need the tag tree "
                     "built from the source (manual)."),
    "tag-tree-missing": ("Only fires when /Marked is true but the structure "
                         "tree is missing; untagged documents are reported "
                         "under pdf-unmarked."),
    "tag-tree-weak": ("Repair the tag tree's quality (headings, figures, "
                      "table headers, marked-content association) in a tag "
                      "editor or by re-exporting."),
    "image-alt-missing": ("Alt text is human content. The auto-fix inserts an "
                          "[ALT-NOT-PROVIDED: ...] marker (or applies "
                          "--alt-map text) so the location stays tracked; "
                          "replace with a real description."),
    "image-alt-tiny": ("Tiny image: decide whether it is decorative (declare "
                       "/Type /Metadata) or meaningful (give it /Alt)."),
    "decorative-undeclared": ("If the image is decorative, declare it with "
                              "/Type /Metadata so AT can skip it."),
    "media-no-alt": ("Provide a caption file or transcript for the media "
                     "(manual content). With --media-placeholder a tracked "
                     "[MEDIA-ALT-REQUIRED: ...] /Alt marker is inserted so "
                     "the gap stays machine-visible; no auto-captioning."),
    "outline-missing": ("Build the outline from H1/H2 headings "
                        "(--outline-map) or the tag tree (deterministic when "
                        "headings exist)."),
    "link-text-vague": "Rename the link to describe its purpose (manual content).",
    "pdf-encrypted": "Save an unencrypted copy for distribution (manual decision).",
    "color-contrast": ("Choose text colors meeting 4.5:1 (3:1 large text) "
                       "against the assumed page background."),
    "reading-order": ("Re-author the content stream so text is written in "
                      "visual reading order (advisory; reordering is "
                      "invasive). For tagged documents the structure tree "
                      "defines reading order and this rule does not apply."),
    "text-spacing": ("Increase line height / word / letter spacing in the "
                     "source layout so the rendered text is comfortable to "
                     "read. WCAG 1.4.12 is an override criterion (the user "
                     "must be able to set 1.5x / 0.26em / 0.12em); this rule "
                     "flags only genuinely cramped rendering, below "
                     "conservative lower bounds (advisory; a layout "
                     "decision)."),
    "actualtext-missing": ("Write an /ActualText plain-text summary of the "
                           "table (manual content)."),
    "xmp-docprops-missing": ("Add the missing XMP document properties "
                             "(dc:title, producer). Date fields are "
                             "deliberately left to the authoring tool."),
    "parenttree-mcid-integrity": ("Automatic via `fix --repair` (orphan "
                                  "repoint + ParentTree rewrite), or repair "
                                  "the /P references and ParentTree in a "
                                  "tag editor."),
}

_REGULATORY_BLURB = (
    "Some jurisdictions now require or strongly expect digital documents to "
    "be accessible — for example, Colorado HB 21-1110 (2024, "
    "accessibility in digital communication) and the accessibility "
    "expectations for ADA Title II entities. This report is not legal "
    "advice: it lists the barriers our automated checks found and how to "
    "resolve them."
)


def _normative_block(sc: str, enrichment: Optional[dict] = None) -> list:
    """Render the normative-text block for one SC (unchanged machinery)."""
    crit = (enrichment or {}).get(sc)
    if not crit:
        return []
    L = []
    L.append(f"<details><summary>Normative text — SC {sc} (official W3C "
             f"Understanding docs)</summary>")
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


def _summary_banner(total: int, stats: Optional[dict], verdict: str) -> list:
    if stats is None:
        if total == 0:
            return ["No barriers were found in this document. "
                    f"**Verdict:** {verdict}."]
        return [f"This document has **{total}** digital accessibility "
                f"barriers that can prevent people from accessing it. "
                f"**Verdict:** {verdict}."]
    found = stats["found_before"]
    remaining = stats["remaining_after"]
    if found == 0:
        return ["No barriers were found — nothing to fix "
                "(**100.0%** — no barriers found). "
                f"**Verdict:** {verdict}."]
    corrected = stats["corrected"]
    lines = [
        f"This document has **{found}** digital accessibility barriers that "
        f"can prevent people from accessing it. **{corrected}** are now "
        f"resolved; **{remaining}** remain. **Improvement:** "
        f"{stats['improvement_pct']}%. **Verdict:** {verdict}."
    ]
    if remaining == 0:
        lines.append("Every check we run now passes — and progress over "
                     "perfection keeps it that way.")
    else:
        lines.append("Every barrier removed makes this document work for "
                     "more people — progress over perfection.")
    return lines


def _finding_block(f: dict, enrichment: Optional[dict]) -> list:
    name, level, _pour, url = SC_META.get(f["sc"], (f["sc"], "?", "", W3C_QUICKREF))
    L = []
    L.append(f"### SC {f['sc']} — {name} (Level {level})")
    L.append("")
    L.append(f"[WCAG 2.2 SC {f['sc']} — {name} (official W3C Understanding "
             f"docs)]({url})")
    L.append("")
    L.append(f"- **Rule:** `{f['rule_id']}`")
    L.append(f"- **Severity:** {f['severity']}")
    L.append(f"- **Location:** {f['location']}")
    L.append(f"- **Barrier:** {RULE_TONES.get(f['rule_id']) or f['description']}")
    fix_text = f.get("fix") or RULE_NOTES.get(f["rule_id"], "")
    if f["fixable"]:
        label = "What we did"
        fix_text = fix_text or "This barrier can be fixed programmatically."
    else:
        label = "What remains"
        fix_text = fix_text or "Manual review required (content knowledge needed)."
    L.append(f"- **{label}:** {fix_text}")
    who = WHO_MAP.get(f["sc"])
    if who:
        L.append(f"- **Who benefits:** {who}")
    if f.get("evidence"):
        L.append(f"- **Evidence:** `{f['evidence']}`")
    L.append("")
    L.extend(_normative_block(f["sc"], enrichment))
    return L


def render_md(result: dict, remediation=None, source_path=None,
              enrichment: Optional[dict] = None, stats: Optional[dict] = None,
              regulatory_context: bool = False,
              enrichment_source: Optional[str] = None,
              excluded_sc: Optional[Any] = None) -> str:
    """Render the audit report as Markdown (source of truth, 1a)."""
    from pathlib import Path
    enrichment = enrichment or {}
    src = source_path or result.get("file", "document.pdf")
    summary = result["summary"]
    findings = result["findings"]
    active_excluded = set(excluded_sc or set())
    for f in findings:
        if f.get("sc") in active_excluded or f.get("excluded"):
            f["excluded"] = True

    verdict = "PASS" if summary["pass"] else "FAIL"

    L = []
    L.append(f"# Accessibility Audit Report — {src}")
    L.append("")
    L.append(f"- **File:** {src}")
    L.append(f"- **Audited:** {result.get('audited_at', 'n/a')}")
    L.append(f"- **Tool:** {result.get('tool', 'pdf-a11y')}")
    L.append("- **Standard:** WCAG 2.2 AA (subset applicable to PDF "
             "structure; PDF/UA-1 target)")
    L.append(f"- **WCAG quick reference:** {W3C_QUICKREF}")
    if enrichment_source:
        L.append(f"- **Normative text source:** {enrichment_source}")
    L.append("")

    L.append("## Summary")
    L.append("")
    L.extend(_summary_banner(summary["total"], stats, verdict))
    L.append("")

    if active_excluded or any(f.get("excluded") for f in findings):
        L.append("### What-If Analysis & Excluded Criteria")
        L.append("")
        L.append("Some WCAG criteria were excluded from active blocking compliance checks via user criteria configuration:")
        for sc in sorted(active_excluded):
            L.append(f"- `[ ] {sc}` [EXCLUDED]")
        L.append("")

    by_pour = {p: [] for p, _ in PRINCIPLES}
    for f in findings:
        by_pour.setdefault(f["sc"][0], []).append(f)
    for p, title in PRINCIPLES:
        L.append(f"## {p}. {title}")
        L.append("")
        L.append(POUR_INTROS[p])
        L.append("")
        group = by_pour.get(p, [])
        if not group:
            L.append("No barriers found in this principle.")
            if p == "4":
                L.append("No 4.x criteria are applicable to static PDF "
                         "structure.")
            L.append("")
            continue
        for f in group:
            L.extend(_finding_block(f, enrichment))

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

    if regulatory_context:
        L.append("## Regulatory context")
        L.append("")
        L.append(_REGULATORY_BLURB)
        L.append("")

    return "\n".join(L)


def report_json(result: dict, remediation=None, stats: Optional[dict] = None) -> str:
    """Data-only JSON report (CI/CD, agents, charting).

    audit result + per-finding w3c_url + stats (when given) + remediation
    (when given), schema_version 2. Deterministic (sorted keys; no extra
    timestamps beyond the existing audited_at).
    """
    data = json.loads(json.dumps(result, indent=2, sort_keys=True))
    data["schema_version"] = 2
    for f in data["findings"]:
        meta = SC_META.get(f["sc"])
        if meta:
            f["w3c_url"] = meta[3]
    if stats:
        data["stats"] = stats
    if remediation is not None:
        data["remediation"] = remediation
    return json.dumps(data, indent=2, sort_keys=True)
