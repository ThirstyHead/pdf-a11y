"""Audit engine: run all rules against a PDF and collect findings."""
import time

from .findings import Finding, findings_sorted, summarize
from .rules import RULES, AuditContext


def audit_file(path, ctx=None) -> dict:
    """Audit a PDF file. Returns a result dict (JSON-safe).

    Result shape:
    {
      "file": str,
      "audited_at": iso8601,
      "tool": "pdf-a11y/0.1.0",
      "findings": [ {rule_id, sc, severity, location, description, evidence, fixable, fix}, ... ],
      "summary": {total, by_severity, blocking, pass}
    }
    """
    from .docmodel import DocModel
    from . import __version__

    with DocModel.open(path) as dm:
        if ctx is None:
            from pathlib import Path
            ctx = AuditContext(source_name=Path(path).name)
        findings = []
        for rule in RULES:
            try:
                findings.extend(rule.check(dm, ctx))
            except Exception as exc:  # a broken rule must not kill the whole audit
                findings.append(Finding(f"{rule.rule_id}__error", rule.sc, "moderate",
                                        "internal",
                                        f"Rule {rule.rule_id} raised: {exc}",
                                        repr(exc), False,
                                        "Fix the rule; treat as manual review."))
    return {
        "file": str(path).rsplit("/", 1)[-1],
        "audited_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": f"pdf-a11y/{__version__}",
        "findings": [f.to_dict() for f in findings_sorted(findings)],
        "summary": summarize(findings_sorted(findings)),
    }


def audit_result_to_json(result: dict) -> str:
    import json
    return json.dumps(result, indent=2, sort_keys=True)


def load_result(path) -> dict:
    import json
    from pathlib import Path
    return json.loads(Path(path).read_text())