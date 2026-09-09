"""Source file immutability and provenance tracking for pdf-a11y.

Delegates to engine_a11y.immutability.
"""
from pathlib import Path
from typing import Optional, Tuple, Union
from engine_a11y.immutability import (
    assert_source_unchanged,
    calculate_sha256,
    get_remediated_path as _engine_get_remediated_path,
    sha256_file,
    verify_immutability,
)


def assert_not_same_path(src: Union[str, Path], dest: Union[str, Path]) -> None:
    src_p = Path(src).resolve()
    dest_p = Path(dest).resolve()
    if src_p == dest_p:
        raise ValueError(
            "Destination path cannot equal source path. pdf-a11y strictly guarantees "
            "that original files remain untouched and immutable."
        )


def verify_remediation_output(source_path: Union[str, Path], dest_path: Union[str, Path]) -> Tuple[str, str]:
    assert_not_same_path(source_path, dest_path)
    return sha256_file(source_path), sha256_file(dest_path)


def get_remediated_path(input_path: Union[str, Path], out_path: Optional[Union[str, Path]] = None) -> Path:
    return _engine_get_remediated_path(input_path, out_path=out_path, suffix_tag="-remediated")


__all__ = [
    "sha256_file",
    "calculate_sha256",
    "assert_source_unchanged",
    "verify_immutability",
    "assert_not_same_path",
    "verify_remediation_output",
    "get_remediated_path",
]
