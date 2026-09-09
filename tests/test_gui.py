"""Tests for PySide6 desktop GUI interface."""
import os
from pathlib import Path
import pytest

pyside6 = pytest.importorskip("PySide6")
from PySide6.QtCore import Qt

# Force offscreen rendering for headless tests
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pdf_a11y.findings import Finding
from pdf_a11y.gui.main_window import MainWindow
from pdf_a11y.gui.models import BatchItem, BatchQueue
from pdf_a11y.gui.triage_dialog import TriageDialog
from pdf_a11y.gui.worker import AuditWorker, BatchWorker, RemediateWorker

FIXTURES = Path(__file__).parent / "fixtures"
CLEAN = FIXTURES / "clean.pdf"
VIOLATIONS = FIXTURES / "violations.pdf"


def test_main_window_init(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert "pdf-a11y" in window.windowTitle()
    assert window.table.columnCount() == 5
    assert window.acceptDrops() is True
    assert window.cbo_theme.count() >= 6


def test_batch_queue(tmp_path: Path):
    queue = BatchQueue()
    assert len(queue) == 0

    item = queue.add_file(CLEAN)
    assert item is not None
    assert len(queue) == 1
    assert item.path == CLEAN.resolve()

    # Reject duplicates
    dup = queue.add_file(CLEAN)
    assert dup is None
    assert len(queue) == 1

    # Non-pdf rejected
    txt = tmp_path / "note.txt"
    txt.write_text("hello")
    assert queue.add_file(txt) is None

    # Clear
    queue.clear()
    assert len(queue) == 0


def test_gui_workers_init():
    audit_w = AuditWorker(CLEAN)
    assert audit_w.file_path == CLEAN

    rem_w = RemediateWorker(CLEAN)
    assert rem_w.file_path == CLEAN


def test_triage_dialog_ui(tmp_path: Path, qtbot):
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(CLEAN.read_bytes())

    findings = [
        Finding(
            rule_id="title-missing",
            sc="2.4.2",
            severity="moderate",
            location="catalog",
            description="Document title missing",
            evidence="",
            fixable=True,
        ),
        Finding(
            rule_id="image-alt-missing",
            sc="1.1.1",
            severity="serious",
            location="page 1 img0",
            description="Image missing alt text",
            evidence="",
            fixable=True,
        ),
    ]

    dialog = TriageDialog(sample, findings)
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Barrier 1 of 2" in dialog.lbl_progress.text()
    dialog.txt_input.setText("Accessible Quartely Report")
    dialog.apply_current()

    assert "Barrier 2 of 2" in dialog.lbl_progress.text()
    assert not dialog.chk_decorative.isHidden()
    dialog.chk_decorative.setChecked(True)
    dialog.apply_current()

    assert dialog.items_modified == 2
