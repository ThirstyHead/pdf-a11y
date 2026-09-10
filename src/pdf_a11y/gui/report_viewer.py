"""In-app Markdown and rich accessibility report viewer."""
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


class ReportViewerDialog(QDialog):
    def __init__(
        self,
        report_path: Path,
        score: Optional[float] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.report_path = Path(report_path)
        self.score = score
        self.setWindowTitle(f"Accessibility Report - {self.report_path.name}")
        self.resize(850, 650)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header Bar
        header_layout = QHBoxLayout()
        title_label = QLabel(f"📄 {self.report_path.name}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title_label, stretch=1)

        # Score Badge
        self.lbl_score_badge = QLabel()
        self._update_score_badge()
        header_layout.addWidget(self.lbl_score_badge)
        layout.addLayout(header_layout)

        # Markdown Content Browser
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        if self.report_path.exists():
            content = self.report_path.read_text(encoding="utf-8")
            self.browser.setMarkdown(content)
        else:
            self.browser.setPlainText(f"Report file not found at: {self.report_path}")
        layout.addWidget(self.browser, stretch=1)

        # Bottom Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_open_external = QPushButton("🌐 Open in Default App")
        self.btn_open_external.clicked.connect(self.open_external)

        self.btn_open_folder = QPushButton("📂 Open Enclosing Folder")
        self.btn_open_folder.clicked.connect(self.open_folder)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_open_external)
        btn_layout.addWidget(self.btn_open_folder)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _update_score_badge(self):
        if self.score is None:
            self.lbl_score_badge.setText("Report")
            self.lbl_score_badge.setProperty("severity", "info")
            return

        if self.score >= 90.0:
            status = "GOOD"
            severity = "pass"
            color = "#10b981"
        elif self.score >= 70.0:
            status = "MODERATE"
            severity = "moderate"
            color = "#f59e0b"
        else:
            status = "NEEDS REMEDIATION"
            severity = "critical"
            color = "#ef4444"

        self.lbl_score_badge.setText(f"{self.score:.1f}% - {status}")
        self.lbl_score_badge.setProperty("severity", severity)
        self.lbl_score_badge.setStyleSheet(
            f"background-color: {color}; color: white; padding: 4px 10px; "
            "border-radius: 6px; font-weight: bold; font-size: 13px;"
        )

    def open_external(self):
        if self.report_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report_path)))

    def open_folder(self):
        folder = self.report_path.parent
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
