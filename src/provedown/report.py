"""Verification report primitives."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from provedown.model import SourceLocation


class Status(str, Enum):
    """Portable status values returned by all verifier plugins."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    """One verifier result tied to a document location."""

    verifier_id: str
    status: Status
    location: SourceLocation
    message: str
    expected: str | None = None
    actual: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifier_id": self.verifier_id,
            "status": self.status.value,
            "location": self.location.display(),
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class Report:
    """Aggregate output from one or more verifiers."""

    findings: list[Finding]

    @classmethod
    def from_findings(cls, findings: Iterable[Finding]) -> Report:
        return cls(list(findings))

    @property
    def ok(self) -> bool:
        return not any(
            finding.status in {Status.FAIL, Status.ERROR} for finding in self.findings
        )

    def count(self, status: Status) -> int:
        return sum(1 for finding in self.findings if finding.status == status)

    def summary(self) -> dict[str, int]:
        return {status.value: self.count(status) for status in Status}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary(),
            "findings": [finding.to_dict() for finding in self.findings],
        }
