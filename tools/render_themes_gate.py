#!/usr/bin/env python3
"""Manual gate for 1b: render a real audit report in all 5 themes.

Usage: .venv/bin/python tools/render_themes_gate.py [fixture.pdf] [outdir]

Writes <outdir>/<stem>.<theme>.html for each bundled theme so the report
can be opened in Safari/Chrome and spot-checked (readability + W3C links).
"""
import sys
from pathlib import Path

from pdf_a11y.audit import audit_file
from pdf_a11y.reports import available_themes, render_html, render_md

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main():
    fixture = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURES / "violations.pdf"
    outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/1b-gate")
    outdir.mkdir(parents=True, exist_ok=True)
    result = audit_file(str(fixture))
    md = render_md(result, source_path=str(fixture))
    written = []
    for t in available_themes():
        doc = render_html(md, theme=t["name"], lang=result.get("language") or "en")
        out = outdir / f"{fixture.stem}.{t['name']}.html"
        out.write_text(doc, encoding="utf-8")
        written.append(str(out))
    print(f"rendered {len(written)} themed reports from {fixture.name}:")
    for w in written:
        print("  ", w)


if __name__ == "__main__":
    main()
