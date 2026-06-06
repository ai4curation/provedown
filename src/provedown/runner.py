"""High-level verification helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from provedown.model import Document, SourceLocation
from provedown.parser import parse_file
from provedown.report import Finding, Report, Status
from provedown.verifiers import VerificationContext, VerifierRegistry, default_registry

PARSER_VERIFIER_ID = "parser"


def verify_document(
    document: Document,
    registry: VerifierRegistry | None = None,
    context: VerificationContext | None = None,
    verifier_ids: Sequence[str] | None = None,
) -> Report:
    active_registry = registry or default_registry()
    findings = list(_diagnostic_findings(document))
    findings.extend(
        active_registry.verify(
            document,
            context=context,
            verifier_ids=verifier_ids,
        ).findings
    )
    return Report.from_findings(findings)


def verify_file(
    path: Path,
    registry: VerifierRegistry | None = None,
    verifier_ids: Sequence[str] | None = None,
) -> Report:
    document = parse_file(path)
    context = VerificationContext(cwd=path.parent)
    return verify_document(
        document,
        registry=registry,
        context=context,
        verifier_ids=verifier_ids,
    )


def _diagnostic_findings(document: Document) -> Iterable[Finding]:
    location = SourceLocation(path=document.path, line=1, column=1)
    for diagnostic in document.diagnostics:
        yield Finding(
            verifier_id=PARSER_VERIFIER_ID,
            status=Status.ERROR,
            location=location,
            message=diagnostic,
        )
