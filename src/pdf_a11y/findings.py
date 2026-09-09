"""Finding data model.

Delegates core finding data structures and metrics to engine_a11y.findings.
"""
from typing import Any, Dict
from engine_a11y.findings import (
    Finding,
    Severity,
    SEVERITY_ORDER,
    findings_sorted,
    summarize,
)

BLOCKING = ("critical", "serious")


def finding_to_jsonable(f: Finding) -> Dict[str, Any]:
    return f.to_dict()


__all__ = [
    "Finding",
    "Severity",
    "SEVERITY_ORDER",
    "BLOCKING",
    "finding_to_jsonable",
    "findings_sorted",
    "summarize",
]
