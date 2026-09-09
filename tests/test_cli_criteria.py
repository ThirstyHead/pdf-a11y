"""Tests for criteria checklist CLI flags in pdf-a11y (--init-criteria and --criteria)."""
from pathlib import Path
import shutil
import pytest
from pdf_a11y.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
VIOLATIONS = FIXTURES / "violations.pdf"


def test_cli_init_criteria(tmp_path: Path):
    target = tmp_path / "criteria.md"
    with pytest.raises(SystemExit) as exc:
        main(["--init-criteria", str(target)])
    assert exc.value.code == 0
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "Criteria Checklist" in content
    assert "[x] 1.1.1" in content


def test_cli_criteria_what_if(tmp_path: Path):
    doc = tmp_path / "doc.pdf"
    shutil.copyfile(VIOLATIONS, doc)

    criteria_file = tmp_path / "criteria.md"
    criteria_file.write_text(
        "# Custom Criteria\n\n"
        "[ ] 1.1.1 Non-text Content\n"
        "[ ] 1.3.1 Info and Relationships\n"
        "[ ] 2.4.2 Page Titled\n"
        "[ ] 3.1.1 Language of Page\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    with pytest.raises(SystemExit) as exc:
        main(
            [
                str(doc),
                "--format",
                "md",
                "--output-dir",
                str(out_dir),
                "--criteria",
                str(criteria_file),
            ]
        )
    # With violations partitioned to excluded, should exit 0 or have report with excluded
    report_file = out_dir / "doc-a11y-report.md"
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "What-If" in content or "EXCLUDED" in content
