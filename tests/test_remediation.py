"""Tests for deterministic remediation engine and remediate_file."""
from pathlib import Path
import shutil
import pytest

from pdf_a11y.immutability import sha256_file
from pdf_a11y.remediate import remediate_file

FIX = Path(__file__).resolve().parent / "fixtures"


def test_remediate_file_end_to_end_immutability(tmp_path: Path):
    src = tmp_path / "violations_copy.pdf"
    shutil.copy(FIX / "violations.pdf", src)

    sha_before = sha256_file(src)
    out = tmp_path / "violations_copy-remediated.pdf"

    res = remediate_file(src, out)

    sha_after = sha256_file(src)
    assert sha_before == sha_after, "Source file was modified!"
    assert res["original_file_immutable"] is True
    assert out.exists()
    assert res["remediated_sha256"] == sha256_file(out)
    assert res["original_sha256"] == sha_before


def test_remediate_file_rejects_same_path(tmp_path: Path):
    src = tmp_path / "sample.pdf"
    src.write_bytes(b"%PDF-1.4\n%EOF")
    with pytest.raises(ValueError, match="Destination path cannot equal source path"):
        remediate_file(src, src)
