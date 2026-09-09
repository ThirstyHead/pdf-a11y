"""Remediation progress statistics (progress over perfection).

Delegates to engine_a11y.reports.stats.
"""
from typing import Any, Dict, Optional
from engine_a11y.reports.stats import compute_progress_stats


def compute_stats(
    found_before: int,
    remaining_after: int,
    pass_before: Optional[bool] = None,
    pass_after: Optional[bool] = None,
) -> Dict[str, Any]:
    corrected = max(found_before - remaining_after, 0)
    if found_before == 0:
        pct = 100.0
    else:
        pct = round(corrected / found_before * 100, 1)
    return {
        "found_before": found_before,
        "remaining_after": remaining_after,
        "corrected": corrected,
        "improvement_pct": pct,
        "pass_before": pass_before,
        "pass_after": pass_after,
    }


__all__ = ["compute_stats", "compute_progress_stats"]
