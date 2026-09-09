"""Tests for the unified CLI twin interface matching docx-a11y, pptx-a11y, and xslx-a11y."""
from pathlib import Path
import pytest
from pdf_a11y.cli import main

FIX = Path(__file__).resolve().parent / "fixtures"


def test_cli_audit_clean(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        main([str(FIX / "clean.pdf"), "--output-dir", str(tmp_path)])
    assert exc.value.code == 0


def test_cli_audit_violations(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        main([str(FIX / "violations.pdf"), "--output-dir", str(tmp_path)])
    assert exc.value.code == 1


def test_cli_missing_file():
    with pytest.raises(SystemExit) as exc:
        main(["non_existent_file.pdf"])
    assert exc.value.code == 2


def test_cli_formats_and_reports(tmp_path: Path):
    out_dir = tmp_path / "reports"
    with pytest.raises(SystemExit) as exc:
        main([
            str(FIX / "clean.pdf"),
            "--format", "md,html,pdf,json",
            "--theme", "ocean",
            "--output-dir", str(out_dir),
        ])
    assert exc.value.code == 0
    assert (out_dir / "clean-a11y-report.md").exists()
    assert (out_dir / "clean-a11y-report.html").exists()
    assert (out_dir / "clean-a11y-report.pdf").exists()
    assert (out_dir / "clean-audit.json").exists()


def test_cli_fix_and_integrity(tmp_path: Path, capsys):
    out_dir = tmp_path / "reports"
    fixed_pdf = tmp_path / "remediated.pdf"
    with pytest.raises(SystemExit) as exc:
        main([
            str(FIX / "fixable.pdf"),
            "--fix",
            "--out-pdf", str(fixed_pdf),
            "--format", "md,html",
            "--output-dir", str(out_dir),
            "--theme", "forest",
        ])
    captured = capsys.readouterr()
    assert "[Integrity Verified]" in captured.out
    assert fixed_pdf.exists()
    assert (out_dir / "fixable-a11y-report.md").exists()
    assert (out_dir / "fixable-a11y-report.html").exists()


def test_cli_rejects_overwriting_input(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        main([
            str(FIX / "clean.pdf"),
            "--fix",
            "--out-pdf", str(FIX / "clean.pdf"),
        ])
    assert "cannot match input document" in str(exc.value)
