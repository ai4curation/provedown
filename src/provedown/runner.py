"""High-level verification helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from provedown.model import Document, SourceLocation
from provedown.parser import parse_file
from provedown.report import Finding, Report, Status
from provedown.verifiers import VerificationContext, VerifierRegistry, default_registry

PARSER_VERIFIER_ID = "parser"
VERIFICATION_SKIPPED_MESSAGE = "verification skipped: document has parser errors"


def verify_document(
    document: Document,
    registry: VerifierRegistry | None = None,
    context: VerificationContext | None = None,
    verifier_ids: Sequence[str] | None = None,
) -> Report:
    findings = list(_diagnostic_findings(document))
    # Parser diagnostics are currently all errors. Keep the status-based gate so
    # typed warning diagnostics can remain non-blocking if they are added later.
    if any(finding.status == Status.ERROR for finding in findings):
        findings.append(
            Finding(
                verifier_id=PARSER_VERIFIER_ID,
                status=Status.SKIP,
                location=SourceLocation(path=document.path, line=1, column=1),
                message=VERIFICATION_SKIPPED_MESSAGE,
            )
        )
        return Report.from_findings(findings)

    active_registry = registry or default_registry()
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
    sandbox: str | None = None,
) -> Report:
    document = parse_file(path)
    context = VerificationContext(cwd=path.parent, sandbox=sandbox)
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
