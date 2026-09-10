"""Main dashboard window for pdf-a11y desktop application with Before/After storytelling."""
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pdf_a11y.audit import audit_file
from pdf_a11y.gui.models import BatchItem, BatchQueue
from pdf_a11y.gui.report_viewer import ReportViewerDialog
from pdf_a11y.gui.theme import APP_STYLESHEET
from pdf_a11y.gui.triage_dialog import TriageDialog
from pdf_a11y.gui.worker import BatchWorker
from pdf_a11y.reports.theme import available_themes


class MainWindow(QMainWindow):
    worker_completed_signal = Signal(int, int)  # (processed, errors)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("pdf-a11y: PDF WCAG & PDF/UA Accessibility Remediation")
        self.resize(1120, 740)
        self.setStyleSheet(APP_STYLESHEET)
        self.setAcceptDrops(True)

        self.queue = BatchQueue()
        self.worker: Optional[BatchWorker] = None

        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # 1. Top Story Guide Banner for non-technical users
        guide_banner = QLabel(
            "💡 <b>How it works:</b> "
            "<b>1.</b> Add original files on the left (<b>Before</b>)  ➔  "
            "<b>2.</b> Click <b>Fix & Audit</b> in the center  ➔  "
            "<b>3.</b> Open your remediated files and reports on the right (<b>After</b>). "
            "<i>Your original files are safe and never modified.</i>"
        )
        guide_banner.setObjectName("guide_banner")
        guide_banner.setWordWrap(True)
        main_layout.addWidget(guide_banner)

        # 2. Main Two-Pane Splitter with Center Bridge
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==========================================
        # Left Pane: "1. Before (Original Documents)"
        # ==========================================
        self.pane_before = QGroupBox("1. Before: Original Documents")
        self.pane_before.setObjectName("pane_before")
        before_layout = QVBoxLayout(self.pane_before)
        before_layout.setSpacing(8)

        lbl_before_sub = QLabel("Files queued for accessibility remediation. Source files remain untouched.")
        lbl_before_sub.setObjectName("pane_subtitle")
        lbl_before_sub.setWordWrap(True)
        before_layout.addWidget(lbl_before_sub)

        # Before Toolbar
        tb_before = QHBoxLayout()
        self.btn_add_files = QPushButton("📄 Add Files...")
        self.btn_add_files.clicked.connect(self.select_files)
        self.btn_add_folder = QPushButton("📁 Add Folder...")
        self.btn_add_folder.clicked.connect(self.select_folder)
        self.btn_clear = QPushButton("🗑️ Clear")
        self.btn_clear.clicked.connect(self.clear_files)
        self.btn_triage = QPushButton("🔍 Triage")
        self.btn_triage.clicked.connect(self.open_triage)

        tb_before.addWidget(self.btn_add_files)
        tb_before.addWidget(self.btn_add_folder)
        tb_before.addWidget(self.btn_clear)
        tb_before.addWidget(self.btn_triage)
        tb_before.addStretch()
        before_layout.addLayout(tb_before)

        # Before Queue Table
        self.table_before = QTableWidget(0, 5)
        self.table_before.setHorizontalHeaderLabels(["File Name", "Pages", "Status", "Findings", "Score"])
        header_before = self.table_before.horizontalHeader()
        header_before.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_before.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_before.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_before.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header_before.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_before.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_before.setAlternatingRowColors(True)
        before_layout.addWidget(self.table_before, stretch=1)

        # Backward compatibility alias
        self.table = self.table_before

        main_splitter.addWidget(self.pane_before)

        # ==========================================
        # Center Column: Remediation Action Bridge
        # ==========================================
        self.center_bridge = QFrame()
        self.center_bridge.setObjectName("center_bridge")
        self.center_bridge.setFixedWidth(190)
        center_layout = QVBoxLayout(self.center_bridge)
        center_layout.setSpacing(10)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        arrow_label = QLabel("➔")
        arrow_label.setStyleSheet("font-size: 28px; color: #3b82f6; font-weight: bold;")
        arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(arrow_label)

        self.btn_remediate_bridge = QPushButton("✨ Fix & Audit ➔")
        self.btn_remediate_bridge.setObjectName("btn_remediate_primary")
        self.btn_remediate_bridge.setFixedHeight(46)
        self.btn_remediate_bridge.clicked.connect(self.toggle_batch)
        center_layout.addWidget(self.btn_remediate_bridge)

        # Backward compatibility alias
        self.btn_start = self.btn_remediate_bridge

        self.chk_autofix = QCheckBox("Auto-fix barriers")
        self.chk_autofix.setChecked(True)
        self.chk_autofix.setToolTip("Automatically apply deterministic remediations and save .fixed.pdf to output folder.")
        center_layout.addWidget(self.chk_autofix)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(12)
        center_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Ready to audit.")
        self.lbl_status.setObjectName("pane_subtitle")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        center_layout.addWidget(self.lbl_status)

        main_splitter.addWidget(self.center_bridge)

        # ==========================================
        # Right Pane: "2. After (Remediated Files & Reports)"
        # ==========================================
        self.pane_after = QGroupBox("2. After: Remediated Files & Reports")
        self.pane_after.setObjectName("pane_after")
        after_layout = QVBoxLayout(self.pane_after)
        after_layout.setSpacing(8)

        lbl_after_sub = QLabel("Remediated documents and accessibility reports generated in your output directory.")
        lbl_after_sub.setObjectName("pane_subtitle")
        lbl_after_sub.setWordWrap(True)
        after_layout.addWidget(lbl_after_sub)

        # After Tree
        self.tree_after = QTreeWidget()
        self.tree_after.setHeaderLabels(["Generated Item / Document", "Type / Score"])
        tree_header = self.tree_after.header()
        tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_after.itemDoubleClicked.connect(self._on_after_item_double_clicked)
        after_layout.addWidget(self.tree_after, stretch=1)

        # After Action Toolbar
        tb_after = QHBoxLayout()
        self.btn_open_output_folder = QPushButton("📂 Open Output Folder")
        self.btn_open_output_folder.clicked.connect(self.open_output_folder)

        self.btn_view_report = QPushButton("🔍 View Report In-App")
        self.btn_view_report.clicked.connect(self.view_selected_report)

        tb_after.addWidget(self.btn_open_output_folder)
        tb_after.addWidget(self.btn_view_report)
        tb_after.addStretch()
        after_layout.addLayout(tb_after)

        main_splitter.addWidget(self.pane_after)

        # Set default splitter proportions (approx 45% / 10% / 45%)
        main_splitter.setSizes([450, 190, 450])
        main_layout.addWidget(main_splitter, stretch=1)

        # 3. Settings Box (Collapsible/compact)
        settings_group = QGroupBox("Output Settings & Options")
        settings_layout = QHBoxLayout(settings_group)
        settings_layout.setSpacing(12)

        # Output directory selector
        settings_layout.addWidget(QLabel("Output Directory:"))
        docs_dir = Path.home() / "Documents"
        default_out = (docs_dir if docs_dir.is_dir() else Path.home()) / "pdf-a11y-output"
        self.txt_out_dir = QLineEdit(str(default_out))
        self.btn_browse_out = QPushButton("Browse...")
        self.btn_browse_out.clicked.connect(self.browse_output_dir)
        settings_layout.addWidget(self.txt_out_dir, stretch=1)
        settings_layout.addWidget(self.btn_browse_out)

        # Format checkboxes
        settings_layout.addWidget(QLabel("Reports:"))
        self.chk_md = QCheckBox("MD")
        self.chk_md.setChecked(True)
        self.chk_html = QCheckBox("HTML")
        self.chk_pdf = QCheckBox("PDF")
        self.chk_json = QCheckBox("JSON")
        settings_layout.addWidget(self.chk_md)
        settings_layout.addWidget(self.chk_html)
        settings_layout.addWidget(self.chk_pdf)
        settings_layout.addWidget(self.chk_json)

        # Theme selection
        settings_layout.addWidget(QLabel("Theme:"))
        self.cbo_theme = QComboBox()
        for t in available_themes():
            name = t.get("name") if isinstance(t, dict) else str(t)
            label = t.get("label", name) if isinstance(t, dict) else str(t)
            self.cbo_theme.addItem(label, userData=name)

        idx = self.cbo_theme.findData("light")
        if idx >= 0:
            self.cbo_theme.setCurrentIndex(idx)
        settings_layout.addWidget(self.cbo_theme)

        main_layout.addWidget(settings_group)

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
            self._update_ui_state()
            self.lbl_status.setText(f"Added {added_count} PDF document(s). Ready to audit.")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing PDF Documents")
        if folder:
            added = self.queue.add_directory(folder)
            self._update_ui_state()
            self.lbl_status.setText(f"Added {added} PDF document(s) from {Path(folder).name}.")

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF Documents", "", "PDF Documents (*.pdf)")
        if files:
            added = 0
            for f in files:
                if self.queue.add_file(f):
                    added += 1
            self._update_ui_state()
            self.lbl_status.setText(f"Added {added} PDF document(s).")

    def clear_files(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Audit in Progress", "Please stop the active audit before clearing.")
            return
        self.queue.clear()
        self._update_ui_state()
        self.tree_after.clear()
        self.lbl_status.setText("Queue cleared.")

    def browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.txt_out_dir.text())
        if folder:
            self.txt_out_dir.setText(folder)

    def _update_table(self):
        self._update_ui_state()

    def _update_ui_state(self):
        # 1. Update Before Table
        self.table_before.setRowCount(len(self.queue.items))
        for row, item in enumerate(self.queue.items):
            self.table_before.setItem(row, 0, QTableWidgetItem(item.path.name))
            pages_str = str(item.page_count) if item.page_count > 0 else "-"
            self.table_before.setItem(row, 1, QTableWidgetItem(pages_str))
            self.table_before.setItem(row, 2, QTableWidgetItem(item.status))
            findings_str = str(item.findings_count) if item.status == "Completed" else "-"
            self.table_before.setItem(row, 3, QTableWidgetItem(findings_str))
            score_str = f"{item.score:.1f}%" if item.score is not None else "-"
            self.table_before.setItem(row, 4, QTableWidgetItem(score_str))

        # 2. Update After Tree
        self.tree_after.clear()
        for item in self.queue.items:
            if item.status == "Completed":
                score_str = f"{item.score:.1f}%" if item.score is not None else "Complete"
                doc_root = QTreeWidgetItem([f"📄 {item.path.name}", score_str])
                doc_root.setData(0, Qt.ItemDataRole.UserRole, None)

                # Remediated PDF
                if item.remediated_path and item.remediated_path.exists():
                    rem_item = QTreeWidgetItem([f"✨ Fixed PDF: {item.remediated_path.name}", "Remediated Document"])
                    rem_item.setData(0, Qt.ItemDataRole.UserRole, str(item.remediated_path))
                    doc_root.addChild(rem_item)

                # Reports
                if "md" in item.reports and item.reports["md"].exists():
                    md_item = QTreeWidgetItem([f"📊 Audit Report: {item.reports['md'].name}", "Markdown Report"])
                    md_item.setData(0, Qt.ItemDataRole.UserRole, str(item.reports["md"]))
                    md_item.setData(1, Qt.ItemDataRole.UserRole, item.score)
                    doc_root.addChild(md_item)

                if "html" in item.reports and item.reports["html"].exists():
                    html_item = QTreeWidgetItem([f"🌐 HTML Report: {item.reports['html'].name}", "Interactive HTML"])
                    html_item.setData(0, Qt.ItemDataRole.UserRole, str(item.reports["html"]))
                    doc_root.addChild(html_item)

                if "pdf" in item.reports and item.reports["pdf"].exists():
                    pdf_item = QTreeWidgetItem([f"📑 PDF Report: {item.reports['pdf'].name}", "Tagged PDF"])
                    pdf_item.setData(0, Qt.ItemDataRole.UserRole, str(item.reports["pdf"]))
                    doc_root.addChild(pdf_item)

                self.tree_after.addTopLevelItem(doc_root)
                doc_root.setExpanded(True)

    def _on_after_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path_str:
            return
        file_path = Path(file_path_str)
        if file_path.suffix.lower() == ".md":
            score = item.data(1, Qt.ItemDataRole.UserRole)
            dialog = ReportViewerDialog(report_path=file_path, score=score, parent=self)
            dialog.exec()
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path)))

    def view_selected_report(self):
        selected = self.tree_after.selectedItems()
        if not selected:
            QMessageBox.information(self, "Select Item", "Please select a report or document in the 'After' pane.")
            return
        item = selected[0]
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path_str:
            # If a parent item was selected, check for first child report
            if item.childCount() > 0:
                child = item.child(0)
                if child is not None:
                    file_path_str = child.data(0, Qt.ItemDataRole.UserRole)
                    item = child
        if file_path_str:
            file_path = Path(file_path_str)
            if file_path.suffix.lower() == ".md":
                score = item.data(1, Qt.ItemDataRole.UserRole)
                dialog = ReportViewerDialog(report_path=file_path, score=score, parent=self)
                dialog.exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path)))

    def open_output_folder(self):
        out_dir = Path(self.txt_out_dir.text()).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

    def open_triage(self):
        selected_rows = self.table_before.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Document", "Please select a PDF in the 'Before' table to triage.")
            return

        row = selected_rows[0].row()
        item = self.queue.items[row]

        try:
            audit_res = audit_file(str(item.path))
            findings = audit_res.get("findings", [])
            dialog = TriageDialog(item.path, findings, parent=self)
            dialog.exec()
            self.lbl_status.setText(f"Triage complete for {item.path.name}.")
        except Exception as exc:
            QMessageBox.critical(self, "Triage Error", f"Failed to inspect PDF: {exc}")

    def selected_theme(self) -> str:
        data = self.cbo_theme.currentData()
        if data:
            return str(data)
        text = self.cbo_theme.currentText()
        return text if text else "light"

    def start_remediation_flow(self):
        self.toggle_batch()

    def toggle_batch(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.btn_remediate_bridge.setText("Stopping...")
            self.btn_remediate_bridge.setEnabled(False)
            return

        if len(self.queue.items) == 0:
            QMessageBox.information(self, "Empty Queue", "Please add at least one PDF to the 'Before' pane.")
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

        theme = self.selected_theme()
        auto_fix = self.chk_autofix.isChecked()
        out_dir = Path(self.txt_out_dir.text()).resolve()

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self.queue.items))
        self.progress_bar.setValue(0)
        self.btn_remediate_bridge.setText("⏹️ Stop Batch")

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
        self.lbl_status.setText(f"Auditing ({idx + 1}/{total}): {name}...")
        self._update_ui_state()

    def _on_item_progress(self, idx: int, step: str):
        self.lbl_status.setText(step)

    def _on_item_finished(self, idx: int, status: str, findings: int, score: float):
        self.progress_bar.setValue(idx + 1)
        self._update_ui_state()

    def _on_all_completed(self, processed: int, errors: int):
        self.progress_bar.setVisible(False)
        self.btn_remediate_bridge.setText("✨ Fix & Audit ➔")
        self.btn_remediate_bridge.setEnabled(True)
        self.lbl_status.setText(f"Batch completed: {processed} processed, {errors} error(s).")
        self._update_ui_state()
        self.worker_completed_signal.emit(processed, errors)

        import os
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            if errors > 0:
                failures = [f"• {it.path.name}: {it.error_message}" for it in self.queue.items if it.status == "Failed"]
                detail = "\n".join(failures) if failures else "Unknown error occurred."
                QMessageBox.warning(
                    self,
                    "Batch Completed With Errors",
                    f"Processing completed with errors.\nSuccessfully processed: {processed}\nErrors: {errors}\n\nDetails:\n{detail}\n\nOutput: {self.txt_out_dir.text()}",
                )
            else:
                QMessageBox.information(
                    self,
                    "Batch Complete",
                    f"Processing finished!\nSuccessfully processed: {processed}\n\nRemediated documents and reports are ready in the 'After' pane.",
                )

    def _on_error(self, idx: int, msg: str):
        self.lbl_status.setText(f"Error: {msg}")
