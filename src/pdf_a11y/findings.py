"""Finding data model.

Every rule violation is a Finding. Findings are the currency between
audit (producer), remediate (consumer), and report (renderer).

Schema is intentionally flat + JSON-serializable so results can be
consumed by CI gates and (optionally) agentic tooling.
"""
from dataclasses import asdict, dataclass
from typing import Optional

SEVERITY_ORDER = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}

BLOCKING = ("critical", "serious")


@dataclass
class Finding:
    """One accessibility violation.

    Attributes:
        rule_id:      stable rule identifier, e.g. "language-missing".
        sc:           WCAG success criterion, e.g. "1.3.1".
        severity:     critical | serious | moderate | minor.
        location:     human-readable element location, e.g. "catalog",
                      "page[1] /Image28", "StructTreeRoot", "outline".
        description:  what is wrong.
        evidence:     raw evidence (object values, ratios, ...).
        fixable:      whether a deterministic programmatic fix exists.
        fix:          description of the applied or recommended fix.
    """

    rule_id: str
    sc: str
    severity: str
    location: str
    description: str
    evidence: str = ""
    fixable: bool = False
    fix: str = ""

    def to_dict(self):
        return asdict(self)

    @property
    def blocking(self) -> bool:
        return self.severity in BLOCKING

    def sort_key(self):
        return (SEVERITY_ORDER.get(self.severity, 9), self.location, self.rule_id)


def finding_to_jsonable(f: Finding) -> dict:
    return f.to_dict()


def findings_sorted(findings) -> list:
    return sorted(findings, key=lambda f: f.sort_key())


def summarize(findings) -> dict:
    return {
        "total": len(findings),
        "by_severity": {
            s: sum(1 for f in findings if f.severity == s)
            for s in ("critical", "serious", "moderate", "minor")
        },
        "blocking": sum(1 for f in findings if f.blocking),
        "pass": not any(f.blocking for f in findings),
    }