"""Document inspection helpers for code and claim relationships."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from provedown.model import (
    CodeBlock,
    CodeUse,
    Document,
    ResultAssertion,
    SourceLocation,
)
from provedown.parser import parse_file

InspectionEventKind = Literal["code", "code-use", "result"]
InspectionIssueLevel = Literal["error", "warning"]


@dataclass(frozen=True)
class InspectionEvent:
    """One parsed document event rendered for dependency inspection."""

    index: int
    kind: InspectionEventKind
    location: SourceLocation
    language: str
    name: str | None = None
    code: str | None = None
    authored: str | None = None
    compare: str | None = None
    reference: str | None = None
    target_location: SourceLocation | None = None
    execution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "index": self.index,
                "kind": self.kind,
                "location": self.location.display(),
                "language": self.language,
                "name": self.name,
                "code": self.code,
                "authored": self.authored,
                "compare": self.compare,
                "reference": self.reference,
                "target_location": (
                    self.target_location.display()
                    if self.target_location is not None
                    else None
                ),
                "execution": self.execution,
            }
        )


@dataclass(frozen=True)
class InspectionIssue:
    """A relationship issue found without executing document code."""

    level: InspectionIssueLevel
    kind: str
    location: SourceLocation
    message: str
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "level": self.level,
                "kind": self.kind,
                "location": self.location.display(),
                "message": self.message,
                "target": self.target,
            }
        )


@dataclass(frozen=True)
class InspectionReport:
    """Static inspection report for a parsed document."""

    path: Path | None
    events: list[InspectionEvent]
    issues: list[InspectionIssue]

    @property
    def ok(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    def summary(self) -> dict[str, int]:
        return {
            "events": len(self.events),
            "errors": sum(1 for issue in self.issues if issue.level == "error"),
            "warnings": sum(1 for issue in self.issues if issue.level == "warning"),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path is not None else None,
            "ok": self.ok,
            "summary": self.summary(),
            "events": [event.to_dict() for event in self.events],
            "issues": [issue.to_dict() for issue in self.issues],
        }


def inspect_file(path: Path) -> InspectionReport:
    """Parse and inspect one Provedown document from disk."""

    return inspect_document(parse_file(path))


def inspect_document(document: Document) -> InspectionReport:
    """Inspect code/result relationships without executing code."""

    events: list[InspectionEvent] = []
    issues: list[InspectionIssue] = []
    referenced_names = set(document.referenced_code_names())

    for diagnostic in document.diagnostics:
        issues.append(
            InspectionIssue(
                level="error",
                kind="parser-diagnostic",
                location=SourceLocation(path=document.path, line=1, column=1),
                message=diagnostic,
            )
        )

    for index, event in enumerate(document.events, start=1):
        if isinstance(event, CodeBlock):
            events.append(_inspect_code_block(index, event, referenced_names))
        elif isinstance(event, CodeUse):
            events.append(_inspect_code_use(index, event, document, issues))
        elif isinstance(event, ResultAssertion):
            events.append(_inspect_result(index, event, document, issues))

    for name, block in document.named_code.items():
        if name not in referenced_names:
            issues.append(
                InspectionIssue(
                    level="warning",
                    kind="unused-named-code",
                    location=block.location,
                    message=(
                        "named code block is never referenced by a code use "
                        "or result assertion"
                    ),
                    target=name,
                )
            )

    return InspectionReport(path=document.path, events=events, issues=issues)


def _inspect_code_block(
    index: int,
    event: CodeBlock,
    referenced_names: set[str],
) -> InspectionEvent:
    execution = "inline"
    if event.name is not None and event.name in referenced_names:
        execution = "deferred"
    return InspectionEvent(
        index=index,
        kind="code",
        location=event.location,
        language=event.language,
        name=event.name,
        code=event.code,
        execution=execution,
    )


def _inspect_code_use(
    index: int,
    event: CodeUse,
    document: Document,
    issues: list[InspectionIssue],
) -> InspectionEvent:
    target = document.named_code.get(event.name)
    if target is None:
        issues.append(
            InspectionIssue(
                level="error",
                kind="unresolved-code-use",
                location=event.location,
                message=f"code use references unknown block {event.name!r}",
                target=event.name,
            )
        )
    return InspectionEvent(
        index=index,
        kind="code-use",
        location=event.location,
        language=event.language,
        name=event.name,
        reference=event.name,
        target_location=target.location if target is not None else None,
        execution="use-site",
    )


def _inspect_result(
    index: int,
    event: ResultAssertion,
    document: Document,
    issues: list[InspectionIssue],
) -> InspectionEvent:
    ref_name = event.referenced_code_name
    target = document.named_code.get(ref_name) if ref_name is not None else None
    if ref_name is not None and target is None:
        issues.append(
            InspectionIssue(
                level="error",
                kind="unresolved-result-reference",
                location=event.location,
                message=f"result assertion references unknown block {ref_name!r}",
                target=ref_name,
            )
        )
    return InspectionEvent(
        index=index,
        kind="result",
        location=event.location,
        language=event.language,
        code=event.code,
        authored=event.authored,
        compare=event.compare,
        reference=ref_name,
        target_location=target.location if target is not None else None,
        execution="eval",
    )


def _drop_none(items: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in items.items() if value is not None}
