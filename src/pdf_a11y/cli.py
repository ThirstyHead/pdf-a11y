"""pdf-a11y CLI.

Usage:
  pdf-a11y audit FILE [--json out.json] [--report out.md] [--language en-US]
             [--background FFFFFF] [--alt-map '0:Image28=...'] [--outline-map '1=Title:0,2=Sub:1']
             [--enrich]
  pdf-a11y audit --batch DIR [same flags except --report]
  pdf-a11y remediate FILE --findings audit.json --out FILE.fixed.pdf [same fix flags]
  pdf-a11y fix FILE [--out FILE.fixed.pdf] [--json out.json] [--report out.md] [same flags]
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
from .report import write_report
from .rules import RULES, AuditContext


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
    if args.report:
        enrichment, source = build_enrichment(result, live=getattr(args, "enrich", False))
        write_report(result, args.report, source_path=args.file,
                     enrichment=enrichment, enrichment_source=source)
        print(f"report written: {args.report} (normative text: {source})")

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

    if args.report:
        enrichment, source = build_enrichment(fr["reaudit"], live=getattr(args, "enrich", False))
        write_report(fr["reaudit"], args.report, remediation=fr["remediation"],
                     source_path=args.file, enrichment=enrichment,
                     enrichment_source=source)
        print(f"report written: {args.report} (normative text: {source})")
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pdf-a11y",
                                description="Audit and remediate PDF files for WCAG 2.1 AA / PDF-UA.")
    p.add_argument("--version", action="version", version=f"pdf-a11y {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit a PDF for WCAG violations")
    a.add_argument("file", nargs="?", help="PDF to audit (omit when using --batch)")
    a.add_argument("--batch", help="audit every PDF in a directory (non-recursive)")
    a.add_argument("--json", help="write findings JSON")
    a.add_argument("--report", help="write markdown report")
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
    fx.add_argument("--report", help="write markdown report (re-audit + remediation section)")
    _add_fix_flags(fx)
    fx.add_argument("--enrich", action="store_true",
                    help="fetch normative text live from wcag-guidelines-mcp for --report")
    fx.set_defaults(func=cmd_fix)

    rl = sub.add_parser("rules", help="list audit rules")
    rl.set_defaults(func=cmd_rules)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())