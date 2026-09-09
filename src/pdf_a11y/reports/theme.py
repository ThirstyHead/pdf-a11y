"""Theme system (subplan 1b) — SMACSS, plain CSS, no build step.

Delegates to engine_a11y.reports.theme.
"""
from typing import Any, Dict, List, Optional
from engine_a11y.reports.theme import (
    BUNDLED_THEMES,
    available_themes as _engine_available_themes,
    theme_css as _engine_theme_css,
)


def available_themes(config_dir: Optional[Any] = None) -> List[Dict[str, Any]]:
    return _engine_available_themes(config_dir=config_dir)


def theme_css(name: str, config_dir: Optional[Any] = None) -> str:
    css = _engine_theme_css(name=name, config_dir=config_dir)
    return css.replace("/* docx-a11y theme:", "/* pdf-a11y theme:")


__all__ = ["BUNDLED_THEMES", "available_themes", "theme_css"]
