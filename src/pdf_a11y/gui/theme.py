"""Accessible Qt stylesheet and color tokens for pdf-a11y GUI."""

APP_STYLESHEET = """
QMainWindow {
    background-color: #f8fafc;
}

QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 6px;
    spacing: 8px;
}

QPushButton {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
    color: #0f172a;
}

QPushButton:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
}

QPushButton:disabled {
    background-color: #f8fafc;
    border-color: #e2e8f0;
    color: #94a3b8;
}

QPushButton#btn_primary {
    background-color: #0284c7;
    border: 1px solid #0369a1;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#btn_primary:hover {
    background-color: #0369a1;
}

QPushButton#btn_primary:disabled {
    background-color: #7dd3fc;
    border-color: #7dd3fc;
    color: #ffffff;
}

QTableWidget {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    gridline-color: #f1f5f9;
    selection-background-color: #f0f9ff;
    selection-color: #0369a1;
}

QHeaderView::section {
    background-color: #f8fafc;
    border: none;
    border-bottom: 1px solid #cbd5e1;
    padding: 6px 8px;
    font-weight: 600;
    color: #334155;
}

QProgressBar {
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    text-align: center;
    background-color: #f1f5f9;
    height: 16px;
}

QProgressBar::chunk {
    background-color: #0284c7;
    border-radius: 3px;
}

QGroupBox {
    font-weight: 600;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    background-color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    color: #1e293b;
}

QLineEdit, QComboBox {
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 5px 8px;
    background-color: #ffffff;
    color: #0f172a;
}

QLineEdit:focus, QComboBox:focus {
    border-color: #0284c7;
}
"""
