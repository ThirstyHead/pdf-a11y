"""Tests for in-app Markdown and rich report viewer dialog."""
import os
from pathlib import Path
import pytest

pyside6 = pytest.importorskip("PySide6")
from PySide6.QtCore import Qt

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pdf_a11y.gui.report_viewer import ReportViewerDialog


def test_report_viewer_init_with_markdown_file(tmp_path: Path, qtbot):
    report_file = tmp_path / "test-report.md"
    report_file.write_text(
        "# Accessibility Audit Report\n\n"
        "**Overall Score:** 92.5%\n\n"
        "## Summary\n- Passed: 12\n- Failed: 1\n",
        encoding="utf-8",
    )
    dialog = ReportViewerDialog(report_path=report_file)
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Accessibility Report" in dialog.windowTitle()
    assert dialog.browser is not None
    assert "92.5%" in dialog.browser.toPlainText()
    assert dialog.btn_open_external is not None
    assert dialog.btn_open_folder is not None


def test_report_viewer_score_badge_calculation(tmp_path: Path, qtbot):
    report_file = tmp_path / "summary.md"
    report_file.write_text("# Report\nScore: 85%\n", encoding="utf-8")
    dialog = ReportViewerDialog(report_path=report_file, score=85.0)
    qtbot.addWidget(dialog)

    assert dialog.lbl_score_badge.text() == "85.0% - MODERATE"
    assert dialog.lbl_score_badge.property("severity") == "moderate"
