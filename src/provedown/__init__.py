"""Public API for Provedown."""

from provedown.compare import Comparator, ComparatorRegistry, ComparisonResult
from provedown.model import (
    CodeBlock,
    CodeUse,
    Document,
    DocumentEvent,
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
    "ParseError",
    "Report",
    "ResultAssertion",
    "SourceLocation",
    "Status",
    "VerificationContext",
    "Verifier",
    "VerifierRegistry",
    "default_registry",
    "parse_document",
    "parse_file",
    "verify_document",
    "verify_file",
]
