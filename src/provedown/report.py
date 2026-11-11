"""Verification report primitives."""

from __future__ import annotations

import json
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

    def __post_init__(self) -> None:
        # Plugins may pass the status as the plain string the docs describe; a
        # bad value raises here, inside the verifier, so the registry reports
        # it against that verifier instead of failing later in reporting.
        if not isinstance(self.status, Status):
            object.__setattr__(self, "status", Status(self.status))
        if not isinstance(self.location, SourceLocation):
            raise TypeError(
                "Finding location must be a SourceLocation, not "
                f"{type(self.location).__name__}"
            )
        # Every field goes into JSON reports, so check them here rather than
        # fail while printing a report after every document has been verified.
        for name in ("verifier_id", "message"):
            _require_str(name, getattr(self, name), optional=False)
        for name in ("expected", "actual"):
            _require_str(name, getattr(self, name), optional=True)
        try:
            evidence = dict(self.evidence)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Finding evidence must be a JSON-serializable mapping: {exc}"
            ) from exc
        for key in evidence:
            if not isinstance(key, str):
                raise TypeError(
                    f"Finding evidence keys must be strings, not {type(key).__name__}"
                )
        try:
            # Strict JSON: NaN and infinities are not valid in --format json.
            text = json.dumps(evidence, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Finding evidence must be a JSON-serializable mapping: {exc}"
            ) from exc
        # Keep a deep copy decoded from the checked text, so a plugin changing
        # its own objects later cannot change or break this finding's evidence.
        object.__setattr__(self, "evidence", json.loads(text))

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


def _require_str(name: str, value: object, *, optional: bool) -> None:
    if isinstance(value, str) or (optional and value is None):
        return
    expected = "a str or None" if optional else "a str"
    raise TypeError(f"Finding {name} must be {expected}, not {type(value).__name__}")


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
