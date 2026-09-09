"""Tests for root CLI parity with sibling accessibility tools."""
from pathlib import Path
import shutil
import pytest
from unittest.mock import patch

from pdf_a11y.cli import main
from pdf_a11y.immutability import sha256_file

FIXTURES = Path(__file__).parent / "fixtures"
CLEAN = FIXTURES / "clean.pdf"
VIOLATIONS = FIXTURES / "violations.pdf"


def test_cli_help_no_args(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "pdf-a11y" in err
    assert "--fix" in err
    assert "--format" in err


def test_cli_gui_flag():
    with patch("pdf_a11y.gui.app.main") as mock_gui:
        with pytest.raises(SystemExit) as exc:
            main(["--gui"])
        assert exc.value.code == 0
        mock_gui.assert_called_once()


def test_cli_direct_audit(tmp_path: Path):
    doc = tmp_path / "doc.pdf"
    shutil.copyfile(CLEAN, doc)
    orig_hash = sha256_file(doc)

    with pytest.raises(SystemExit) as exc:
        main([str(doc), "--format", "md,json", "--output-dir", str(tmp_path)])
    assert exc.value.code == 0
    # Immutability preserved
    assert sha256_file(doc) == orig_hash
    # Reports generated
    assert (tmp_path / "doc-a11y-report.md").exists()
    assert (tmp_path / "doc-audit.json").exists()


def test_cli_direct_fix(tmp_path: Path):
    doc = tmp_path / "doc.pdf"
    shutil.copyfile(VIOLATIONS, doc)
    orig_hash = sha256_file(doc)

    out_pdf = tmp_path / "fixed.pdf"
    with pytest.raises(SystemExit) as exc:
        main([
            str(doc),
            "--fix",
            "--out-pdf", str(out_pdf),
            "--format", "md,html,pdf,json",
            "--output-dir", str(tmp_path)
        ])
    assert exc.value.code in (0, 1)

    # Source untouched
    assert sha256_file(doc) == orig_hash
    # Remediated PDF exists
    assert out_pdf.exists()
    # All 4 reports generated
    assert (tmp_path / "doc-a11y-report.md").exists()
    assert (tmp_path / "doc-a11y-report.html").exists()
    assert (tmp_path / "doc-a11y-report.pdf").exists()
    assert (tmp_path / "doc-audit.json").exists()


def test_cli_direct_triage(tmp_path: Path):
    doc = tmp_path / "doc.pdf"
    shutil.copyfile(VIOLATIONS, doc)
    orig_hash = sha256_file(doc)

    out_triaged = tmp_path / "triaged.pdf"
    with patch("pdf_a11y.cli.run_interactive_triage") as mock_triage:
        with pytest.raises(SystemExit) as exc:
            main([
                str(doc),
                "--triage",
                "--out-pdf", str(out_triaged),
                "--output-dir", str(tmp_path)
            ])
        assert exc.value.code in (0, 1)
        mock_triage.assert_called_once()
        assert sha256_file(doc) == orig_hash
