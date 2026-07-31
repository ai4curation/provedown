"""Verifier plugin interfaces and default registry."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from provedown.compare import ComparatorRegistry, default_comparators
from provedown.model import Document
from provedown.report import Finding, Report


@dataclass
class VerificationContext:
    """Runtime options shared by verifier plugins."""

    cwd: Path | None = None
    comparators: ComparatorRegistry = field(default_factory=default_comparators)
    sandbox: str | None = None


class Verifier(Protocol):
    """Protocol implemented by all verifier plugins."""

    verifier_id: str

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        """Return findings for a parsed document."""


class VerifierRegistry:
    """Small plugin registry for verifier-neutral orchestration."""

    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {}

    def register(self, verifier: Verifier) -> None:
        self._verifiers[verifier.verifier_id] = verifier

    def get(self, verifier_id: str) -> Verifier:
        return self._verifiers[verifier_id]

    def names(self) -> list[str]:
        return sorted(self._verifiers)

    def verify(
        self,
        document: Document,
        context: VerificationContext | None = None,
        verifier_ids: Sequence[str] | None = None,
    ) -> Report:
        active_context = context or VerificationContext()
        selected = (
            [self._verifiers[name] for name in verifier_ids]
            if verifier_ids is not None
            else [self._verifiers[name] for name in self.names()]
        )
        findings: list[Finding] = []
        for verifier in selected:
            findings.extend(verifier.verify(document, active_context))
        return Report.from_findings(findings)


def default_registry() -> VerifierRegistry:
    from provedown.verifiers.python import PythonResultVerifier
    from provedown.verifiers.sql import SQLResultVerifier

    registry = VerifierRegistry()
    registry.register(PythonResultVerifier())
    registry.register(SQLResultVerifier())
    return registry
