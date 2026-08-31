# pdf-a11y

Audit and remediate PDF files against **WCAG 2.1 AA** with a PDF/UA-1 target — standalone, deterministic, no AI in the loop.

`pdf-a11y` is a rule-based auditor over the PDF object structure that pikepdf exposes (catalog, page resources, marked content, structure tree). It reports every violation with a WCAG success-criterion mapping, then applies the fixes it can do deterministically and writes a new file (the source is never modified). Re-run the audit to verify a PASS.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e .          # or: pip install pdf-a11y

# 1. audit (exit 0 = pass, 1 = fail, 2 = usage/IO error)
pdf-a11y audit recipe.pdf --json findings.json --report report.md
#    reports can embed official WCAG normative text (see "Report enrichment")

# 2. remediate (needs the audit JSON; provide maps for deterministic structure)
pdf-a11y remediate recipe.pdf --findings findings.json \
    --out recipe_fixed.pdf --alt-map '0:Im1=Loaf of bread' --outline-map '1=Title:0'

# 3. re-verify
pdf-a11y audit recipe_fixed.pdf
```

Use the venv entry point on machines where the console script isn't on PATH:

```bash
.venv/bin/pdf-a11y audit recipe.pdf
```

### One-command fix (recommended)

```bash
pdf-a11y fix recipe.pdf --alt-map '0:Im1=Loaf of bread' --outline-map '1=Title:0'
# => recipe.pdf.fixed.pdf; exits 0 on PASS, 1 if blocking findings remain, 2 on error
# --json out.json  full before/after result   --report out.md  markdown report
```

### Batch mode

```bash
pdf-a11y fix --batch ./policy-pdfs       # fixes every .pdf in the dir (non-recursive)
pdf-a11y audit --batch ./policy-pdfs     # audit-only triage
# outputs: <file>.fixed.pdf per file; summary line: pass=N fail=N error=N
# exit: 0 all pass, 1 any fail, 2 any error (corrupt/missing)
```

Batch notes: `*.pdf` only, non-recursive, skips `~$*` lock files and `*.fixed.pdf` outputs; the same `--alt-map`/`--outline-map`/`--language`/`--background` apply to every file (maps are per-file coordinates, so a shared map is best-effort). `fix --batch --report` is not supported — use `--json` for the aggregated result.

### Audit options

| Flag | Default | Meaning |
|---|---|---|
| `--json OUT` | — | write machine-readable findings (stable key order, sorted findings) |
| `--report OUT` | — | write a markdown report |
| `--language CODE` | `en-US` | default language code used when fixing SC 3.1.1 |
| `--background RRGGBB` | `FFFFFF` | assumed page background for contrast math |
| `--alt-map 'page:ImageName=text'` | — | deterministic alt text: page number + image XObject name → `/Alt` value |
| `--outline-map 'level=title:page'` | — | deterministic outline: heading level + title → page number |
| `--scaffold` | off | build a deterministic tag tree for untagged documents (see "Scaffolding") |
| `--enrich` | off | fetch normative text live from a locally installed wcag-guidelines-mcp (default: bundled offline cache) |

`remediate` accepts the same `--language`, `--background`, `--alt-map`, `--outline-map`, `--scaffold` flags.

### Exit codes

**audit:** 0 = pass (no blocking findings), 1 = fail, 2 = usage/IO error.

**fix:**

| exit | meaning |
|---|---|
| `0` | PASS after fix (no blocking findings remain) |
| `1` | FAIL — blocking findings remain after fix (which ones are listed on stdout) |
| `2` | error — file unreadable/corrupt |

Batch mode (`fix --batch DIR`, `audit --batch DIR`): exit 2 if any file errored, else 1 if any failed, else 0.

## Scaffolding (opt-in `--scaffold`)

By default, an untagged document (no `/MarkInfo /Marked`, no structure tree) fails SC 1.3.1 and the fix leaves it manual — building a tag tree is a content-level decision. With `--scaffold`, `fix` instead builds a **deterministic tag tree** from the document's own content stream:

```bash
pdf-a11y fix recipe.pdf --scaffold
# bread sample: 5 findings FAIL -> 0 findings PASS
pdf-a11y audit recipe.pdf.fixed.pdf   # re-verify
```

How it works (all deterministic, no AI):

1. Each page's content stream is split into top-level `BT`/`ET` text units by a string-literal-aware scanner (escaped parens, hex strings, comments; the `q`/`Q`/`cm` graphics state is tracked so font sizes and positions are measured in device space).
2. Each unit is matched to a rendered span by PyMuPDF (same page, baseline ±2 pt, size ±0.25 pt, x-overlap) to recover its **Alt** text — this works even for subsetted, custom-encoded fonts, since the text comes from the renderer, not the raw stream bytes.
3. Roles are assigned from font-size tiers: body size = the median of all rendered sizes; a size ≥ 1.3× body (on a 0.5 pt grid) becomes H1…Hn in rank order (capped at 6); everything else is `P`. A unit that looks like a heading but has no matched text is **demoted to P** — no fake headings.
4. Each unit is wrapped in `/M<mcid> BDC … EMC` (1-based MCIDs in stream order), a `StructTreeRoot` with per-page `S=/Document` roots is written, headings carry `/Alt`, and `/MarkInfo /Marked` is set.

Downstream fixes then run unmodified: the document title comes from the first H1's Alt, the outline is derived from the headings, and the audit's `tag-tree-weak` check verifies the BDC/EMC↔tree association.

**Caveat:** a scaffolded document is a *deterministic best-effort* structure. Reading order follows the content stream, heading choices are font-size heuristics, and the audit's PASS only proves internal consistency — it does not certify PDF/UA compliance. Review the result in a tag editor before production PDF/UA certification.

## Rules

`pdf-a11y rules` lists the registry; the baseline set:

| rule_id | SC | severity | deterministic fix |
|---|---|---|---|
| `image-alt-missing` | 1.1.1 | critical | placeholder only — real alt text is human content (supply `--alt-map`) |
| `pdf-unmarked` | 1.3.1 | serious | yes — sets `/MarkInfo /Marked` |
| `tag-tree-missing` | 1.3.1 | serious | no — manual (a structure tree requires content-level decisions) |
| `tag-tree-weak` | 1.3.1 | serious | no — manual (repair the tree) |
| `language-missing` | 3.1.1 | moderate | yes — catalog `/Lang` (from `--language`) |
| `title-missing` | 2.4.2 (by convention) | moderate | yes — document title from first heading or filename stem |
| `outline-missing` | 2.4.1 | moderate | yes, when derivable (headings in the tag tree, or `--outline-map`) |
| `color-contrast` | 1.4.3 | moderate | no — advisory (needs human rendering context) |
| `pdf-encrypted` | 1.3.1 | moderate | no — manual (unlock the file) |
| `link-text-vague` | 2.4.4 | moderate | no — manual (link purpose is human content) |
| `display-doctitle-off` | 2.4.2 | minor | yes — `/ViewerPreferences /DisplayDocTitle` true |
| `decorative-undeclared` | 1.1.1 | minor | yes — marks known-decorative images |

Severity order: critical → serious (blocking) → moderate → minor. The audit **passes** when there are no critical/serious findings; moderate findings are advisory.

## Determinism & safety

- **Same input file + same version → identical findings JSON.** Findings are sorted by severity then location; JSON keys are sorted.
- **Remediation only mutates a copy.** The source `.pdf` is never touched; output goes to `--out` (default `<file>.fixed.pdf`).
- **Only deterministic fixes run automatically.** Anything requiring human judgment (real alt text, structure-tree repair, link purpose) is reported as `fixable: false` / skipped, never guessed.
- **A broken rule cannot kill the audit** — it is captured as an internal finding.

## Scope

- WCAG 2.1 AA with a PDF/UA-1 target. 2.x keyboard/interaction criteria are largely N/A for static PDFs; 2.4.1 (bypass blocks) and 2.4.4 (link purpose) are applied to the document outline and link annotations, which are the PDF equivalents. SC 2.4.2 (Page Titled) is applied by convention to document title metadata.
- 1.2.x media alternatives are advisory (no auto-captioning).
- 3.1.1 / 3.2.x / 3.3.x are out of scope for static document content.
- Contrast assumes a flat background (`--background`); page-level backgrounds/gradients are out of scope.

## Examples

`examples/` holds a real-world recipe document (`No Knead Bread-print.pdf`) used to reproduce an original manual audit run end-to-end; `examples/*.fixed.pdf` are regenerable outputs of `fix` (not committed).

## Changelog

### 0.2.0

- **Tag-tree scaffolding** (`scaffold.py`): opt-in `--scaffold` flag on `fix` builds a deterministic tag tree from an untagged document's own content stream — BT/ET text units, PyMuPDF-matched Alt text, font-size-tier H1–H6/P roles, BDC/EMC associations, `StructTreeRoot` + `/MarkInfo /Marked`. The bread sample goes 5 findings FAIL → 0 findings PASS.
- **Test suite**: characterization tests with programmatically built, committed PDF fixtures (`tests/make_fixtures.py`, `tests/fixtures/`); 30 tests.
- **CI**: GitHub Actions matrix (py 3.10–3.13) + CLI smoke test on every PR.
- **Rule fixes**: untagged documents report a single 1.3.1 finding (was two); `outline-missing` now reports an honest `fixable` flag (false when no headings and no `--outline-map`).

### 0.1.0

- Baseline: `audit`, `remediate`, `fix` (+`--batch`), `rules`; 12 rules; `--json`/`--report`/`--enrich` outputs; alt-map/outline-map knobs; exit codes 0/1/2.

## License

MIT