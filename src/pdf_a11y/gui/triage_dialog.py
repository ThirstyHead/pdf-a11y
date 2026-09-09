"""Visual interactive remediation dialog for PDF accessibility barriers."""
from pathlib import Path
from typing import Any, List, Optional, Union
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from pdf_a11y.immutability import sha256_file
from pdf_a11y.remediate import remediate_file
from pdf_a11y.rules import AuditContext
from pdf_a11y.triage import TriageSession


class TriageDialog(QDialog):
    def __init__(
        self,
        pdf_path: Union[Path, str],
        findings: List[Any],
        parent=None,
    ):
        super().__init__(parent)
        self.pdf_path = Path(pdf_path).resolve()
        findings_dicts = []
        for f in findings:
            if hasattr(f, "to_dict"):
                findings_dicts.append(f.to_dict())
            elif isinstance(f, dict):
                findings_dicts.append(f)

        self.session = TriageSession(findings=findings_dicts, file_path=str(self.pdf_path))
        self.current_idx = 0
        self.items_modified = 0

        self.setWindowTitle("Interactive Remediation Triage — pdf-a11y")
        self.resize(620, 340)
        self._init_ui()
        self._load_current()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.lbl_progress = QLabel("Barrier 1 of 1")
        self.lbl_progress.setStyleSheet("font-weight: 600; color: #0284c7;")
        layout.addWidget(self.lbl_progress)

        self.lbl_location = QLabel("Location:")
        self.lbl_location.setStyleSheet("font-weight: 600; color: #334155;")
        layout.addWidget(self.lbl_location)

        self.lbl_desc = QLabel("Description:")
        self.lbl_desc.setWordWrap(True)
        layout.addWidget(self.lbl_desc)

        # Input row
        self.lbl_input_prompt = QLabel("Descriptive Text / Value:")
        layout.addWidget(self.lbl_input_prompt)

        self.txt_input = QLineEdit()
        layout.addWidget(self.txt_input)

        self.chk_decorative = QCheckBox("Mark as Artifact / Decorative (screen readers will ignore)")
        layout.addWidget(self.chk_decorative)

        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_skip = QPushButton("Skip (Leave Unchanged)")
        self.btn_skip.clicked.connect(self.skip_current)

        self.btn_apply = QPushButton("Apply & Continue")
        self.btn_apply.setObjectName("btn_primary")
        self.btn_apply.clicked.connect(self.apply_current)

        btn_layout.addWidget(self.btn_skip)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    def _load_current(self):
        if not self.session.items:
            self.lbl_progress.setText("No triageable barriers found.")
            self.lbl_location.setText("")
            self.lbl_desc.setText("All automated checks either passed or require standard deterministic fixes.")
            self.txt_input.setEnabled(False)
            self.chk_decorative.setEnabled(False)
            self.btn_apply.setEnabled(False)
            self.btn_skip.setText("Close")
            return

        if self.current_idx >= len(self.session.items):
            self._finish_triage()
            return

        item = self.session.items[self.current_idx]
        total = len(self.session.items)
        self.lbl_progress.setText(f"Barrier {self.current_idx + 1} of {total}")
        self.lbl_location.setText(f"Location: {item.location}")
        self.lbl_desc.setText(item.description)
        self.lbl_input_prompt.setText(item.prompt)

        is_alt = item.rule_id in ("image-alt-missing", "figure-without-alt", "media-alt-missing")
        self.chk_decorative.setVisible(is_alt)
        self.chk_decorative.setChecked(False)

        self.txt_input.setText("")
        self.txt_input.setFocus()

    def skip_current(self):
        if not self.session.items or self.current_idx >= len(self.session.items):
            self.accept()
            return
        self.current_idx += 1
        self._load_current()

    def apply_current(self):
        if not self.session.items or self.current_idx >= len(self.session.items):
            self.accept()
            return

        item = self.session.items[self.current_idx]
        val = None

        if self.chk_decorative.isVisible() and self.chk_decorative.isChecked():
            val = "artifact"
        else:
            txt = self.txt_input.text().strip()
            if txt:
                val = txt

        if val is not None:
            self.session.resolve_item(self.current_idx, val)
            self.items_modified += 1

        self.current_idx += 1
        self._load_current()

    def _finish_triage(self):
        if self.items_modified > 0:
            out_p = self.pdf_path.with_name(f"{self.pdf_path.stem}-triaged.pdf")
            overrides = self.session.to_context_overrides()
            ctx = AuditContext(source_name=self.pdf_path.name)
            if "title" in overrides:
                ctx.title = overrides["title"]
            if "default_language" in overrides:
                ctx.default_language = overrides["default_language"]
            if "alt_map" in overrides:
                ctx.alt_map.update(overrides["alt_map"])

            remediate_file(input_path=self.pdf_path, out_path=out_p, context=ctx)

        self.accept()
