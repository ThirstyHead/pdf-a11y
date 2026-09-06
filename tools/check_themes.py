#!/usr/bin/env python3
"""WCAG 1.4.3 contrast gate for every bundled theme (dev check).

Checks --fg and every --sev-* against --bg (all must be >= 4.5:1 normal
text). Uses the same contrast math as the audit (pdf_a11y.contrast).
Exit 1 on any failure.
"""
import re
import sys
from pathlib import Path

from pdf_a11y.contrast import contrast_ratio
from pdf_a11y.reports.theme import BUNDLED_DIR, BUNDLED_THEMES

TOKEN_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
GATE = ("--fg", "--sev-critical", "--sev-serious", "--sev-moderate",
        "--sev-minor")
MIN = 4.5


def parse_hex(value):
    v = value.strip()
    if not (len(v) == 7 and v.startswith("#")):
        return None
    return (int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16))


def main():
    failures = []
    for name in BUNDLED_THEMES:
        css = (BUNDLED_DIR / name / "tokens.css").read_text()
        tokens = {k: v.strip() for k, v in TOKEN_RE.findall(css)}
        bg = parse_hex(tokens["--bg"])
        for key in GATE:
            fg = parse_hex(tokens[key])
            if fg is None or bg is None:
                failures.append(f"{name}: {key} or --bg is not #rrggbb")
                continue
            ratio = contrast_ratio(fg, bg)
            status = "ok " if ratio >= MIN else "FAIL"
            print(f"{name:14s} {status} {key:15s} {ratio:5.2f}:1")
            if ratio < MIN:
                failures.append(f"{name}: {key} {ratio:.2f}:1 < {MIN}")
    if failures:
        print("\nCONTRAST GATE FAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    print(f"\nall {len(BUNDLED_THEMES)} bundled themes pass the "
          f"{MIN}:1 contrast gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
