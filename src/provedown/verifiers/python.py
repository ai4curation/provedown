"""Built-in verifier for Python result assertions."""

from __future__ import annotations

import ast
import contextlib
import os
import random
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import CodeType
from typing import Any

from provedown.model import (
    CodeBlock,
    CodeUse,
    Document,
    ResultAssertion,
    SourceLocation,
)
from provedown.report import Finding, Status
from provedown.verifiers import VerificationContext

PYTHON_LANGUAGE_NAMES = {"python", "py"}
VERIFIER_ID = "python-results"


@dataclass
class PythonResultVerifier:
    """Execute Python cells and verify scalar result spans."""

    verifier_id: str = VERIFIER_ID
    namespace: dict[str, Any] = field(default_factory=dict)

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        if context.sandbox == "uv":
            from provedown.verifiers.python_uv import UVPythonRunner

            return UVPythonRunner(document=document, context=context).verify()
        if context.sandbox is not None:
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=_document_location(document),
                    message=f"unknown Python sandbox mode: {context.sandbox}",
                )
            ]
        runner = _PythonRunner(document=document, context=context)
        return runner.verify()


@dataclass
class _PythonRunner:
    document: Document
    context: VerificationContext
    namespace: dict[str, Any] = field(default_factory=dict)
    executed_referenced_names: set[str] = field(default_factory=set)

    def verify(self) -> list[Finding]:
        findings: list[Finding] = []
        deferred_names = self._deferred_code_names()
        with _working_directory(self._execution_cwd()):
            self.namespace["__name__"] = "__provedown__"
            if self.document.path is not None:
                self.namespace["__file__"] = str(self.document.path)
            for event in self.document.events:
                if isinstance(event, CodeBlock):
                    if event.name in deferred_names:
                        continue
                    findings.extend(self._execute_code_block(event))
                elif isinstance(event, CodeUse):
                    findings.extend(self._execute_code_use(event))
                elif isinstance(event, ResultAssertion):
                    finding = self._verify_result(event)
                    if finding is not None:
                        findings.append(finding)
        return findings

    def _execute_code_use(self, event: CodeUse) -> list[Finding]:
        block = self.document.named_code.get(event.name)
        if block is None:
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=event.location,
                    message=f"unknown code block reference: {event.name}",
                )
            ]
        self.executed_referenced_names.add(event.name)
        return self._execute_code_block(block, execution_location=event)

    def _execute_code_block(
        self,
        block: CodeBlock,
        execution_location: CodeUse | None = None,
    ) -> list[Finding]:
        if not _is_python(block.language):
            return []
        location = execution_location.location if execution_location else block.location
        try:
            code = compile(block.code, location.display(), "exec")
            exec(code, self.namespace)
        except Exception as exc:
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=location,
                    message=f"python cell raised {type(exc).__name__}: {exc}",
                    evidence={"code": block.code},
                )
            ]
        return []

    def _verify_result(self, result: ResultAssertion) -> Finding | None:
        if not _is_python(result.language):
            return None

        expression = result.code
        ref_name = result.referenced_code_name
        if ref_name is not None:
            referenced = self.document.named_code.get(ref_name)
            if referenced is None:
                return Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=result.location,
                    message=f"unknown result code reference: {ref_name}",
                    expected=result.authored,
                )
            if not _is_python(referenced.language):
                return Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.SKIP,
                    location=result.location,
                    message=(
                        "python verifier does not handle referenced language "
                        f"{referenced.language!r}"
                    ),
                    expected=result.authored,
                )
            expression = referenced.code

        if result.compare == "none":
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.SKIP,
                location=result.location,
                message="assertion explicitly marked as not verified",
                expected=result.authored,
                evidence={"code": expression, "compare": result.compare},
            )

        seed = _seed_value(result.attributes)
        if seed is not None:
            _seed_random_generators(seed, self.namespace)

        try:
            actual = self._evaluate_expression(expression, result.location.display())
        except Exception as exc:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=f"python result raised {type(exc).__name__}: {exc}",
                expected=result.authored,
                evidence={"code": expression},
            )

        comparison = self.context.comparators.compare(
            result.compare,
            result.authored,
            actual,
            result.attributes,
        )
        return Finding(
            verifier_id=VERIFIER_ID,
            status=comparison.status,
            location=result.location,
            message=comparison.message,
            expected=comparison.expected,
            actual=comparison.actual,
            evidence={"code": expression, "compare": result.compare},
        )

    def _evaluate_expression(self, expression: str, filename: str) -> Any:
        parsed = ast.parse(expression, mode="eval")
        code: CodeType = compile(parsed, filename, "eval")
        return eval(code, self.namespace)

    def _execution_cwd(self) -> Path:
        if self.context.cwd is not None:
            return self.context.cwd
        if self.document.path is not None:
            return self.document.path.parent
        return Path.cwd()

    def _deferred_code_names(self) -> set[str]:
        return _deferred_code_names(self.document)


@contextlib.contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _is_python(language: str) -> bool:
    return language.strip().lower() in PYTHON_LANGUAGE_NAMES


def _deferred_code_names(document: Document) -> set[str]:
    names: set[str] = set()
    for event in document.events:
        if isinstance(event, CodeUse):
            names.add(event.name)
        elif isinstance(event, ResultAssertion):
            ref_name = event.referenced_code_name
            if ref_name is not None:
                names.add(ref_name)
    return names


def _document_location(document: Document) -> SourceLocation:
    return SourceLocation(path=document.path, line=1, column=1)


def _seed_value(attributes: Mapping[str, str]) -> int | None:
    value = attributes.get("seed") or attributes.get("data-seed")
    if value is None or not value.strip():
        return None
    return int(value)


def _seed_random_generators(seed: int, namespace: Mapping[str, Any]) -> None:
    random.seed(seed)
    numpy = namespace.get("np")
    if numpy is not None and hasattr(numpy, "random"):
        numpy.random.seed(seed)
