"""Accessible Qt stylesheet and color tokens for pdf-a11y GUI.

Delegates to engine_a11y.gui.theme and extends with storytelling layout styles.
"""
from engine_a11y.gui.theme import APP_STYLESHEET as BASE_STYLESHEET

STORY_STYLESHEET = """
/* Before & After Panels */
QGroupBox#pane_before, QGroupBox#pane_after {
    font-size: 13px;
    font-weight: bold;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    margin-top: 12px;
    background-color: #ffffff;
}

QGroupBox#pane_before::title, QGroupBox#pane_after::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    background-color: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    color: #1e293b;
}

#pane_subtitle {
    font-size: 11px;
    color: #64748b;
    font-weight: normal;
}

/* Center Bridge */
QFrame#center_bridge {
    background-color: #f8fafc;
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
}

#btn_remediate_primary {
    background-color: #2563eb;
    color: #ffffff;
    font-size: 14px;
    font-weight: bold;
    padding: 10px 16px;
    border-radius: 6px;
    border: none;
}
#btn_remediate_primary:hover {
    background-color: #1d4ed8;
}
#btn_remediate_primary:disabled {
    background-color: #94a3b8;
}

/* Guide Header */
#guide_banner {
    background-color: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
    color: #1e40af;
    font-weight: 500;
}
"""

APP_STYLESHEET = BASE_STYLESHEET + "\n" + STORY_STYLESHEET

__all__ = ["APP_STYLESHEET"]
