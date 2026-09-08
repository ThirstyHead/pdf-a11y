#!/usr/bin/env python3
"""Regenerate the bundled theme token files + theme.json (deterministic).

Provenance for src/pdf_a11y/reports/themes/{name}/{tokens.css,theme.json}.
Idempotent: running it reproduces the committed assets byte-for-byte. The
canonical values live here (single source) — edit them here, then run:

    .venv/bin/python tools/gen_themes.py
    .venv/bin/python tools/check_themes.py   # WCAG 1.4.3 gate
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src/pdf_a11y/reports/themes"

#: token order is the documented contract (all 10 per theme).
TOKEN_ORDER = ["--bg", "--fg", "--muted", "--accent", "--link", "--code-bg",
               "--sev-critical", "--sev-serious", "--sev-moderate", "--sev-minor"]

THEMES = {
    "light": {
        "label": "Light", "mode": "light", "default": True,
        "tokens": {
            "--bg": "#ffffff", "--fg": "#1a1a2e", "--muted": "#555555",
            "--accent": "#1a5fb4", "--link": "#0b5394", "--code-bg": "#f2f2f2",
            "--sev-critical": "#a3132f", "--sev-serious": "#9c3d00",
            "--sev-moderate": "#7a5a00", "--sev-minor": "#4a5568",
        },
    },
    "dark": {
        "label": "Dark", "mode": "dark", "default": False,
        "tokens": {
            "--bg": "#12121c", "--fg": "#e8e8f0", "--muted": "#a0a0b0",
            "--accent": "#6ea8fe", "--link": "#8ab4f8", "--code-bg": "#1e1e2e",
            "--sev-critical": "#ff8787", "--sev-serious": "#ffa657",
            "--sev-moderate": "#e6c35c", "--sev-minor": "#9fb4d0",
        },
    },
    "high-contrast": {
        "label": "High Contrast", "mode": "light", "default": False,
        "tokens": {
            "--bg": "#ffffff", "--fg": "#000000", "--muted": "#333333",
            "--accent": "#0000ee", "--link": "#0000cc", "--code-bg": "#f0f0f0",
            "--sev-critical": "#990000", "--sev-serious": "#8a4b00",
            "--sev-moderate": "#6b5b00", "--sev-minor": "#333333",
        },
    },
    "ocean": {
        "label": "Ocean", "mode": "light", "default": False,
        "tokens": {
            "--bg": "#eef5fa", "--fg": "#0b2530", "--muted": "#3f6478",
            "--accent": "#0a5c8a", "--link": "#084d6e", "--code-bg": "#dbe9f2",
            "--sev-critical": "#8f1c3a", "--sev-serious": "#8a4300",
            "--sev-moderate": "#5f5300", "--sev-minor": "#33495a",
        },
    },
    "forest": {
        "label": "Forest", "mode": "light", "default": False,
        "tokens": {
            "--bg": "#f1f7f1", "--fg": "#1c2e1c", "--muted": "#43604a",
            "--accent": "#2d6a2d", "--link": "#245724", "--code-bg": "#dcebe0",
            "--sev-critical": "#8c1f1f", "--sev-serious": "#7a4a00",
            "--sev-moderate": "#5a5200", "--sev-minor": "#37503f",
        },
    },
    "print": {
        "label": "Print (black & white)", "mode": "light", "default": False,
        "tokens": {
            "--bg": "#ffffff", "--fg": "#000000", "--muted": "#000000",
            "--accent": "#000000", "--link": "#000000", "--code-bg": "#ffffff",
            "--sev-critical": "#000000", "--sev-serious": "#000000",
            "--sev-moderate": "#000000", "--sev-minor": "#000000",
        },
    },
}


def render_tokens(tokens):
    lines = [":root {"]
    lines += [f"  {k}: {tokens[k]};" for k in TOKEN_ORDER]
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    changed = 0
    for name, t in THEMES.items():
        d = ROOT / name
        d.mkdir(parents=True, exist_ok=True)
        token_path = d / "tokens.css"
        new_tokens = render_tokens(t["tokens"])
        if token_path.exists() and token_path.read_text() == new_tokens:
            pass
        else:
            token_path.write_text(new_tokens, encoding="utf-8")
            changed += 1
        meta = {"name": name, "label": t["label"], "mode": t["mode"],
                "default": t["default"]}
        meta_path = d / "theme.json"
        new_meta = json.dumps(meta, indent=2) + "\n"
        if meta_path.exists() and meta_path.read_text() != new_meta:
            changed += 1
        meta_path.write_text(new_meta, encoding="utf-8")
    print(f"gen_themes: {len(THEMES)} themes under {ROOT} ({changed} files changed)")


if __name__ == "__main__":
    main()
