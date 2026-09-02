"""Audit rules for WCAG 2.1 AA on PDF files (PDF/UA-1 target).

Each Rule implements:
    check(dm, ctx)  -> list[Finding]      # dm: pdf_a11y.docmodel.DocModel
    fix(dm, finding, ctx) -> bool         # deterministic fixes only; False = manual

Rules are ordered in RULES. A broken rule is captured as an internal finding
by the audit engine and never kills the run.

Scope (per local a11y wiki, pdf-a11y-workflow):
  - 2.x keyboard/interaction criteria are largely N/A for static PDFs;
    2.4.1 (bypass blocks) and 2.4.4 (link purpose) are applied to the
    document outline and link annotations, which ARE the PDF equivalents.
  - 1.2.x media alternatives: media-no-alt detects media objects lacking
    /Alt; the caption/transcript is human content (no auto-captioning).
  - 3.1.1 / 3.2.x / 3.3.x are out of scope for static document content.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pikepdf

from .contrast import contrast_ratio, hex_to_rgb
from .docmodel import DocModel, key, member, new_dict, norm_name
from .findings import Finding
from .readingorder import reading_order_report
from .spacing import spacing_report

LANG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
BAD_LINK_TEXT = re.compile(
    r"^(click here|here|read more|link|this link|click this|more|details?)$", re.I)

# Roles allowed as the root structural element of a tagged PDF (PDF 32000-1
# 14.7.7; the PDF/UA convention in practice).
ROOT_ROLES = {"Document"}


@dataclass
class AuditContext:
    """Knobs that make audits deterministic and caller-controlled."""

    source_name: str = "document.pdf"
    default_language: str = "en-US"
    background_rgb: str = "FFFFFF"          # assumed page background for contrast
    large_text_size_pt: float = 18.0
    large_text_bold_pt: float = 14.0
    # deterministic alt-text injection: "page:name=text" entries applied when
    # the image-alt-missing fix runs (e.g. "0:Image28=Loaf of no knead bread").
    alt_map: dict = field(default_factory=dict)   # {(page:int, name:str): text}
    # deterministic outline for the outline-missing fix:
    # [(level, title, page_no_0based), ...]
    outline_map: list = field(default_factory=list)
    # opt-in deterministic tag-tree scaffolding for untagged documents
    # (Phase 5; default off so default fix behavior is untouched)
    scaffold: bool = False
    # reading-order (SC 1.3.1) max tolerated stream/visual inversion count
    # before the reading-order rule fires (1 = one adjacent swap ok)
    reading_order_tolerance: int = 1
    # text-spacing (SC 1.4.12) conservative *lower* bounds: a page is flagged
    # when its minimum observed spacing falls below the matching bound. These
    # are far below the WCAG 1.4.12 override targets (1.5x / 0.26em / 0.12em)
    # because those are user-settable targets, not as-rendered minimums; the
    # bounds only catch genuinely cramped rendering (see spacing.py).
    text_spacing_line_min: float = 1.0
    text_spacing_word_min: float = 0.08
    text_spacing_letter_min: float = -0.12
    # opt-in: when true, media-no-alt findings become fixable and the fix
    # writes a machine-clear [MEDIA-ALT-REQUIRED: ...] placeholder /Alt on
    # the media object (transcript/caption itself is still manual — no
    # auto-captioning, per the roadmap non-goals).
    media_placeholder: bool = False
    # opt-in: OCR text-less (scanned) pages before audit/fix (Phase A).
    # When True and a backend is present, `fix` runs an OCR pre-pass; when the
    # backend is absent it degrades gracefully (no traceback) and notes it.
    ocr: bool = False
    # opt-in: repair already-tagged-but-weak trees (Phase B). Implies scaffold.
    repair: bool = False


# ---------------------------------------------------------------------------
# shared doc-level checks (used by several rules)
# ---------------------------------------------------------------------------

def _catalog_findings(dm, ctx):
    """Core PDF/UA catalog requirements. Returns (taggable, lang_findings, title_findings, display_findings)."""
    has_str = dm.struct_tree() is not None
    marked = dm.is_marked()

    lang_f = []
    lang = dm.lang()
    if not dm.has_lang():
        lang_f.append(Finding("language-missing", "3.1.1", "moderate", "catalog",
                              "Document has no /Lang entry; assistive technology cannot "
                              "determine the default language.",
                              "/Lang absent", True,
                              f"Set /Lang to '{ctx.default_language}' (deterministic)."))
    elif not LANG_RE.fullmatch(lang):
        lang_f.append(Finding("language-malformed", "3.1.1", "moderate", "catalog",
                              "Document /Lang is not a valid BCP-47 language tag.",
                              f"/Lang={lang!r}", True,
                              f"Replace with a valid tag such as '{ctx.default_language}'."))

    title_f = []
    if not dm.title():
        title_f.append(Finding("title-missing", "2.4.2", "moderate", "catalog",
                               "Document has no title (/Info /Title and XMP dc:title "
                               "both empty); document naming is impossible.",
                               "/Info.Title empty, dc:title empty", True,
                               "Set title from the first H1 structural element, the "
                               "first outline entry, or the filename stem (deterministic)."))

    display_f = []
    if not dm.display_doc_title():
        display_f.append(Finding("display-doctitle-off", "2.4.2", "minor", "catalog",
                                 "ViewerPreferences does not request the document title "
                                 "be displayed (/DisplayDocTitle false).",
                                 "/DisplayDocTitle absent/false", True,
                                 "Set /ViewerPreferences /DisplayDocTitle true."))

    return has_str, marked, lang_f, title_f, display_f


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

class LanguageMissing:
    """SC 3.1.1: default language must be declared in the catalog /Lang."""

    rule_id = "language-missing"
    sc = "3.1.1"
    severity = "moderate"

    def check(self, dm, ctx):
        _, _, lang_f, _, _ = _catalog_findings(dm, ctx)
        return lang_f

    def fix(self, dm, finding, ctx):
        if finding.rule_id == "language-malformed":
            dm.set_lang(ctx.default_language)
        else:
            dm.set_lang(ctx.default_language)
        return True


class TitleMissing:
    """SC 2.4.2 (by convention): document title metadata must be non-empty."""

    rule_id = "title-missing"
    sc = "2.4.2"
    severity = "moderate"

    def check(self, dm, ctx):
        _, _, _, title_f, _ = _catalog_findings(dm, ctx)
        return title_f

    def fix(self, dm, finding, ctx):
        title = _pick_title(dm, ctx)
        if not title:
            return False
        dm.set_title(title)
        return True


class DisplayDocTitle:
    """SC 2.4.2 (minor): viewer should display the document title."""

    rule_id = "display-doctitle-off"
    sc = "2.4.2"
    severity = "minor"

    def check(self, dm, ctx):
        _, _, _, _, display_f = _catalog_findings(dm, ctx)
        return display_f

    def fix(self, dm, finding, ctx):
        dm.set_display_doc_title(True)
        return True


class UnmarkedPdf:
    """SC 1.3.1 / PDF-UA: document must be marked tagged with /Marked true."""

    rule_id = "pdf-unmarked"
    sc = "1.3.1"
    severity = "serious"

    def check(self, dm, ctx):
        has_str, marked, _, _, _ = _catalog_findings(dm, ctx)
        if marked:
            return []
        if has_str:
            return [Finding(self.rule_id, self.sc, self.severity, "catalog",
                            "StructTreeRoot exists but /MarkInfo /Marked is not true; "
                            "the document is not declared tagged.",
                            "/MarkInfo absent or /Marked false", True,
                            "Set /MarkInfo /Marked true (deterministic).")]
        # With --scaffold, the tree is created deterministically, so this
        # finding IS fixable (the scaffold path runs before this rule's fix).
        return [Finding(self.rule_id, self.sc, self.severity, "catalog",
                        "Document is untagged: no /MarkInfo /Marked and no "
                        "StructTreeRoot. Assistive technology has no logical "
                        "structure to consume.",
                        "/MarkInfo absent, StructTreeRoot absent", bool(ctx.scaffold),
                        "Create a tag tree (manual: use a PDF tag editor or re-export "
                        "from the source document with structure). With --scaffold, "
                        "a deterministic tag tree is scaffolded from the content "
                        "stream (best-effort; review before PDF/UA certification).")]

    def fix(self, dm, finding, ctx):
        # Marking a document with no tag tree would be a lie; either the tree
        # exists and the flag was dropped, or --scaffold builds the tree.
        if dm.struct_tree() is None:
            if ctx.scaffold:
                return _scaffold_fix(dm, ctx)
            return False
        dm.set_marked(True)
        return True


class MissingTagTree:
    """SC 1.3.1 / PDF-UA: /StructTreeRoot must exist in a tagged PDF.

    Only fires for the inconsistent state "/Marked true but no tree".
    An untagged document (no Marked, no tree) is reported exactly once,
    by UnmarkedPdf — the missing tree is that finding's root cause, not a
    second finding.
    """

    rule_id = "tag-tree-missing"
    sc = "1.3.1"
    severity = "serious"

    def check(self, dm, ctx):
        if dm.struct_tree() is not None:
            return []
        if not dm.is_marked():
            # Untagged (no Marked, no tree) is reported once, by UnmarkedPdf.
            return []
        return [Finding(self.rule_id, self.sc, self.severity, "catalog",
                        "/MarkInfo /Marked is true but /StructTreeRoot is absent; "
                        "the document claims tagging without a structure tree.",
                        "Marked=true, StructTreeRoot absent", True,
                        "Restore the structure tree (manual) or drop the Marked flag.")]

    def fix(self, dm, finding, ctx):
        if not ctx.scaffold:
            return False
        if dm.struct_tree() is not None:
            dm.set_marked(True)
            return True
        return _scaffold_fix(dm, ctx)


class WeakTagTree:
    """SC 1.3.1 / PDF-UA: tagged PDF structure quality (headings, figures,
    table semantics, marked-content associations)."""

    rule_id = "tag-tree-weak"
    sc = "1.3.1"
    severity = "serious"

    def check(self, dm, ctx):
        st = dm.struct_tree()
        if st is None:
            return []
        out = []
        entries = list(dm.walk_struct(st))
        n_el = sum(1 for e in entries if e[4] is not None and not isinstance(e[4], int))

        # root role / first child role (weak signal, logged in evidence only)
        root_s = norm_name(key(st, "S")) or "Document"
        root_k = key(st, "K")
        first_child_s = None
        if root_k is not None:
            if isinstance(root_k, pikepdf.Array):
                first = root_k[0]
            else:
                first = root_k
            if not isinstance(first, int):
                try:
                    first_child_s = norm_name(key(first, "S"))
                except Exception:
                    first_child_s = None

        headings = dm.heading_levels(st)
        n_head = len(headings)
        n_fig = sum(1 for e in entries if e[1] == "Figure")
        n_alt = sum(1 for e in entries if e[1] == "Figure" and e[2])

        # 1. no headings at all in a tagged document (structure exists but is flat)
        if n_el > 1 and n_head == 0:
            out.append(Finding(self.rule_id, self.sc, self.severity, "StructTreeRoot",
                               f"Tag tree has {n_el} elements but no heading roles "
                               "(H1-H6); the document hierarchy is invisible to AT.",
                               f"elements={n_el}, headings=0", True,
                               "Promote section titles to heading roles (manual unless "
                               "the titles are recoverable from the content)."))

        # 2. heading level skips
        prev = None
        for lvl, text in headings:
            if prev is not None and lvl - prev > 1:
                out.append(Finding(self.rule_id, self.sc, self.severity,
                                   f"StructTreeRoot heading {text[:30]!r}",
                                   f"Heading level skipped: H{prev} -> H{lvl}.",
                                   f"level={lvl}, text={text[:40]!r}", False,
                                   "Insert the intermediate heading or re-level the "
                                   "heading (manual: tag editor)."))
            prev = lvl

        # 3. figures without alt
        figs_no_alt = n_fig - n_alt
        if figs_no_alt > 0:
            out.append(Finding(self.rule_id, self.sc, self.severity, "StructTreeRoot",
                               f"{figs_no_alt} of {n_fig} Figure structure elements have "
                               "no Alt description.",
                               f"figures={n_fig}, with_alt={n_alt}", False,
                               "Write Alt text for each figure (manual content)."))

        # 4. tables without header cells
        for ti, nrows, nh in dm.table_stats(st):
            if nrows > 0 and nh == 0:
                out.append(Finding(self.rule_id, self.sc, self.severity,
                                   f"StructTreeRoot table[{ti}]",
                                   f"Table has {nrows} rows but no TH (header) cells; "
                                   "column semantics are lost for AT.",
                                   f"rows={nrows}, header_cells=0", False,
                                   "Mark header row/cells with TH role (manual: tag editor)."))

        # 5. marked content associations
        bdc, emc, _ = dm.content_bdc_counts()
        if n_el > 1 and bdc == 0:
            out.append(Finding(self.rule_id, self.sc, self.severity, "content streams",
                               "Structure tree exists but no page content carries "
                               "marked-content (BDC/EMC) operators; the structure is "
                               "not associated with visible content.",
                               f"BDC=0, EMC=0, struct_elements={n_el}", False,
                               "Regenerate the tagged export (manual: re-export from "
                               "the source with tagging enabled)."))
        elif n_el > 1 and bdc != emc:
            out.append(Finding(self.rule_id, self.sc, self.severity, "content streams",
                               "Unbalanced marked-content operators (BDC != EMC); "
                               "tag association is corrupted.",
                               f"BDC={bdc}, EMC={emc}", False,
                               "Regenerate the tagged export (manual)."))

        # 6. orphaned structure elements (missing /P parent pointer)
        orphans = sum(1 for e in entries
                      if not isinstance(e[4], int) and e[3] is False)
        if orphans:
            out.append(Finding(self.rule_id, self.sc, self.severity, "StructTreeRoot",
                               f"{orphans} structure element(s) lack a /P parent pointer; "
                               "tag tree is malformed.",
                               f"orphans={orphans}", bool(ctx.repair),
                               "Repair the tag tree (automatic with fix --repair; "
                               "otherwise manual: tag editor or re-export)."))
        return out

    def fix(self, dm, finding, ctx):
        # Opt-in (repair implies scaffold in the CLI): repoint orphaned /P
        # elements and repair the ParentTree. Content-level weaknesses are
        # deliberately NOT guessed at (see repair.repair_weak_tree).
        if ctx.scaffold and ctx.repair:
            from .repair import repair_weak_tree
            r = repair_weak_tree(dm)
            return (r["repointed"] + r["parenttree_fixed"]) > 0
        return False


class ImageAltMissing:
    """SC 1.1.1: every page image needs alternative text (XObject /Alt) or a
    decorated decorative marker (/Type /Metadata)."""

    rule_id = "image-alt-missing"
    sc = "1.1.1"
    severity = "critical"

    def check(self, dm, ctx):
        out = []
        for pi, name, obj, res, owner in dm.images:
            # images wrapped in a Figure structure element get their alt there;
            # we can't cheaply match MCID->XObject, so flag by absence and let
            # the figure check handle the structural side.
            if key(obj, "Alt") is not None and str(key(obj, "Alt")).strip():
                continue
            if str(key(obj, "Type")) == "/Metadata":  # decorative marker
                continue
            # tiny/blank images (smash patterns, logos < 8px) are advisory
            w = int(key(obj, "Width") or 0)
            h = int(key(obj, "Height") or 0)
            severity = self.severity
            if 0 < max(w, h) < 8:
                severity = "minor"
            rule_id = "image-alt-tiny" if severity == "minor" else self.rule_id
            out.append(Finding(rule_id,
                               self.sc, severity, f"page[{pi}] /{name}",
                               f"Image /{name} has no /Alt alternative text and no "
                               "decorative marker.",
                               f"{w}x{h}", True,
                               "Provide a human-written description (--alt-map "
                               "'page:name=text'); auto-fix inserts a tracked "
                               "[ALT-NOT-PROVIDED: ...] placeholder."))
        return out

    def fix(self, dm, finding, ctx):
        if finding.rule_id == "image-alt-tiny":
            return False  # tiny images: leave to manual decision
        m = re.match(r"page\[(\d+)\]\s+/(\S+)", finding.location)
        if not m:
            return False
        pi, name = int(m.group(1)), m.group(2)
        text = ctx.alt_map.get((pi, name))
        if not text:
            title = dm.title() or ctx.source_name
            text = f"[ALT-NOT-PROVIDED: image /{name} on page {pi + 1} in '{title}' - insert a human-written description]"
        return dm.set_image_alt(pi, name, text)


class DecorativeImageUndeclared:
    """SC 1.1.1 (minor): decorative images should be declared (/Type /Metadata)
    so AT can skip them. Advisory: we cannot know intent automatically."""

    rule_id = "decorative-undeclared"
    sc = "1.1.1"
    severity = "minor"

    def check(self, dm, ctx):
        out = []
        for pi, name, obj, res, owner in dm.images:
            w = int(key(obj, "Width") or 0)
            h = int(key(obj, "Height") or 0)
            # small non-content-sized images are *probably* decorative: advisory
            if 8 <= max(w, h) <= 16 and min(w, h) <= 8 and key(obj, "Alt") is None:
                out.append(Finding(self.rule_id, self.sc, self.severity,
                                   f"page[{pi}] /{name}",
                                   f"Small image /{name} ({w}x{h}) may be decorative; "
                                   "if so, declare it decorative so AT can ignore it.",
                                   f"{w}x{h}", True,
                                   "Set /Type /Metadata on the XObject (deterministic "
                                   "if decorative) or provide /Alt."))
        return out

    def fix(self, dm, finding, ctx):
        m = re.match(r"page\[(\d+)\]\s+/(\S+)", finding.location)
        if not m:
            return False
        return dm.set_image_alt(int(m.group(1)), m.group(2), "", decorative=True)


class OutlineMissing:
    """SC 2.4.1 / 2.4.4 (PDF equivalents): an outline/TOC gives AT users a
    way to bypass blocks and navigate; entries need descriptive titles."""

    rule_id = "outline-missing"
    sc = "2.4.1"
    severity = "moderate"

    def check(self, dm, ctx):
        if dm.outlines:
            return []
        # The fix needs *either* --outline-map *or* existing headings; without
        # both it cannot succeed, so report the honest fixable state. With
        # --scaffold, an untagged doc gets a deterministic tree first, after
        # which the outline IS derivable from its headings.
        derivable = bool(ctx.outline_map) or (
            dm.struct_tree() is not None
            and any(t.strip() for _, t in dm.heading_levels(dm.struct_tree())))
        if not derivable and ctx.scaffold:
            derivable = True
        return [Finding(self.rule_id, self.sc, self.severity, "catalog",
                        "Document has no outline (TOC); assistive technology users "
                        "cannot navigate by structure.",
                        "/Outlines absent", derivable,
                        "Build the outline from H1/H2 headings (--outline-map "
                        "'level=title:page' entries) or from the tag tree "
                        "(deterministic when headings exist). With --scaffold, "
                        "an untagged document gets a deterministic tree first.")]

    def fix(self, dm, finding, ctx):
        entries = list(ctx.outline_map)
        if not entries:
            # derive from tag-tree headings when available
            st = dm.struct_tree()
            if st is not None:
                prev_page = 0
                for lvl, text in dm.heading_levels(st):
                    if text.strip():
                        entries.append((lvl, text.strip(), prev_page))
        if not entries:
            return False
        return dm.set_outline(entries)


class BadLinkText:
    """SC 2.4.4: link annotations should have descriptive accessible names."""

    rule_id = "link-text-vague"
    sc = "2.4.4"
    severity = "moderate"

    def check(self, dm, ctx):
        out = []
        for pi, page in enumerate(dm.pages):
            annots = key(page, "Annots")
            if annots is None:
                continue
            for ann in annots:
                if str(key(ann, "Subtype")) != "/Link":
                    continue
                t = key(ann, "T")
                if t is None or not str(t).strip():
                    continue
                txt = str(t).strip()
                if BAD_LINK_TEXT.fullmatch(txt):
                    out.append(Finding(self.rule_id, self.sc, self.severity,
                                       f"page[{pi}] link {txt!r}",
                                       f"Link has non-descriptive accessible text "
                                       f"{txt!r}; users cannot tell where it leads.",
                                       f"/T={txt!r}", False,
                                       "Rename the link text to describe its purpose "
                                       "(manual content)."))
        return out

    def fix(self, dm, finding, ctx):
        return False


class EncryptedPdf:
    """SC 1.4.x (prerequisite): encrypted PDFs may block AT extraction entirely.
    Advisory: a strong owner password defeats reading, but a user-password-only
    PDF is still machine-readable."""

    rule_id = "pdf-encrypted"
    sc = "1.3.1"
    severity = "moderate"

    def check(self, dm, ctx):
        if not dm.doc.is_encrypted:
            return []
        perms = ""
        try:
            perms = " user-password" if dm.doc.owner_password else " owner-encrypted"
        except Exception:
            perms = " unknown"
        return [Finding(self.rule_id, self.sc, self.severity, "document",
                        f"Document is encrypted{perms}; some assistive technology and "
                        "audit tools cannot read the content.",
                        "is_encrypted=True", False,
                        "Save an unencrypted copy for distribution (manual decision).")]

    def fix(self, dm, finding, ctx):
        return False


class ColorContrast:
    """SC 1.4.3: text colors must meet 4.5:1 (3:1 large) against the assumed
    background. PDF text color lives in content streams (rg/RG/Tc/TI), which
    are hard to parse portably, so this rule checks what IS deterministic:
    XObject-based graphics are out of scope; the rule therefore scans the
    page's marked content for /cs (color space) operators only when a
    flat-background assumption holds. For now: advisory scan of content
    stream colors where unambiguous (direct rg values near text ops)."""

    rule_id = "color-contrast"
    sc = "1.4.3"
    severity = "moderate"

    def check(self, dm, ctx):
        out = []
        bg = hex_to_rgb(ctx.background_rgb)
        if bg is None:
            return out
        for pi, page in enumerate(dm.pages):
            for data in dm._page_content_bytes(page):
                s = data.decode("latin-1", "replace")
                # direct non-stroking colors: <r> <g> <b> rg
                for m in re.finditer(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg", s):
                    try:
                        r, g, b = (int(round(float(m.group(i)) * 255)) for i in (1, 2, 3))
                    except ValueError:
                        continue
                    if not all(0 <= c <= 255 for c in (r, g, b)):
                        continue
                    rgb = (r, g, b)
                    ratio = contrast_ratio(rgb, bg)
                    # large-text threshold unknown from operator context; use the
                    # stricter normal threshold to avoid false negatives
                    if ratio < 4.5:
                        out.append(Finding(self.rule_id, self.sc, self.severity,
                                           f"page[{pi}] content stream",
                                           f"Text color #{r:02X}{g:02X}{b:02X} fails "
                                           f"contrast: {ratio:.2f}:1 < 4.5:1 (assumed "
                                           f"background #{ctx.background_rgb}); may be "
                                           "below 3:1 for large text as well.",
                                           f"color=#{r:02X}{g:02X}{b:02X}, ratio={ratio:.2f}",
                                           False,
                                           "Choose a text color meeting 4.5:1 (3:1 large "
                                           "text) against the page background (manual)."))
        # de-duplicate identical findings per page (same color may repeat)
        seen = set()
        deduped = []
        for f in out:
            k = (f.location, f.evidence)
            if k in seen:
                continue
            seen.add(k)
            deduped.append(f)
        return deduped

    def fix(self, dm, finding, ctx):
        return False


class ReadingOrder:
    """SC 1.3.1: the content-stream (extraction) order must match the visual
    reading order so assistive technology reads the text in the order a sighted
    reader would see it.

    The old stream-order *assumption* never verified this; it just assumed the
    content stream was authored in reading order. This rule replaces that
    assumption with a geometric check: it measures how many pairs of text
    lines appear in the opposite relative order in the content stream vs the
    column-aware visual order (an inversion count). A divergence above the
    configured tolerance (default 1, i.e. one adjacent swap) is a finding.

    Deterministic: pure geometry over PyMuPDF's text dict, no network/AI, and
    it does not depend on tagging (extraction order matters whether or not the
    document is tagged). No deterministic fix is offered (re-authoring the
    content stream is a manual decision), so findings are advisory and do not
    block on their own.
    """

    rule_id = "reading-order"
    sc = "1.3.1"
    severity = "moderate"

    def check(self, dm, ctx):
        # Tagged documents get their reading order from the structure tree
        # (Steps 6/7 validate that), not the content stream — so a
        # content-stream geometry check is the wrong oracle for them and would
        # false-positive (e.g. on fixtures whose stream is intentionally
        # scrambled but correctly tagged). Only untagged documents, where the
        # content stream *is* the extraction order, are checked here.
        if dm.struct_tree() is not None:
            return []
        tol = getattr(ctx, "reading_order_tolerance", 1)
        try:
            pages = reading_order_report(str(dm.path), tolerance=tol)
        except Exception:
            # A PDF PyMuPDF cannot read should not break the whole audit; the
            # geometric check is best-effort.
            return []
        out = []
        for pg in pages:
            if pg.n_lines < 2:
                continue
            if not pg.streams_ok:
                out.append(Finding(
                    self.rule_id, self.sc, self.severity,
                    f"page[{pg.page_no}]",
                    f"Content-stream text order diverges from the visual reading "
                    f"order on page {pg.page_no + 1} ({pg.inversions} inverted "
                    f"line pair(s); tolerance {tol}). Screen readers will read the "
                    "text out of visual order.",
                    f"inversions={pg.inversions}, tolerance={tol}, "
                    f"lines={pg.n_lines}",
                    False,
                    "Re-author the content stream so text is written in visual "
                    "reading order (manual)."))
        return out

    def fix(self, dm, finding, ctx):
        return False


class TextSpacing:
    """SC 1.4.12: text must not be rendered so tightly that it is hard to read.

    WCAG 1.4.12 is an *override* criterion — the user must be able to *set*
    line height to 1.5x, word spacing to 0.26em (0.12em CJK), and letter
    spacing to 0.05em without loss of content. Those are targets the user can
    reach, NOT as-rendered minimums: virtually all normal text renders with
    line height ~1.2-1.5x and word spacing ~0.2em, so a literal "flag if below
    WCAG value" rule would flag every ordinary document (and every committed
    fixture).

    This rule therefore measures the *minimum* observed line height (baseline
    gap / font size), word spacing (inter-word gap / font size, em), and letter
    spacing (intra-word char gap / font size, em) per page via
    :mod:`pdf_a11y.spacing`, and emits a finding when a minimum falls below a
    conservative lower bound (``AuditContext.text_spacing_*``; defaults
    line<1.0x, word<0.08em, letter<-0.12em). It reports the offending text so
    the issue is locatable. Advisory (fixable=False): spacing remediation is a
    layout decision. Deterministic geometry, no network/AI.
    """

    rule_id = "text-spacing"
    sc = "1.4.12"
    severity = "moderate"

    def check(self, dm, ctx):
        line_min = getattr(ctx, "text_spacing_line_min", 1.0)
        word_min = getattr(ctx, "text_spacing_word_min", 0.08)
        letter_min = getattr(ctx, "text_spacing_letter_min", -0.12)
        try:
            pages = spacing_report(str(dm.path))
        except Exception:
            # A PDF PyMuPDF cannot read should not break the whole audit.
            return []
        out = []
        for pg in pages:
            issues = []
            if pg.min_line_height is not None and pg.min_line_height < line_min:
                issues.append(
                    f"line height {pg.min_line_height:.2f}x < {line_min}x"
                    + (f" at '{pg.line_height_text[:40]}'" if pg.line_height_text else ""))
            if pg.min_word_gap is not None and pg.min_word_gap < word_min:
                issues.append(
                    f"word spacing {pg.min_word_gap:.2f}em < {word_min}em"
                    + (f" at '{pg.word_gap_text[:40]}'" if pg.word_gap_text else ""))
            if pg.min_letter_gap is not None and pg.min_letter_gap < letter_min:
                issues.append(
                    f"letter spacing {pg.min_letter_gap:.2f}em < {letter_min}em"
                    + (f" at '{pg.letter_gap_text[:40]}'" if pg.letter_gap_text else ""))
            if issues:
                out.append(Finding(
                    self.rule_id, self.sc, self.severity,
                    f"page[{pg.page_no}]",
                    f"Text on page {pg.page_no + 1} is rendered with cramped "
                    f"spacing: {'; '.join(issues)}. Users cannot rely on the "
                    "document's own spacing being readable (WCAG 1.4.12).",
                    "; ".join(issues),
                    False,
                    "Increase line height / word / letter spacing in the source "
                    "layout, or ensure the content survives the user applying "
                    "WCAG 1.4.12 overrides (manual layout decision)."))
        return out

    def fix(self, dm, finding, ctx):
        return False


class MediaNoAlt:
    """SC 1.2.1: time-based media (video/audio) must have alternatives.

    Detects the deterministic carriers of embedded media in a PDF — form
    XObjects, /Screen annotations, and catalog /EmbeddedFiles — and flags
    each one that has no ``/Alt`` alternative text. The alternative itself
    (caption / transcript) is human content, so the default finding is
    manual (fixable=False). With ``--media-placeholder`` (AuditContext
    ``media_placeholder=True``) the finding becomes fixable and the fix
    writes a tracked ``[MEDIA-ALT-REQUIRED: ...]`` placeholder /Alt so the
    gap stays machine-visible — the same tracking pattern the image alt
    rule uses. No auto-captioning (roadmap non-goal).

    Serious/blocking: a screen-reader user gets no alternative at all for
    the media, so it blocks a PDF/UA pass — consistent with the
    image-alt-missing treatment of 1.1.1 non-text content.
    """

    rule_id = "media-no-alt"
    sc = "1.2.1"
    severity = "serious"

    KIND_LABEL = {
        "form-xobject": "form XObject",
        "screen-annot": "screen annotation",
        "embedded-file": "embedded file",
    }

    def check(self, dm, ctx):
        out = []
        for kind, loc, obj in dm.media_items():
            alt = key(obj, "Alt")
            if alt is not None and str(alt).strip():
                continue
            label = self.KIND_LABEL.get(kind, kind)
            fixable = bool(getattr(ctx, "media_placeholder", False))
            out.append(Finding(self.rule_id, self.sc, self.severity, loc,
                               f"Time-based media ({label}) has no /Alt "
                               "alternative (caption or transcript); "
                               "assistive technology users cannot access "
                               "its content.",
                               f"kind={kind}", fixable,
                               "Provide a caption file or transcript "
                               "(manual content). With --media-placeholder a "
                               "tracked [MEDIA-ALT-REQUIRED: ...] marker is "
                               "inserted so the gap stays visible."))
        return out

    def fix(self, dm, finding, ctx):
        if not getattr(ctx, "media_placeholder", False):
            return False
        m = re.match(r"^page\[(\d+)\]\s+(\S.*)$", finding.location)
        if m:
            pi = int(m.group(1))
            rest = m.group(2)
            kind = "screen-annot" if rest.startswith("screen annotation") \
                else "form-xobject"
            for k, loc, obj in dm.media_items():
                if k == kind and loc == finding.location:
                    obj["/Alt"] = (f"[MEDIA-ALT-REQUIRED: {kind} "
                                   f"{rest} on page {pi + 1} - insert a "
                                   "human-written caption/transcript]")
                    return True
            return False
        if finding.location.startswith("embedded file"):
            for k, loc, obj in dm.media_items():
                if k == "embedded-file" and loc == finding.location:
                    obj["/Alt"] = (f"[MEDIA-ALT-REQUIRED: embedded file "
                                   f"{loc} - insert a human-written "
                                   "caption/transcript]")
                    return True
            return False
        return False


RULES = [
    LanguageMissing(),
    TitleMissing(),
    DisplayDocTitle(),
    UnmarkedPdf(),
    MissingTagTree(),
    WeakTagTree(),
    ImageAltMissing(),
    DecorativeImageUndeclared(),
    MediaNoAlt(),
    OutlineMissing(),
    BadLinkText(),
    EncryptedPdf(),
    ColorContrast(),
    ReadingOrder(),
    TextSpacing(),
]

RULES_BY_ID = {r.rule_id: r for r in RULES}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _pick_title(dm, ctx) -> Optional[str]:
    """Deterministic title candidates, in priority order."""
    # 1. first H1 structural element
    st = dm.struct_tree()
    if st is not None:
        for lvl, text in dm.heading_levels(st):
            if lvl == 1 and text.strip():
                return text.strip()
    # 2. first outline entry
    if dm.outlines:
        return dm.outlines[0].title.strip()
    # 3. filename stem
    stem = Path(dm.path).name
    for suffix in (".pdf",):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem.replace("-", " ").replace("_", " ").strip() or None


def _scaffold_fix(dm, ctx):
    """Opt-in deterministic tag-tree scaffold (Phase 5). Builds a tree from
    the source file's content stream + fitz text; returns False when nothing
    could be structured (e.g. a page with no decodable text units)."""
    from .scaffold import build_plan
    try:
        plan = build_plan(dm.path)
        n = dm.build_scaffold(plan.blocks_by_page())
    except Exception:
        return False
    return n > 0


def _has_fix(r) -> bool:
    """A rule's fix() can return True for some findings."""
    import inspect
    src = inspect.getsource(r.fix)
    return "return True" in src or "return dm.set" in src or "return ok" in src