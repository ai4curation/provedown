"""Public API for Provedown."""

from provedown.compare import Comparator, ComparatorRegistry, ComparisonResult
from provedown.inspection import (
    InspectionEvent,
    InspectionIssue,
    InspectionReport,
    inspect_document,
    inspect_file,
)
from provedown.linting import LintFinding, LintReport, lint_document, lint_file
from provedown.model import (
    CodeBlock,
    CodeUse,
    Document,
    DocumentEvent,
    ProvedownConfig,
    ResultAssertion,
    SourceLocation,
)
from provedown.parser import ParseError, parse_document, parse_file
from provedown.report import Finding, Report, Status
from provedown.runner import verify_document, verify_file
from provedown.verifiers import (
    VerificationContext,
    Verifier,
    VerifierRegistry,
    default_registry,
)

__all__ = [
    "CodeBlock",
    "CodeUse",
    "Comparator",
    "ComparatorRegistry",
    "ComparisonResult",
    "Document",
    "DocumentEvent",
    "Finding",
    "InspectionEvent",
    "InspectionIssue",
    "InspectionReport",
    "LintFinding",
    "LintReport",
    "ParseError",
    "ProvedownConfig",
    "Report",
    "ResultAssertion",
    "SourceLocation",
    "Status",
    "VerificationContext",
    "Verifier",
    "VerifierRegistry",
    "default_registry",
    "inspect_document",
    "inspect_file",
    "lint_document",
    "lint_file",
    "parse_document",
    "parse_file",
    "verify_document",
    "verify_file",
]
