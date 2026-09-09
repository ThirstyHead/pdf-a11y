"""Interactive human-in-the-loop triage engine for PDF accessibility."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .audit import audit_file
from .immutability import (
    assert_not_same_path,
    assert_source_unchanged,
    get_remediated_path,
    sha256_file,
)
from .remediate import remediate_file
from .rules import AuditContext


@dataclass
class TriageItem:
    rule_id: str
    location: str
    description: str
    prompt: str
    current_value: Optional[str] = None
    action: str = "input"  # "input", "select", "boolean"
    choices: Optional[List[str]] = None
    resolved_value: Optional[Any] = None


class TriageSession:
    """Manages author-intent decision points for document accessibility."""

    def __init__(
        self,
        findings: List[Dict[str, Any]],
        doc_model: Optional[Any] = None,
        file_path: Optional[str] = None,
    ):
        self.findings = findings
        self.doc_model = doc_model
        self.file_path = file_path
        self.items: List[TriageItem] = []
        self._build_items()

    def _build_items(self) -> None:
        for f in self.findings:
            rule_id = f.get("rule_id", "")
            loc = f.get("location", "")
            msg = f.get("message", "")

            if rule_id == "title-missing":
                self.items.append(
                    TriageItem(
                        rule_id=rule_id,
                        location=loc,
                        description=msg or "Document title is missing.",
                        prompt="Enter a descriptive document title (or press Enter to auto-generate):",
                        action="input",
                    )
                )
            elif rule_id in ("language-missing", "language-malformed"):
                self.items.append(
                    TriageItem(
                        rule_id=rule_id,
                        location=loc,
                        description=msg or "Document language is missing or invalid.",
                        prompt="Enter primary language BCP-47 tag (e.g. 'en-US', 'fr-FR'):",
                        action="input",
                        current_value=f.get("evidence", ""),
                    )
                )
            elif rule_id in ("image-alt-missing", "figure-without-alt", "media-alt-missing"):
                self.items.append(
                    TriageItem(
                        rule_id=rule_id,
                        location=loc,
                        description=msg or "Image or figure is missing alternative text.",
                        prompt=f"Enter alternative text for image at {loc} (or 'artifact' to mark decorative):",
                        action="input",
                    )
                )
            elif rule_id in ("outline-missing", "bookmarks-missing"):
                self.items.append(
                    TriageItem(
                        rule_id=rule_id,
                        location=loc,
                        description=msg or "Document has headings but no outline/bookmarks navigation.",
                        prompt="Generate outline / bookmarks from heading structure? (y/n):",
                        action="boolean",
                        choices=["y", "n"],
                    )
                )

    def get_pending_items(self) -> List[TriageItem]:
        return [item for item in self.items if item.resolved_value is None]

    def resolve_item(self, index: int, value: Any) -> None:
        if 0 <= index < len(self.items):
            self.items[index].resolved_value = value

    def to_context_overrides(self) -> Dict[str, Any]:
        overrides: Dict[str, Any] = {}
        for item in self.items:
            if item.resolved_value is None:
                continue
            val = item.resolved_value
            if item.rule_id == "title-missing":
                if isinstance(val, str) and val.strip():
                    overrides["title"] = val.strip()
            elif item.rule_id in ("language-missing", "language-malformed"):
                if isinstance(val, str) and val.strip():
                    overrides["default_language"] = val.strip()
            elif item.rule_id in ("image-alt-missing", "figure-without-alt", "media-alt-missing"):
                if "alt_map" not in overrides:
                    overrides["alt_map"] = {}
                overrides["alt_map"][item.location] = str(val).strip()
        return overrides


def run_interactive_triage(
    in_path: Union[str, Path],
    out_path: Optional[Union[str, Path]] = None,
    input_func: Optional[Callable[[str], str]] = None,
    print_func: Optional[Callable[..., None]] = None,
) -> int:
    """Run interactive terminal triage session and apply remediations non-destructively."""
    in_p = Path(in_path).resolve()
    out_p = Path(out_path).resolve() if out_path else get_remediated_path(in_p)
    assert_not_same_path(in_p, out_p)

    _input = input_func or input
    _print = print_func or print

    initial_hash = sha256_file(in_p)

    audit_res = audit_file(str(in_p))
    findings = audit_res.get("findings") or audit_res.get("issues", [])
    session = TriageSession(findings=findings, file_path=str(in_p))

    _print(f"\n--- Interactive Triage Session: {in_p.name} ---")
    _print(f"Total findings: {len(findings)}, Pending author-intent decisions: {len(session.items)}\n")

    resolved_count = 0
    for idx, item in enumerate(session.items):
        _print(f"[{idx + 1}/{len(session.items)}] {item.description}")
        _print(f"Location: {item.location}")
        try:
            resp = _input(f"{item.prompt} ")
        except (EOFError, KeyboardInterrupt):
            _print("\nTriage interrupted by user.")
            break

        if resp is not None and str(resp).strip():
            session.resolve_item(idx, str(resp).strip())
            resolved_count += 1
        else:
            _print("Skipped.")

    overrides = session.to_context_overrides()
    ctx = AuditContext(source_name=in_p.name)
    if "title" in overrides:
        ctx.title = overrides["title"]
    if "default_language" in overrides:
        ctx.default_language = overrides["default_language"]
    if "alt_map" in overrides:
        ctx.alt_map.update(overrides["alt_map"])

    # Remediate non-destructively
    remediate_file(input_path=in_p, out_path=out_p, context=ctx)
    assert_source_unchanged(in_p, initial_hash)

    _print(f"\nTriage complete. Saved remediated document to: {out_p}\n")
    return resolved_count
