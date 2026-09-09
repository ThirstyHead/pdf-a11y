"""Remediation progress statistics (progress over perfection)."""
from typing import Any, Dict, Optional


def compute_stats(found_before: int, remaining_after: int,
                  pass_before: Optional[bool] = None,
                  pass_after: Optional[bool] = None) -> Dict[str, Any]:
    """Improvement metrics for the summary banner / JSON report.

    improvement_pct = (found_before - remaining_after) / found_before * 100,
    1 decimal; found_before == 0 -> 100.0 ("no barriers found").
    """
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


def compute_progress_stats(
    before_summary: Dict[str, Any],
    after_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculates progress metrics between before and after audit states."""
    b_total = before_summary.get("total", 0)
    b_blocking = before_summary.get("blocking", 0)

    if after_summary is None:
        return {
            "mode": "audit_only",
            "total_findings": b_total,
            "blocking_findings": b_blocking,
            "compliance_verdict": "PASS" if b_blocking == 0 else "ACTION REQUIRED",
        }

    a_total = after_summary.get("total", 0)
    a_blocking = after_summary.get("blocking", 0)
    resolved_blocking = max(0, b_blocking - a_blocking)
    improvement_rate = 100.0 if b_blocking == 0 else round((resolved_blocking / b_blocking) * 100.0, 1)

    return {
        "mode": "remediated",
        "before_total": b_total,
        "after_total": a_total,
        "before_blocking": b_blocking,
        "after_blocking": a_blocking,
        "resolved_blocking": resolved_blocking,
        "improvement_rate_pct": improvement_rate,
        "compliance_verdict": "PASS" if a_blocking == 0 else "PARTIAL REMEDIATION (MANUAL REVIEW NEEDED)",
    }
