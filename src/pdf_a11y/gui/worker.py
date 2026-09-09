"""Background QThread workers for executing PDF document audits and batch remediation."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from PySide6.QtCore import QThread, Signal

from pdf_a11y.audit import audit_file
from pdf_a11y.docmodel import DocModel
from pdf_a11y.gui.models import BatchItem
from pdf_a11y.immutability import get_remediated_path
from pdf_a11y.remediate import remediate_file
from pdf_a11y.reports.html import render_html
from pdf_a11y.reports.md import render_md
from pdf_a11y.reports.pdf import render_pdf
from pdf_a11y.rules import AuditContext


class AuditWorker(QThread):
    audit_completed = Signal(dict)
    audit_failed = Signal(str)

    def __init__(self, file_path: Union[Path, str], parent=None):
        super().__init__(parent)
        self.file_path = Path(file_path)

    def run(self):
        try:
            res = audit_file(str(self.file_path))
            self.audit_completed.emit(res)
        except Exception as exc:
            self.audit_failed.emit(f"Audit failed: {type(exc).__name__}: {exc}")


class RemediateWorker(QThread):
    remediation_completed = Signal(dict)
    remediation_failed = Signal(str)

    def __init__(
        self,
        file_path: Union[Path, str],
        out_path: Optional[Union[Path, str]] = None,
        context: Optional[AuditContext] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.out_path = Path(out_path) if out_path else None
        self.context = context

    def run(self):
        try:
            res = remediate_file(self.file_path, out_path=self.out_path, context=self.context)
            self.remediation_completed.emit(res)
        except Exception as exc:
            self.remediation_failed.emit(f"Remediation failed: {type(exc).__name__}: {exc}")


class BatchWorker(QThread):
    item_started = Signal(int, int, str)  # (item_idx, total_items, file_name)
    item_progress = Signal(int, str)  # (item_idx, step_name)
    item_finished = Signal(int, str, int, float)  # (item_idx, status, findings_count, score)
    all_completed = Signal(int, int)  # (total_processed, total_errors)
    error_occurred = Signal(int, str)  # (item_idx, error_message)

    def __init__(
        self,
        items: List[BatchItem],
        out_dir: Union[Path, str],
        formats: List[str],
        theme: str = "light",
        auto_fix: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.items = items
        self.out_dir = Path(out_dir)
        self.formats = formats
        self.theme = theme
        self.auto_fix = auto_fix
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.error_occurred.emit(0, f"Cannot create output directory '{self.out_dir}': {exc}")
            self.all_completed.emit(0, len(self.items))
            return

        total = len(self.items)
        processed = 0
        errors = 0

        for idx, item in enumerate(self.items):
            if self._stop_requested:
                break

            item.status = "Auditing"
            self.item_started.emit(idx, total, item.path.name)

            try:
                # 1. Count pages
                try:
                    with DocModel.open(item.path) as dm:
                        item.page_count = len(dm.doc.pages)
                except Exception:
                    item.page_count = 0

                # 2. Audit document
                self.item_progress.emit(idx, "Auditing PDF...")
                audit_res = audit_file(str(item.path))
                findings = audit_res.get("findings", [])
                item.findings_count = len(findings)
                item.critical_count = sum(1 for f in findings if f.get("severity") == "critical")
                summary = audit_res.get("summary", {})
                score = summary.get("score")
                item.score = float(score) if score is not None else (100.0 if not findings else 50.0)

                target_doc_path = item.path

                # 3. Remediate if requested
                if self.auto_fix and findings:
                    self.item_progress.emit(idx, "Applying deterministic remediations...")
                    rem_out = self.out_dir / f"{item.path.stem}.fixed.pdf"
                    remediate_file(input_path=item.path, out_path=rem_out)
                    item.remediated_path = rem_out
                    target_doc_path = rem_out

                # 4. Generate requested reports
                self.item_progress.emit(idx, "Generating accessibility reports...")
                stem = item.path.stem
                if "json" in self.formats:
                    json_out = self.out_dir / f"{stem}-a11y-report.json"
                    json_out.write_text(json.dumps(audit_res, indent=2))
                    item.reports["json"] = json_out

                if "md" in self.formats or "html" in self.formats or "pdf" in self.formats:
                    md_text = render_md(audit_res, source_path=item.path)
                    if "md" in self.formats:
                        md_out = self.out_dir / f"{stem}-a11y-report.md"
                        md_out.write_text(md_text)
                        item.reports["md"] = md_out

                    if "html" in self.formats or "pdf" in self.formats:
                        html_doc = render_html(md_text, theme=self.theme, lang=audit_res.get("language") or "en")
                        if "html" in self.formats:
                            html_out = self.out_dir / f"{stem}.html"
                            html_out.write_text(html_doc)
                            item.reports["html"] = html_out

                        if "pdf" in self.formats:
                            pdf_out = self.out_dir / f"{stem}-a11y-report.pdf"
                            render_pdf(html_doc, theme=self.theme, out_path=pdf_out, lang=audit_res.get("language") or "en")
                            item.reports["pdf"] = pdf_out

                item.status = "Completed"
                self.item_finished.emit(idx, "Completed", item.findings_count, item.score)
                processed += 1

            except Exception as exc:
                item.status = "Failed"
                item.error_message = str(exc)
                self.error_occurred.emit(idx, f"Error processing {item.path.name}: {exc}")
                self.item_finished.emit(idx, "Failed", 0, 0.0)
                errors += 1

        self.all_completed.emit(processed, errors)
