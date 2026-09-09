"""HTML report engine (v0.5.0, subplan 1b).

Delegates to engine_a11y.reports.html.
"""
from pathlib import Path
from typing import Optional, Union
from engine_a11y.reports.html import render_html as _engine_render_html


def render_html(
    md_text: str,
    theme: str = "light",
    lang: str = "en",
    config_dir: Optional[Union[str, Path]] = None,
) -> str:
    html = _engine_render_html(
        md_text=md_text,
        theme=theme,
        lang=lang,
        config_dir=str(config_dir) if config_dir else None,
    )
    return html.replace("/* docx-a11y theme:", "/* pdf-a11y theme:")


__all__ = ["render_html"]
