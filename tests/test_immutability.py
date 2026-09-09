"""Tests for document immutability and SHA-256 verification."""
import hashlib
from pathlib import Path
import pytest

from pdf_a11y.immutability import (
    sha256_file,
    calculate_sha256,
    assert_source_unchanged,
    verify_immutability,
    verify_remediation_output,
    assert_not_same_path,
    get_remediated_path,
)


def test_sha256_calculation(tmp_path):
    f = tmp_path / "sample.pdf"
    f.write_bytes(b"%PDF-1.4\n%EOF")
    h = sha256_file(f)
    assert len(h) == 64
    assert calculate_sha256(f) == h


def test_assert_source_unchanged_passes(tmp_path):
    f = tmp_path / "sample.pdf"
    f.write_bytes(b"%PDF-1.4\n%EOF")
    h = sha256_file(f)
    assert_source_unchanged(f, h)
    assert verify_immutability(f, h) is True


def test_assert_source_unchanged_fails_on_mutation(tmp_path):
    f = tmp_path / "sample.pdf"
    f.write_bytes(b"%PDF-1.4\n%EOF")
    h = sha256_file(f)
    f.write_bytes(b"%PDF-1.4\nmutated\n%EOF")
    with pytest.raises(RuntimeError, match="mutated"):
        assert_source_unchanged(f, h)


def test_verify_remediation_output_rejects_same_path(tmp_path):
    f = tmp_path / "sample.pdf"
    f.write_bytes(b"%PDF-1.4\n%EOF")
    with pytest.raises(ValueError, match="Destination path cannot equal source path"):
        verify_remediation_output(f, f)
    with pytest.raises(ValueError, match="strictly guarantees that original files remain"):
        assert_not_same_path(f, f)


def test_get_remediated_path():
    in_path = Path("/path/to/Sample.pdf")
    out_path = get_remediated_path(in_path)
    assert out_path == Path("/path/to/Sample-remediated.pdf")

    explicit = Path("/somewhere/custom.pdf")
    assert get_remediated_path(in_path, explicit) == explicit


def test_verify_remediation_output_returns_hashes(tmp_path):
    src = tmp_path / "src.pdf"
    src.write_bytes(b"%PDF-1.4\nsrc\n%EOF")
    dst = tmp_path / "dst.pdf"
    dst.write_bytes(b"%PDF-1.4\ndst\n%EOF")
    h_src, h_dst = verify_remediation_output(src, dst)
    assert h_src == sha256_file(src)
    assert h_dst == sha256_file(dst)
