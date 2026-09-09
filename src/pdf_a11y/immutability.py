"""Source file immutability and provenance tracking for pdf-a11y.

Guarantees that input PDF files are never modified in place, maintaining
complete non-destructive audit and remediation guarantees.
"""
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Union


def sha256_file(path: Union[str, Path]) -> str:
    """Calculates the hex-encoded SHA-256 digest of a file."""
    p = Path(path)
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


calculate_sha256 = sha256_file


def assert_source_unchanged(source_path: Union[str, Path], expected_hash: str) -> None:
    """Raises RuntimeError if the file at source_path does not match expected_hash."""
    current_hash = sha256_file(source_path)
    if current_hash != expected_hash:
        raise RuntimeError(
            f"Document immutability violation: Source document was mutated during processing! "
            f"Expected SHA-256: {expected_hash}, Current SHA-256: {current_hash}"
        )


def verify_immutability(path: Union[str, Path], expected_sha256: str) -> bool:
    """Verifies that the target file has not changed from its original SHA-256 digest."""
    assert_source_unchanged(path, expected_sha256)
    return True


def assert_not_same_path(src: Union[str, Path], dest: Union[str, Path]) -> None:
    """Asserts that the destination path is not the exact same file as the source."""
    src_p = Path(src).resolve()
    dest_p = Path(dest).resolve()
    if src_p == dest_p:
        raise ValueError(
            f"Destination path cannot equal source path. pdf-a11y strictly guarantees "
            "that original files remain untouched and immutable."
        )


def verify_remediation_output(source_path: Union[str, Path], dest_path: Union[str, Path]) -> Tuple[str, str]:
    """Validates that destination differs from source and returns (source_hash, dest_hash)."""
    assert_not_same_path(source_path, dest_path)
    return sha256_file(source_path), sha256_file(dest_path)


def get_remediated_path(input_path: Union[str, Path], out_path: Optional[Union[str, Path]] = None) -> Path:
    """Determines the output path for a remediated PDF."""
    in_p = Path(input_path).resolve()
    if out_path:
        return Path(out_path).resolve()
    stem = in_p.stem
    suffix = in_p.suffix or ".pdf"
    return in_p.with_name(f"{stem}-remediated{suffix}")
