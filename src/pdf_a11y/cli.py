"""pdf-a11y CLI.

Usage:
  pdf-a11y audit FILE [--json out.json] [--report out.md] [--format md|json]
             [--language en-US] [--background FFFFFF]
             [--alt-map '0:Image28=...'] [--outline-map '1=Title:0,2=Sub:1']
             [--enrich]
  pdf-a11y audit --batch DIR [same flags except --report/--format]
  pdf-a11y remediate FILE --findings audit.json --out FILE.fixed.pdf [same fix flags]
  pdf-a11y fix FILE [--out FILE.fixed.pdf] [--json out.json] [--report out.md]
             [--format md|json] [same flags]
  pdf-a11y fix --batch DIR [--json out.json] [same flags except --out/--report]
  pdf-a11y rules

Batch mode: non-recursive *.pdf in the directory; skips lock files (~$*) and
our own *.fixed.pdf outputs. The same --language/--background/--alt-map/
--outline-map apply to every file (maps are per-file coordinates, so a shared
map is best-effort).

Exit codes (audit): 0 = pass (no blocking findings), 1 = fail, 2 = usage/IO error.
Exit codes (fix):    0 = PASS after fix, 1 = FAIL (blocking findings remain),
                     2 = error (unreadable/corrupt file). Batch mode: 2 if any
                     file errored, else 1 if any failed, else 0.
"""
import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .audit import audit_file, audit_result_to_json
from .enrich import build_enrichment
from .remediate import _batch_pdf_files, fix_batch, fix_one, remediate
from .report import write_report  # noqa: F401  (compat re-export)
from .reports import compute_stats, render_md, render_html, report_json, theme_css
from .reports.pdf import render_pdf
from .reports.theme import available_themes
from .rules import RULES, AuditContext
from .remediate import remediate_file
from .triage import run_interactive_triage


def _parse_alt_map(s):
    """'0:Image28=Loaf of bread,1:Im1=Pot' -> {(0, 'Image28'): '...', (1, 'Im1'): '...'}"""
    out = {}
    if not s:
        return out
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        coords, _, text = part.partition("=")
        page_s, _, name = coords.partition(":")
        out[(int(page_s.strip()), name.strip())] = text.strip()
    return out


def _parse_outline_map(s):
    """'1=Title:0,2=Sub:1' -> [(1, 'Title', 0), (2, 'Sub', 1)]"""
    out = []
    if not s:
        return out
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        level_s, _, rest = part.partition("=")
        title, _, page_s = rest.rpartition(":")
        try:
            out.append((int(level_s.strip()), title.strip(), int(page_s.strip())))
        except ValueError:
            raise SystemExit(f"error: bad --outline-map entry {part!r} "
                             f"(want 'level=title:page')")
    return out


def _report_plan(args):
    """[(fmt, out_path)] from --format (multi-valued) + --report (md alias).

    md -> <stem>-a11y-report.md, unless --report PATH gives the explicit path
    (in which case --report also enables the md format). json ->
    <stem>-a11y-report.json. Output defaults land in the CWD, never next to
    the source.
    """
    raw_fmts = list(getattr(args, "formats", None) or [])
    report = getattr(args, "report", None)
    if report:
        raw_fmts.append("md")
    fmts = []
    for f in raw_fmts:
        for part in f.split(","):
            part = part.strip().lower()
            if part:
                fmts.append(part)
    seen, plan = set(), []
    stem = Path(getattr(args, "file", "") or "report").stem or "report"
    for f in fmts:
        if f in seen:
            continue
        seen.add(f)
        if f == "md":
            plan.append((f, report or f"{stem}-a11y-report.md"))
        elif f == "json":
            plan.append((f, f"{stem}-a11y-report.json"))
        elif f == "html":
            plan.append((f, f"{stem}.html"))
        elif f == "pdf":
            plan.append((f, f"{stem}.report.pdf"))
    return plan


def _write_reports(args, result, remediation=None, stats=None, live_enrich=None):
    """Render + write each (fmt, out) in the plan; returns the plan written."""
    written = []
    enrichment = source = None
    plan = _report_plan(args)
    theme = getattr(args, "theme", None) or "light"
    if any(f == "html" for f, _ in plan):
        try:
            theme_css(theme)  # validates the theme name (error lists themes)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(2)
    for fmt, out in plan:
        if fmt == "md":
            if enrichment is None and live_enrich is not None:
                enrichment, source = build_enrichment(result, live=live_enrich)
            text = render_md(result, remediation=remediation,
                             source_path=getattr(args, "file", None),
                             enrichment=enrichment,
                             enrichment_source=source, stats=stats)
            Path(out).write_text(text)
            written.append((fmt, out, source))
        elif fmt == "json":
            Path(out).write_text(report_json(result, remediation=remediation,
                                             stats=stats) + "\n")
            written.append((fmt, out, None))
        elif fmt == "html":
            if enrichment is None and live_enrich is not None:
                enrichment, source = build_enrichment(result, live=live_enrich)
            md_text = render_md(result, remediation=remediation,
                                source_path=getattr(args, "file", None),
                                enrichment=enrichment,
                                enrichment_source=source, stats=stats)
            doc = render_html(md_text, theme=theme,
                              lang=result.get("language") or "en")
            Path(out).write_text(doc)
            written.append((fmt, out, source))
        elif fmt == "pdf":
            if enrichment is None and live_enrich is not None:
                enrichment, source = build_enrichment(result, live=live_enrich)
            md_text = render_md(result, remediation=remediation,
                                source_path=getattr(args, "file", None),
                                enrichment=enrichment,
                                enrichment_source=source, stats=stats)
            doc = render_html(md_text, theme=theme,
                              lang=result.get("language") or "en")
            from .reports.pdf import render_pdf
            render_pdf(doc, theme=theme, out_path=out, lang=result.get("language") or "en")
            written.append((fmt, out, source))
    for fmt, out, source in written:
        if fmt == "md":
            print(f"report written: {out} (normative text: {source})")
        elif fmt == "html":
            print(f"report written: {out} (html, theme: {theme})")
        elif fmt == "pdf":
            print(f"report written: {out} (pdf, theme: {theme})")
        else:
            print(f"report written: {out} (json)")
    return written


def _ctx(args, source_name, scaffold: bool) -> AuditContext:
    # repair is a *write* capability: audit stays read-only, so the flag is a
    # no-op there (mirrors how the scaffold default differs per command).
    repair = getattr(args, "repair", False) and args.cmd != "audit"
    return AuditContext(
        source_name=source_name,
        default_language=args.language,
        background_rgb=args.background,
        alt_map=_parse_alt_map(getattr(args, "alt_map", None)),
        outline_map=_parse_outline_map(getattr(args, "outline_map", None)),
        scaffold=scaffold,
        media_placeholder=getattr(args, "media_placeholder", False),
        ocr=getattr(args, "ocr", False),
        repair=repair,
    )


def _add_fix_flags(p, scaffold_default=True):
    p.add_argument("--language", default="en-US", help="default language code (default en-US)")
    p.add_argument("--background", default="FFFFFF", help="assumed background RGB for contrast math")
    p.add_argument("--alt-map", help="deterministic alt text: 'page:ImageName=text' comma-separated")
    p.add_argument("--outline-map", help="deterministic outline: 'level=title:page' comma-separated")
    p.add_argument("--media-placeholder", action="store_true",
                   help="make media-no-alt findings fixable by writing a tracked "
                        "[MEDIA-ALT-REQUIRED: ...] /Alt placeholder (the caption/"
                        "transcript itself stays manual; no auto-captioning)")
    p.add_argument("--ocr", action="store_true",
                   help="OCR text-less (scanned) pages before fixing "
                        "(requires the `ocr` extra + tesseract; degrades gracefully)")
    p.add_argument("--repair", action="store_true",
                   help="repair already-tagged-but-weak trees (orphaned /P, "
                        "ParentTree); implies --scaffold; fail-safe on "
                        "content-level weaknesses (leaves them as findings)")
    # 0.3.0: `--scaffold` / `--no-scaffold` pair.
    #   - fix / remediate: ON by default (scaffold on; --no-scaffold opts out).
    #   - audit: OFF by default (scaffold_default=False) so auditing an untagged
    #     doc reports the same fixable flags as pre-0.3.0 (read-only, unchanged).
    # `--scaffold` remains valid in all cases (back-compat).
    p.add_argument("--scaffold", action=argparse.BooleanOptionalAction,
                   default=scaffold_default,
                   help="deterministic tag-tree scaffolding for untagged documents "
                        "(on by default for fix/remediate; off by default for audit; "
                        "pass --no-scaffold to keep the manual behavior)")


def cmd_audit(args) -> int:
    if getattr(args, "batch", None):
        return _cmd_audit_batch(args)
    ctx = _ctx(args, args.file, scaffold=args.scaffold)
    try:
        result = audit_file(args.file, ctx)
    except FileNotFoundError as e:
        print(f"error: file not found: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if args.json:
        Path(args.json).write_text(audit_result_to_json(result) + "\n")
        print(f"findings written: {args.json}")
    _write_reports(args, result, live_enrich=getattr(args, "enrich", False))

    s = result["summary"]
    verdict = "PASS" if s["pass"] else "FAIL"
    print(f"audit {args.file}: {s['total']} findings "
          f"(critical={s['by_severity']['critical']}, serious={s['by_severity']['serious']}, "
          f"moderate={s['by_severity']['moderate']}) -> {verdict}")
    for f in result["findings"]:
        mark = "fixable" if f["fixable"] else "manual "
        print(f"  [{f['severity'].upper():8s}] SC {f['sc']:5s} {mark} @ {f['location']} :: {f['description']}")
    return 0 if s["pass"] else 1


def _cmd_audit_batch(args) -> int:
    """audit --batch DIR: audit every PDF in the dir (non-recursive),
    per-file verdict lines + aggregate; --json writes ONE aggregated file."""
    if getattr(args, "formats", None) or getattr(args, "report", None):
        print("warning: --report/--format are not supported in batch mode; "
              "use --json (one aggregated file)", file=sys.stderr)
    results = {}
    failed = 0
    try:
        files = _batch_pdf_files(Path(args.batch))
    except NotADirectoryError as e:
        print(f"error: not a directory: {e}", file=sys.stderr)
        return 2
    if not files:
        print(f"error: no .pdf files in {args.batch}", file=sys.stderr)
        return 2
    for p in files:
        pctx = _ctx(args, p.name, scaffold=False)
        try:
            result = audit_file(p, pctx)
        except Exception as e:
            failed += 1
            results[p.name] = {"error": f"{type(e).__name__}: {e}"}
            print(f"[ERROR] {p.name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        s = result["summary"]
        verdict = "PASS" if s["pass"] else "FAIL"
        if not s["pass"]:
            failed += 1
        results[p.name] = result
        print(f"[{verdict}] {p.name}: {s['total']} findings "
              f"(critical={s['by_severity']['critical']}, serious={s['by_severity']['serious']}, "
              f"moderate={s['by_severity']['moderate']})")
    if args.json:
        agg = {"directory": str(Path(args.batch)), "files": results}
        Path(args.json).write_text(json.dumps(agg, indent=2, sort_keys=True) + "\n")
        print(f"batch findings written: {args.json}")
    print(f"audit batch {args.batch}: {len(files)} file(s), {failed} failed")
    return 0 if failed == 0 else 1


def cmd_remediate(args) -> int:
    ctx = _ctx(args, args.file, scaffold=args.scaffold)
    try:
        rr = remediate(args.file, args.findings, args.out, ctx)
    except FileNotFoundError as e:
        print(f"error: file not found: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"remediated {args.file} -> {args.out}")
    print(f"  applied: {len(rr.applied)}, skipped(manual): {len(rr.skipped)}")
    for a in rr.applied:
        print(f"  [applied ] {a[0]} @ {a[1]}")
    for s in rr.skipped:
        reason = s[2] if len(s) > 2 else ""
        print(f"  [skipped] {s[0]} @ {s[1]}" + (f" — {reason}" if reason else ""))
    print("re-verify: pdf-a11y audit " + Path(args.out).name)
    return 0 if rr.ok else 1


def cmd_fix(args) -> int:
    if getattr(args, "batch", None):
        return _cmd_fix_batch(args)
    if not args.file:
        print("error: FILE required (or use --batch DIR)", file=sys.stderr)
        return 2
    src = args.file
    if getattr(args, "ocr", False):
        from .ocr import ocr_prepare
        src, _n, note = ocr_prepare(args.file)
        print(f"[ocr] {note}")
    if getattr(args, "repair", False):
        args.scaffold = True          # --repair implies --scaffold
    ctx = _ctx(args, src, scaffold=args.scaffold)
    out = args.out or str(Path(src).with_name(Path(src).name + ".fixed.pdf"))
    fr = fix_one(src, out, ctx)
    fr["ocr"] = bool(getattr(args, "ocr", False))
    if fr["status"] == "error":
        print(f"error: {fr['error']}", file=sys.stderr)
        return 2

    if args.json:
        Path(args.json).write_text(json.dumps(fr, indent=2, sort_keys=True) + "\n")
        print(f"fix result written: {args.json}")

    before = fr["findings_before"]
    after_total = fr["reaudit"]["summary"]["total"]
    if fr["remediation"]:
        m = fr["remediation"]
        print(f"fix {args.file} -> {fr['output_path']}")
        print(f"  applied: {len(m['applied'])}, skipped(manual): {len(m['skipped'])}")
        for s in m["skipped"]:
            reason = s[2] if len(s) > 2 else ""
            print(f"  [skipped] {s[0]} @ {s[1]}" + (f" — {reason}" if reason else ""))
    else:
        print(f"fix {args.file} -> {fr['output_path']} (clean: 0 findings, copied)")

    verdict = "PASS" if fr["status"] == "pass" else "FAIL (blocking findings remain)"
    print(f"  findings: {before} -> {after_total} => {verdict}")
    if fr["status"] != "pass":
        for f in fr["reaudit"]["findings"]:
            if f["severity"] in ("critical", "serious"):
                print(f"  [BLOCKING] {f['rule_id']} SC {f['sc']} @ {f['location']} :: {f['description']}")

    stats = None
    if fr["reaudit"] is not None:
        stats = compute_stats(
            fr["findings_before"],
            fr["reaudit"]["summary"]["total"],
            pass_before=fr.get("pass_before"),
            pass_after=fr["reaudit"]["summary"]["pass"])
    _write_reports(args, fr["reaudit"], remediation=fr["remediation"],
                   stats=stats, live_enrich=getattr(args, "enrich", False))
    return 0 if fr["status"] == "pass" else 1


def _cmd_fix_batch(args) -> int:
    """fix --batch DIR: fix every PDF in the dir (non-recursive),
    per-file before->after lines + aggregate; --json writes the full
    aggregate dict. Exit: 2 if any error, 1 if any fail, else 0."""
    if getattr(args, "report", None):
        print("warning: --report is not supported in batch mode; "
              "use --json (one aggregated file)", file=sys.stderr)
    ctx = _ctx(args, "", scaffold=args.scaffold)
    try:
        res = fix_batch(args.batch, ctx)
    except NotADirectoryError as e:
        print(f"error: not a directory: {e}", file=sys.stderr)
        return 2
    if not res["entries"]:
        print(f"error: no .pdf files in {args.batch}", file=sys.stderr)
        return 2
    s = res["summary"]
    for e in res["entries"]:
        mark = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}[e["status"]]
        after = e["reaudit"]["summary"]["total"] if e["reaudit"] else "?"
        extra = f" :: {e['error']}" if e["status"] == "error" else ""
        print(f"[{mark}] {e['file']}: {e['findings_before']} -> {after}{extra}")
    failed = s["fail"] + s["error"]
    print(f"fix batch {args.batch}: {s['total']} file(s) — "
          f"pass={s['pass']} fail={s['fail']} error={s['error']} "
          f"(findings {s['findings_before']} -> {s['findings_after']})")
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
        print(f"batch result written: {args.json}")
    print(f"{failed} file(s) failed")
    if s["error"]:
        return 2
    return 0 if s["fail"] == 0 else 1


def cmd_rules(_args) -> int:
    from .rules import _has_fix
    print(f"{'rule_id':28s} {'sc':6s} {'severity':9s} fixable-rules")
    for r in RULES:
        print(f"{r.rule_id:28s} {r.sc:6s} {r.severity:9s} {'yes' if _has_fix(r) else 'no '}")
    return 0


def process_single_file(input_path: Path, args: argparse.Namespace, out_dir: Path) -> bool:
    """Processes a single .pdf file: triage, audit, remediation, and reporting."""
    stem = input_path.stem
    target_path = input_path

    if getattr(args, "triage", False):
        triaged_pdf = Path(args.out_pdf) if getattr(args, "out_pdf", None) else out_dir / f"{stem}-triaged.pdf"
        run_interactive_triage(target_path, triaged_pdf)
        if triaged_pdf.exists():
            target_path = triaged_pdf
            stem = target_path.stem

    # 1. Initial audit
    audit_before = audit_file(str(target_path))
    audit_after = None
    rem_res = {}

    # 2. Remediate if requested
    if getattr(args, "fix", False):
        fixed_pdf = Path(args.out_pdf) if getattr(args, "out_pdf", None) else out_dir / f"{stem}-remediated.pdf"
        if fixed_pdf.resolve() == target_path.resolve():
            print("Error: --out-pdf cannot match input document. pdf-a11y strictly guarantees that original files remain untouched and immutable.", file=sys.stderr)
            sys.exit(2)

        rem_res = remediate_file(target_path, fixed_pdf)
        print(f"[Integrity Verified] Original file preserved unchanged (SHA-256: {rem_res.get('original_sha256')})")
        print(f"Remediation saved to: {fixed_pdf}")
        for fix in rem_res.get("remediations_applied", []):
            print(f" - {fix}")
        audit_after = audit_file(str(fixed_pdf))

    # 3. Render reports
    raw_formats = getattr(args, "formats", None) or getattr(args, "format", "md")
    formats = []
    if isinstance(raw_formats, list):
        for f in raw_formats:
            for part in str(f).split(","):
                part = part.strip().lower()
                if part:
                    formats.append(part)
    elif raw_formats:
        for part in str(raw_formats).split(","):
            part = part.strip().lower()
            if part:
                formats.append(part)

    theme = getattr(args, "theme", "light") or "light"

    md_text = render_md(
        audit_before,
        remediation=rem_res.get("remediation") if getattr(args, "fix", False) else None,
        source_path=str(input_path),
    )

    if "md" in formats:
        md_file = out_dir / f"{stem}-a11y-report.md"
        md_file.write_text(md_text, encoding="utf-8")
        print(f"Markdown report: {md_file}")

    if "json" in formats:
        json_file = out_dir / f"{stem}-audit.json"
        json_file.write_text(json.dumps(audit_before, indent=2), encoding="utf-8")
        print(f"JSON audit: {json_file}")

    if "html" in formats:
        html_doc = render_html(md_text, theme=theme, lang=audit_before.get("language") or "en")
        html_file = out_dir / f"{stem}-a11y-report.html"
        html_file.write_text(html_doc, encoding="utf-8")
        print(f"Accessible HTML report: {html_file}")

    if "pdf" in formats:
        html_doc = render_html(md_text, theme=theme, lang=audit_before.get("language") or "en")
        pdf_file = out_dir / f"{stem}-a11y-report.pdf"
        render_pdf(html_doc, theme=theme, out_path=pdf_file, lang=audit_before.get("language") or "en")
        print(f"Accessible PDF report: {pdf_file}")

    final_summary = (audit_after or audit_before).get("summary", {})
    return bool(final_summary.get("pass", False))


def _build_subcommand_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pdf-a11y",
                                description="Audit and remediate PDF files for WCAG 2.1 AA / PDF-UA.")
    p.add_argument("--version", action="version", version=f"pdf-a11y {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit a PDF for WCAG violations")
    a.add_argument("file", nargs="?", help="PDF to audit (omit when using --batch)")
    a.add_argument("--batch", help="audit every PDF in a directory (non-recursive)")
    a.add_argument("--json", help="write findings JSON")
    a.add_argument("--report",
                   help="write the markdown report to PATH "
                        "(alias for --format md with an explicit path)")
    a.add_argument("--format", dest="formats", action="append", default=None,
                   metavar="FMT",
                   help="report format to write, repeatable or comma-separated "
                        "(md, json, html, pdf). md defaults to <stem>-a11y-report.md; "
                        "json writes <stem>-a11y-report.json; html writes <stem>.html; "
                        "pdf writes <stem>.report.pdf")
    a.add_argument("--theme", default=None, metavar="THEME",
                   help="theme for --format html and pdf (default: light; see "
                        "--help for bundled: light, dark, high-contrast, "
                        "ocean, forest, print)")
    _add_fix_flags(a, scaffold_default=False)
    a.add_argument("--enrich", action="store_true",
                   help="fetch normative text live from a locally installed wcag-guidelines-mcp "
                        "(default: use the bundled offline cache)")
    a.set_defaults(func=cmd_audit)

    r = sub.add_parser("remediate", help="apply deterministic fixes from an audit JSON")
    r.add_argument("file")
    r.add_argument("--findings", required=True, help="audit JSON produced by `pdf-a11y audit --json`")
    r.add_argument("--out", required=True, help="output PDF (source is never modified)")
    _add_fix_flags(r)
    r.set_defaults(func=cmd_remediate)

    fx = sub.add_parser("fix", help="audit + remediate + verify in one step (source untouched)")
    fx.add_argument("file", nargs="?", help="PDF to fix (omit when using --batch)")
    fx.add_argument("--batch", help="process every PDF in a directory instead of one file (non-recursive)")
    fx.add_argument("--out", help="output PDF (default: <file>.fixed.pdf)")
    fx.add_argument("--json", help="write full fix result JSON (before/after/remediation)")
    fx.add_argument("--report",
                    help="write the markdown report (re-audit + remediation "
                         "section) to PATH (alias for --format md with an "
                         "explicit path)")
    fx.add_argument("--format", dest="formats", action="append", default=None,
                    metavar="FMT",
                    help="report format to write, repeatable or comma-separated "
                         "(md, json, html, pdf)")
    _add_fix_flags(fx)
    fx.add_argument("--enrich", action="store_true",
                    help="fetch normative text live from wcag-guidelines-mcp for --report")
    fx.set_defaults(func=cmd_fix)

    rl = sub.add_parser("rules", help="list audit rules")
    rl.set_defaults(func=cmd_rules)
    return p


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    subcommands = {"audit", "remediate", "fix", "scaffold", "rules", "enrich", "clean"}

    if argv and argv[0] in subcommands:
        p = _build_subcommand_parser()
        args = p.parse_args(argv)
        return args.func(args)

    root_parser = argparse.ArgumentParser(
        prog="pdf-a11y",
        description="Audit and remediate PDF documents against WCAG 2.1/2.2 AA and PDF/UA standards."
    )
    root_parser.add_argument("--version", action="version", version=f"pdf-a11y {__version__}")
    root_parser.add_argument("file", nargs="?", default=None, help="Path to .pdf file or directory")
    root_parser.add_argument("--gui", action="store_true", help="Launch graphical user interface")
    root_parser.add_argument("--format", default="md", help="Report formats (comma-separated): md, html, pdf, json (default: md)")
    root_parser.add_argument("--theme", default="light", help="Theme for HTML/PDF reports (light, dark, high-contrast, ocean, forest, print)")
    root_parser.add_argument("--output-dir", default=".", help="Directory to save generated reports (default: current directory)")
    root_parser.add_argument("--fix", action="store_true", help="Perform deterministic remediation (source remains immutable)")
    root_parser.add_argument("--triage", action="store_true", help="Launch interactive author-intent triage session")
    root_parser.add_argument("--out-pdf", default=None, help="Output path for remediated .pdf file")
    root_parser.add_argument("--batch", action="store_true", help="Process all .pdf files in specified directory")

    if not argv:
        root_parser.print_help(sys.stderr)
        return 2

    args = root_parser.parse_args(argv)

    if args.gui:
        try:
            from .gui.app import main as gui_main
            gui_main()
            return 0
        except (ImportError, ModuleNotFoundError) as e:
            print(f"Error: GUI dependencies not installed. Run 'pip install pdf-a11y[gui]'. ({e})", file=sys.stderr)
            return 2

    if not args.file:
        root_parser.print_help(sys.stderr)
        return 2

    input_path = Path(args.file)
    if not input_path.exists():
        print(f"Error: File or directory '{input_path}' not found.", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_dir() or args.batch:
        files = sorted(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path]
        files = [f for f in files if not f.name.startswith("._")]
        if not files:
            print(f"No .pdf files found in {input_path}", file=sys.stderr)
            return 2
        all_passed = True
        for f in files:
            print(f"\nProcessing: {f.name}...")
            passed = process_single_file(f, args, out_dir)
            if not passed:
                all_passed = False
        return 0 if all_passed else 1
    else:
        passed = process_single_file(input_path, args, out_dir)
        return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())