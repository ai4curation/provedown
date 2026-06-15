"""Static lints for fragile Provedown documents."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from provedown.inspection import inspect_document
from provedown.model import CodeBlock, Document, ResultAssertion, SourceLocation
from provedown.parser import parse_file

LintLevel = Literal["error", "warning"]


@dataclass(frozen=True)
class LintFinding:
    """One lint finding tied to a document location."""

    level: LintLevel
    code: str
    location: SourceLocation
    message: str
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "level": self.level,
            "code": self.code,
            "location": self.location.display(),
            "message": self.message,
        }
        if self.target is not None:
            payload["target"] = self.target
        return payload


@dataclass(frozen=True)
class LintReport:
    """Aggregate lint report for one document."""

    path: Path | None
    findings: list[LintFinding]

    @property
    def ok(self) -> bool:
        return not any(finding.level == "error" for finding in self.findings)

    def summary(self) -> dict[str, int]:
        return {
            "errors": sum(1 for finding in self.findings if finding.level == "error"),
            "warnings": sum(
                1 for finding in self.findings if finding.level == "warning"
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path is not None else None,
            "ok": self.ok,
            "summary": self.summary(),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def lint_file(path: Path) -> LintReport:
    """Parse and lint one Provedown document from disk."""

    return lint_document(parse_file(path))


def lint_document(document: Document) -> LintReport:
    """Lint a parsed document without executing code."""

    findings: list[LintFinding] = []
    _add_relationship_lints(document, findings)
    _add_result_policy_lints(document, findings)
    _add_python_fragility_lints(document, findings)
    return LintReport(path=document.path, findings=findings)


def _add_relationship_lints(
    document: Document,
    findings: list[LintFinding],
) -> None:
    for issue in inspect_document(document).issues:
        if issue.kind == "parser-diagnostic":
            findings.append(
                LintFinding(
                    level="error",
                    code="parser-diagnostic",
                    location=issue.location,
                    message=issue.message,
                    target=issue.target,
                )
            )
        elif issue.kind in {"unresolved-code-use", "unresolved-result-reference"}:
            findings.append(
                LintFinding(
                    level="error",
                    code=issue.kind,
                    location=issue.location,
                    message=issue.message,
                    target=issue.target,
                )
            )
        elif issue.kind == "unused-named-code":
            findings.append(
                LintFinding(
                    level="warning",
                    code=issue.kind,
                    location=issue.location,
                    message=issue.message,
                    target=issue.target,
                )
            )


def _add_result_policy_lints(
    document: Document,
    findings: list[LintFinding],
) -> None:
    none_results: list[ResultAssertion] = []
    for event in document.events:
        if not isinstance(event, ResultAssertion) or event.compare != "none":
            continue
        none_results.append(event)
        if not _has_justification(event):
            findings.append(
                LintFinding(
                    level="warning",
                    code="unjustified-none-compare",
                    location=event.location,
                    message=(
                        'result uses data-compare="none" without data-reason '
                        "or data-justification"
                    ),
                    target=event.authored,
                )
            )

    if len(none_results) > 3:
        findings.append(
            LintFinding(
                level="warning",
                code="excessive-none-compare",
                location=none_results[0].location,
                message=(
                    f"document has {len(none_results)} unverified result "
                    "assertions"
                ),
            )
        )


def _add_python_fragility_lints(
    document: Document,
    findings: list[LintFinding],
) -> None:
    for event in document.events:
        if isinstance(event, CodeBlock) and _is_python(event.language):
            _lint_python_source(
                event.code,
                mode="exec",
                location=event.location,
                findings=findings,
                skip_random=_has_seed(event),
            )
        elif (
            isinstance(event, ResultAssertion)
            and _is_python(event.language)
            and event.referenced_code_name is None
            and event.compare != "none"
        ):
            _lint_python_source(
                event.code,
                mode="eval",
                location=event.location,
                findings=findings,
                skip_random=_has_seed(event),
            )


def _lint_python_source(
    source: str,
    mode: Literal["exec", "eval"],
    location: SourceLocation,
    findings: list[LintFinding],
    *,
    skip_random: bool,
) -> None:
    try:
        tree = ast.parse(source, mode=mode)
    except SyntaxError as exc:
        findings.append(
            LintFinding(
                level="error",
                code="python-syntax-error",
                location=location,
                message=f"python syntax error: {exc.msg}",
            )
        )
        return

    visitor = _FragilityVisitor(skip_random=skip_random)
    visitor.visit(tree)
    for message in visitor.messages:
        findings.append(
            LintFinding(
                level="warning",
                code="fragile-python",
                location=location,
                message=message,
            )
        )


class _FragilityVisitor(ast.NodeVisitor):
    def __init__(self, *, skip_random: bool) -> None:
        self.skip_random = skip_random
        self.messages: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = _qualified_name(node.func)
        if name is not None:
            self._check_call(name)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        name = _qualified_name(node.value)
        if name in {"os.environ"}:
            self._add_once("reads environment variables through os.environ")
        self.generic_visit(node)

    def _check_call(self, name: str) -> None:
        if not self.skip_random and _is_random_call(name):
            self._add_once(
                "uses random values without an explicit seed attribute nearby"
            )
        if name in {"time.time", "time.monotonic", "time.perf_counter"}:
            self._add_once("uses wall-clock or process-clock time")
        if name in {"datetime.datetime.now", "datetime.datetime.utcnow"}:
            self._add_once("uses current datetime")
        if name in {"datetime.date.today"}:
            self._add_once("uses current date")
        if name in {"requests.get", "requests.post", "urllib.request.urlopen"}:
            self._add_once("uses a network call during verification")

    def _add_once(self, message: str) -> None:
        if message not in self.messages:
            self.messages.append(message)


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        if parent is None:
            return node.attr
        return f"{parent}.{node.attr}"
    return None


def _is_random_call(name: str) -> bool:
    return name in {
        "random",
        "randint",
        "randrange",
        "uniform",
        "choice",
        "choices",
        "shuffle",
        "sample",
        "random.random",
        "random.randint",
        "random.randrange",
        "random.uniform",
        "random.choice",
        "random.choices",
        "random.shuffle",
        "random.sample",
        "np.random.random",
        "np.random.randint",
        "np.random.choice",
        "numpy.random.random",
        "numpy.random.randint",
        "numpy.random.choice",
    }


def _has_justification(event: ResultAssertion) -> bool:
    return bool(
        event.attributes.get("data-reason", "").strip()
        or event.attributes.get("data-justification", "").strip()
    )


def _has_seed(event: CodeBlock | ResultAssertion) -> bool:
    return bool(
        event.attributes.get("seed", "").strip()
        or event.attributes.get("data-seed", "").strip()
    )


def _is_python(language: str) -> bool:
    return language.strip().lower() in {"python", "py"}
