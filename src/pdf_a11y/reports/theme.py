"""Theme system (subplan 1b) — SMACSS, plain CSS, no build step.

Layer order (deterministic, documented in themes/README.md):
  tokens.css -> _layout/objects.css -> _layout/units.css -> overrides.css
Output starts with ``/* pdf-a11y theme: <name> */``.

User themes live in ``<config_dir>/themes/<name>/`` (same shape as bundled)
and win on name collision.
"""
import json
from pathlib import Path

BUNDLED_DIR = Path(__file__).parent / "themes"
BUNDLED_THEMES = ["light", "dark", "high-contrast", "ocean", "forest"]

_TOKENS = ("--bg", "--fg", "--muted", "--accent", "--link", "--code-bg",
           "--sev-critical", "--sev-serious", "--sev-moderate", "--sev-minor")


def _load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text())
    for key in ("name", "label", "mode"):
        if key not in data:
            raise ValueError(f"theme manifest {path} missing '{key}'")
    if data["mode"] not in ("light", "dark"):
        raise ValueError(f"theme manifest {path}: mode must be light|dark")
    data.setdefault("default", False)
    return data


def _user_theme_dirs(config_dir) -> list:
    if config_dir is None:
        return []
    base = Path(config_dir) / "themes"
    if not base.is_dir():
        return []
    return sorted(
        d for d in base.iterdir()
        if d.is_dir() and not d.name.startswith("_")
        and (d / "theme.json").exists())


def _bundled_theme_dirs() -> list:
    return sorted(
        BUNDLED_DIR / name for name in BUNDLED_THEMES
        if (BUNDLED_DIR / name / "theme.json").exists())


def available_themes(config_dir=None) -> list:
    """Manifests for all themes; user themes first (they win on collision)."""
    themes, seen = [], set()
    for d in (*_user_theme_dirs(config_dir), *_bundled_theme_dirs()):
        if d.name in seen:
            continue
        seen.add(d.name)
        themes.append(_load_manifest(d / "theme.json"))
    return themes


def _find_theme_dir(name: str, config_dir=None) -> Path:
    for d in (*_user_theme_dirs(config_dir), *_bundled_theme_dirs()):
        if d.name == name:
            return d
    raise KeyError(f"unknown theme: {name!r} "
                   f"(available: {', '.join(t['name'] for t in available_themes(config_dir))})")


def theme_css(name: str, config_dir=None) -> str:
    """Assembled stylesheet for one theme (deterministic layer order)."""
    d = _find_theme_dir(name, config_dir)
    parts = [f"/* pdf-a11y theme: {name} */\n"]
    parts.append((d / "tokens.css").read_text().rstrip() + "\n")
    for layer in ("objects.css", "units.css"):
        parts.append((BUNDLED_DIR / "_layout" / layer).read_text().rstrip() + "\n")
    overrides = d / "overrides.css"
    if overrides.exists():
        parts.append(overrides.read_text().rstrip() + "\n")
    return "\n".join(parts)
