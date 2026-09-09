"""pdf-a11y CLI entry point."""
import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional, Set

from engine_a11y.criteria_config import (
    apply_criteria_config,
    generate_criteria_template,
    load_criteria_config,
)
from engine_a11y.findings import summarize

from . import __version__
from .audit import audit_file, audit_result_to_json
from .immutability import sha256_file
from .remediate import remediate_file
from .reports.html import render_html
from .reports.md import render_md
from .reports.pdf import render_pdf
from .reports.theme import available_themes
from .rules import AuditContext
from .triage import run_interactive_triage


def process_single_file(
    input_path: Path,
    args: argparse.Namespace,
    out_dir: Path,
    excluded_sc: Optional[Set[str]] = None,
) -> bool:
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
    if excluded_sc:
        apply_criteria_config(audit_before.get("findings", []), excluded_sc)
        audit_before["summary"] = summarize(audit_before.get("findings", []))

    audit_after = None
    rem_res = {}

    # 2. Remediate if requested
    if getattr(args, "fix", False):
        fixed_pdf = Path(args.out_pdf) if getattr(args, "out_pdf", None) else out_dir / f"{stem}-remediated.pdf"
        if fixed_pdf.resolve() == target_path.resolve():
            sys.exit(
                "Error: --out-pdf cannot match input document. pdf-a11y strictly guarantees "
                "that original files remain untouched and immutable."
            )

        ctx = AuditContext(
            source_name=target_path.name,
            media_placeholder=getattr(args, "media_placeholder", False),
            scaffold=getattr(args, "scaffold", True),
            repair=getattr(args, "repair", False),
        )
        rem_res = remediate_file(target_path, fixed_pdf, context=ctx)
        print(f"[Integrity Verified] Original file preserved unchanged (SHA-256: {rem_res.get('original_sha256')})")
        print(f"Remediation saved to: {fixed_pdf}")
        for fix in rem_res.get("remediations_applied", []):
            print(f" - {fix}")
        audit_after = audit_file(str(fixed_pdf))
        if excluded_sc:
            apply_criteria_config(audit_after.get("findings", []), excluded_sc)
            audit_after["summary"] = summarize(audit_after.get("findings", []))

    # 3. Render reports
    raw_formats = getattr(args, "format", "md") or "md"
    formats = [f.strip().lower() for f in raw_formats.split(",") if f.strip()]
    theme = getattr(args, "theme", "light") or "light"

    theme_names = [t["name"] if isinstance(t, dict) else str(t) for t in available_themes()]
    if theme not in theme_names:
        print(
            f"Error: unknown theme {theme!r}. Available themes: {theme_names}",
            file=sys.stderr,
        )
        sys.exit(2)

    md_text = render_md(
        audit_before,
        remediation=rem_res.get("remediation") if getattr(args, "fix", False) else None,
        source_path=str(input_path),
        excluded_sc=excluded_sc,
    )

    if "md" in formats:
        md_file = out_dir / f"{stem}-a11y-report.md"
        md_file.write_text(md_text, encoding="utf-8")
        print(f"Markdown report: {md_file}")

    if "json" in formats:
        json_file = out_dir / f"{stem}-audit.json"
        json_text = audit_result_to_json(audit_before)
        json_file.write_text(json_text, encoding="utf-8")
        (out_dir / f"{stem}-a11y-report.json").write_text(json_text, encoding="utf-8")
        print(f"JSON audit: {json_file}")

    if "html" in formats:
        html_doc = render_html(md_text, theme=theme, lang=audit_before.get("language") or "en")
        html_file = out_dir / f"{stem}-a11y-report.html"
        html_file.write_text(html_doc, encoding="utf-8")
        (out_dir / f"{stem}.html").write_text(html_doc, encoding="utf-8")
        print(f"Accessible HTML report: {html_file}")

    if "pdf" in formats:
        html_doc = render_html(md_text, theme=theme, lang=audit_before.get("language") or "en")
        pdf_file = out_dir / f"{stem}-a11y-report.pdf"
        render_pdf(
            html_doc,
            theme=theme,
            out_path=pdf_file,
            lang=audit_before.get("language") or "en",
        )
        (out_dir / f"{stem}.report.pdf").write_bytes(pdf_file.read_bytes())
        print(f"Accessible PDF report: {pdf_file}")

    final_summary = (audit_after or audit_before).get("summary", {})
    return bool(final_summary.get("pass", False))


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pdf-a11y",
        description="Audit and remediate PDF documents against WCAG 2.2 AA standards.",
    )
    parser.add_argument("--version", action="version", version=f"pdf-a11y {__version__}")
    parser.add_argument("file", nargs="?", default=None, help="Path to PDF .pdf file or folder")
    parser.add_argument("--gui", action="store_true", help="Launch graphical user interface")
    parser.add_argument(
        "--format",
        default="md",
        help="Report formats (comma-separated): md, html, pdf, json (default: md)",
    )
    parser.add_argument(
        "--theme",
        default="light",
        help=f"SMACSS theme for HTML/PDF reports: {[t['name'] for t in available_themes()]}",
    )
    parser.add_argument("--output-dir", default=".", help="Directory to save generated reports (default: current directory)")
    parser.add_argument("--fix", action="store_true", help="Perform deterministic remediation")
    parser.add_argument("--triage", action="store_true", help="Launch interactive human triage session")
    parser.add_argument("--out-pdf", dest="out_pdf", default=None, help="Output path for remediated .pdf file")
    parser.add_argument("--out", dest="out_pdf", help=argparse.SUPPRESS)
    parser.add_argument("--batch", action="store_true", help="Process all .pdf files in specified directory")
    parser.add_argument("--repair", action="store_true", help="Repair weak tag trees and ParentTree")
    parser.add_argument("--media-placeholder", action="store_true", help="Emit placeholder alt text for media elements")
    parser.add_argument(
        "--no-scaffold",
        dest="scaffold",
        action="store_false",
        default=True,
        help="Do not automatically scaffold tag tree",
    )
    parser.add_argument(
        "--scaffold",
        dest="scaffold",
        action="store_true",
        help="Scaffold tag tree (default)",
    )
    parser.add_argument(
        "--criteria",
        help="Path to criteria configuration checklist ([x]/[ ]) or YAML for what-if testing",
    )
    parser.add_argument(
        "--init-criteria",
        nargs="?",
        const="a11y-criteria.txt",
        help="Generate default criteria checklist file ([x]/[ ]) and exit",
    )

    args = parser.parse_args(argv)

    if args.gui:
        try:
            from .gui.app import main as gui_main
            gui_main()
            sys.exit(0)
        except (ImportError, ModuleNotFoundError) as e:
            print(f"Error: GUI dependencies not installed. Run 'pip install pdf-a11y[gui]'. ({e})", file=sys.stderr)
            sys.exit(2)

    if args.init_criteria:
        out_criteria = Path(args.init_criteria)
        generate_criteria_template(out_criteria)
        print(f"Generated criteria checklist at: {out_criteria}")
        sys.exit(0)

    if not args.file:
        parser.print_help(sys.stderr)
        sys.exit(2)

    input_path = Path(args.file)
    if not input_path.exists():
        print(f"Error: File or directory '{input_path}' not found.", file=sys.stderr)
        sys.exit(2)

    excluded_sc: Set[str] = set()
    if args.criteria:
        criteria_path = Path(args.criteria)
        if not criteria_path.exists():
            print(f"Error: Criteria config '{criteria_path}' not found.", file=sys.stderr)
            sys.exit(2)
        _, excluded_sc = load_criteria_config(criteria_path)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_dir() or args.batch:
        files = sorted(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path]
        files = [f for f in files if not f.name.startswith("._")]
        if not files:
            print(f"No .pdf files found in {input_path}", file=sys.stderr)
            sys.exit(2)
        all_passed = True
        for f in files:
            print(f"\nProcessing: {f.name}...")
            passed = process_single_file(f, args, out_dir, excluded_sc=excluded_sc)
            if not passed:
                all_passed = False
        sys.exit(0 if all_passed else 1)
    else:
        passed = process_single_file(input_path, args, out_dir, excluded_sc=excluded_sc)
        sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
