"""Main dashboard window for pdf-a11y desktop application."""
from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from pdf_a11y.audit import audit_file
from pdf_a11y.gui.models import BatchItem, BatchQueue
from pdf_a11y.gui.theme import APP_STYLESHEET
from pdf_a11y.gui.triage_dialog import TriageDialog
from pdf_a11y.gui.worker import BatchWorker
from pdf_a11y.reports.theme import available_themes


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pdf-a11y: PDF WCAG & PDF/UA Accessibility Remediation")
        self.resize(1020, 720)
        self.setStyleSheet(APP_STYLESHEET)
        self.setAcceptDrops(True)

        self.queue = BatchQueue()
        self.worker: Optional[BatchWorker] = None

        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 1. Top Action Toolbar
        toolbar_layout = QHBoxLayout()
        self.btn_add_folder = QPushButton("📁 Add Folder...")
        self.btn_add_folder.clicked.connect(self.select_folder)

        self.btn_add_files = QPushButton("📄 Add Files...")
        self.btn_add_files.clicked.connect(self.select_files)

        self.btn_clear = QPushButton("🗑️ Clear List")
        self.btn_clear.clicked.connect(self.clear_files)

        self.btn_triage = QPushButton("🔍 Interactive Triage")
        self.btn_triage.clicked.connect(self.open_triage)

        toolbar_layout.addWidget(self.btn_add_folder)
        toolbar_layout.addWidget(self.btn_add_files)
        toolbar_layout.addWidget(self.btn_clear)
        toolbar_layout.addWidget(self.btn_triage)
        toolbar_layout.addStretch()

        main_layout.addLayout(toolbar_layout)

        # 2. Main content splitter: Queue Table & Detail/Preview
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["File Name", "Pages", "Status", "Findings", "Score"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        splitter.addWidget(self.table)

        # Preview area
        self.preview_browser = QTextBrowser()
        self.preview_browser.setPlaceholderText("Select a file row to preview its findings or accessibility report...")
        splitter.addWidget(self.preview_browser)
        splitter.setSizes([380, 180])

        main_layout.addWidget(splitter, stretch=1)

        # 3. Settings Box
        settings_group = QGroupBox("Configuration & Output Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(10)

        # Output directory selector
        out_dir_layout = QHBoxLayout()
        out_dir_layout.addWidget(QLabel("Output Directory:"))
        docs_dir = Path.home() / "Documents"
        default_out = (docs_dir if docs_dir.is_dir() else Path.home()) / "pdf-a11y-output"
        self.txt_out_dir = QLineEdit(str(default_out))
        self.btn_browse_out = QPushButton("Browse...")
        self.btn_browse_out.clicked.connect(self.browse_output_dir)
        out_dir_layout.addWidget(self.txt_out_dir, stretch=1)
        out_dir_layout.addWidget(self.btn_browse_out)
        settings_layout.addLayout(out_dir_layout)

        # Format & Theme options
        opts_layout = QHBoxLayout()
        opts_layout.addWidget(QLabel("Report Formats:"))
        self.chk_md = QCheckBox("Markdown (.md)")
        self.chk_md.setChecked(True)
        self.chk_html = QCheckBox("HTML (.html)")
        self.chk_pdf = QCheckBox("Tagged PDF (.pdf)")
        self.chk_json = QCheckBox("JSON (.json)")
        opts_layout.addWidget(self.chk_md)
        opts_layout.addWidget(self.chk_html)
        opts_layout.addWidget(self.chk_pdf)
        opts_layout.addWidget(self.chk_json)

        opts_layout.addSpacing(20)
        opts_layout.addWidget(QLabel("Theme:"))
        self.cbo_theme = QComboBox()
        self.cbo_theme.addItems(available_themes())
        if "light" in available_themes():
            self.cbo_theme.setCurrentText("light")
        opts_layout.addWidget(self.cbo_theme)

        opts_layout.addStretch()
        settings_layout.addLayout(opts_layout)

        # Auto-remediate checkbox
        self.chk_autofix = QCheckBox("Automatically apply deterministic remediations (source remains strictly unmodified)")
        self.chk_autofix.setChecked(True)
        settings_layout.addWidget(self.chk_autofix)

        main_layout.addWidget(settings_group)

        # 4. Bottom Controls: Progress & Run Button
        bottom_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.lbl_status = QLabel("Ready. Drag and drop PDF files or select a folder to begin.")

        self.btn_start = QPushButton("🚀 Run Batch Audit & Remediate")
        self.btn_start.setObjectName("btn_primary")
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self.toggle_batch)

        bottom_layout.addWidget(self.lbl_status, stretch=1)
        bottom_layout.addWidget(self.progress_bar, stretch=1)
        bottom_layout.addWidget(self.btn_start)

        main_layout.addLayout(bottom_layout)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        added_count = 0
        for url in urls:
            path = Path(url.toLocalFile())
            if path.is_dir():
                added_count += self.queue.add_directory(path)
            elif path.is_file() and path.suffix.lower() == ".pdf":
                if self.queue.add_file(path):
                    added_count += 1
        if added_count > 0:
            self._update_table()
            self.lbl_status.setText(f"Added {added_count} PDF document(s). Ready to audit.")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing PDF Documents")
        if folder:
            added = self.queue.add_directory(folder)
            self._update_table()
            self.lbl_status.setText(f"Added {added} PDF document(s) from {Path(folder).name}.")

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF Documents", "", "PDF Documents (*.pdf)")
        if files:
            added = 0
            for f in files:
                if self.queue.add_file(f):
                    added += 1
            self._update_table()
            self.lbl_status.setText(f"Added {added} PDF document(s).")

    def clear_files(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Audit in Progress", "Please stop the active audit before clearing.")
            return
        self.queue.clear()
        self._update_table()
        self.lbl_status.setText("Queue cleared.")
        self.preview_browser.clear()

    def browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.txt_out_dir.text())
        if folder:
            self.txt_out_dir.setText(folder)

    def _update_table(self):
        self.table.setRowCount(len(self.queue.items))
        for row, item in enumerate(self.queue.items):
            self.table.setItem(row, 0, QTableWidgetItem(item.path.name))
            pages_str = str(item.page_count) if item.page_count > 0 else "-"
            self.table.setItem(row, 1, QTableWidgetItem(pages_str))
            self.table.setItem(row, 2, QTableWidgetItem(item.status))
            findings_str = str(item.findings_count) if item.status == "Completed" else "-"
            self.table.setItem(row, 3, QTableWidgetItem(findings_str))
            score_str = f"{item.score:.1f}%" if item.score is not None else "-"
            self.table.setItem(row, 4, QTableWidgetItem(score_str))

    def on_table_selection_changed(self):
        selected = self.table.selectedIndexes()
        if not selected:
            return
        row = selected[0].row()
        if 0 <= row < len(self.queue.items):
            item = self.queue.items[row]
            if "md" in item.reports and item.reports["md"].exists():
                self.preview_browser.setMarkdown(item.reports["md"].read_text())
            elif item.error_message:
                self.preview_browser.setPlainText(f"Error:\n{item.error_message}")
            else:
                self.preview_browser.setPlainText(f"File: {item.path}\nStatus: {item.status}\nFindings: {item.findings_count}")

    def open_triage(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Document", "Please select a PDF in the table to triage.")
            return

        row = selected_rows[0].row()
        item = self.queue.items[row]

        try:
            audit_res = audit_file(str(item.path))
            findings = audit_res.get("findings", [])
            dialog = TriageDialog(item.path, findings, parent=self)
            dialog.exec()
            # Refresh audit status
            self.lbl_status.setText(f"Triage complete for {item.path.name}.")
        except Exception as exc:
            QMessageBox.critical(self, "Triage Error", f"Failed to inspect PDF: {exc}")

    def toggle_batch(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.btn_start.setText("Stopping...")
            self.btn_start.setEnabled(False)
            return

        if len(self.queue.items) == 0:
            QMessageBox.information(self, "Empty Queue", "Please add at least one PDF to audit.")
            return

        formats = []
        if self.chk_md.isChecked():
            formats.append("md")
        if self.chk_html.isChecked():
            formats.append("html")
        if self.chk_pdf.isChecked():
            formats.append("pdf")
        if self.chk_json.isChecked():
            formats.append("json")

        theme = self.cbo_theme.currentText()
        auto_fix = self.chk_autofix.isChecked()
        out_dir = Path(self.txt_out_dir.text()).resolve()

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self.queue.items))
        self.progress_bar.setValue(0)
        self.btn_start.setText("⏹️ Stop Batch")

        self.worker = BatchWorker(
            items=self.queue.items,
            out_dir=out_dir,
            formats=formats,
            theme=theme,
            auto_fix=auto_fix,
        )
        self.worker.item_started.connect(self._on_item_started)
        self.worker.item_progress.connect(self._on_item_progress)
        self.worker.item_finished.connect(self._on_item_finished)
        self.worker.all_completed.connect(self._on_all_completed)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_item_started(self, idx: int, total: int, name: str):
        self.lbl_status.setText(f"Processing ({idx + 1}/{total}): {name}...")
        self._update_table()

    def _on_item_progress(self, idx: int, step: str):
        self.lbl_status.setText(step)

    def _on_item_finished(self, idx: int, status: str, findings: int, score: float):
        self.progress_bar.setValue(idx + 1)
        self._update_table()

    def _on_all_completed(self, processed: int, errors: int):
        self.progress_bar.setVisible(False)
        self.btn_start.setText("🚀 Run Batch Audit & Remediate")
        self.btn_start.setEnabled(True)
        self.lbl_status.setText(f"Batch completed: {processed} processed, {errors} error(s).")
        self._update_table()
        QMessageBox.information(
            self,
            "Batch Complete",
            f"Processing finished!\nSuccessfully processed: {processed}\nErrors: {errors}\nOutput: {self.txt_out_dir.text()}",
        )

    def _on_error(self, idx: int, msg: str):
        self.lbl_status.setText(f"Error on item {idx + 1}: {msg}")
