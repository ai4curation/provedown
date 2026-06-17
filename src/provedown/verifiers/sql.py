"""Built-in verifier for SQL result assertions."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from provedown.model import CodeBlock, CodeUse, Document, ResultAssertion
from provedown.report import Finding, Status
from provedown.verifiers import VerificationContext

SQL_LANGUAGE_NAMES = {"sql", "duckdb", "duckdb-sql"}
VERIFIER_ID = "sql-results"


@dataclass
class SQLResultVerifier:
    """Execute DuckDB SQL cells and verify scalar result spans."""

    verifier_id: str = VERIFIER_ID

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        runner = _SQLRunner(document=document, context=context)
        return runner.verify()


@dataclass
class _SQLRunner:
    document: Document
    context: VerificationContext
    connection: Any = field(init=False)

    def verify(self) -> list[Finding]:
        findings: list[Finding] = []
        deferred_names = self._deferred_code_names()
        with _working_directory(self._execution_cwd()):
            self.connection = duckdb.connect(database=":memory:")
            try:
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
            finally:
                self.connection.close()
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
        return self._execute_code_block(block, execution_location=event)

    def _execute_code_block(
        self,
        block: CodeBlock,
        execution_location: CodeUse | None = None,
    ) -> list[Finding]:
        if not _is_sql(block.language):
            return []
        location = execution_location.location if execution_location else block.location
        try:
            self.connection.execute(block.code)
        except Exception as exc:
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=location,
                    message=f"sql cell raised {type(exc).__name__}: {exc}",
                    evidence={"code": block.code},
                )
            ]
        return []

    def _verify_result(self, result: ResultAssertion) -> Finding | None:
        if not _is_sql(result.language):
            return None

        query = result.code
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
            if not _is_sql(referenced.language):
                return Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.SKIP,
                    location=result.location,
                    message=(
                        "sql verifier does not handle referenced language "
                        f"{referenced.language!r}"
                    ),
                    expected=result.authored,
                )
            query = referenced.code

        if result.compare == "none":
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.SKIP,
                location=result.location,
                message="assertion explicitly marked as not verified",
                expected=result.authored,
                evidence={"code": query, "compare": result.compare},
            )

        try:
            actual = self._evaluate_query(query)
        except Exception as exc:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=f"sql result raised {type(exc).__name__}: {exc}",
                expected=result.authored,
                evidence={"code": query},
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
            evidence={"code": query, "compare": result.compare},
        )

    def _evaluate_query(self, query: str) -> Any:
        cursor = self.connection.execute(query)
        rows = cursor.fetchall()
        description = cursor.description or []
        column_count = len(description)
        if not rows:
            return ""
        if column_count == 1:
            values = [row[0] for row in rows]
            return values[0] if len(values) == 1 else values
        return rows[0] if len(rows) == 1 else rows

    def _execution_cwd(self) -> Path:
        if self.context.cwd is not None:
            return self.context.cwd
        if self.document.path is not None:
            return self.document.path.parent
        return Path.cwd()

    def _deferred_code_names(self) -> set[str]:
        names: set[str] = set()
        for event in self.document.events:
            if isinstance(event, CodeUse):
                names.add(event.name)
            elif isinstance(event, ResultAssertion):
                ref_name = event.referenced_code_name
                if ref_name is not None:
                    names.add(ref_name)
        return names


@contextlib.contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _is_sql(language: str) -> bool:
    return language.strip().lower() in SQL_LANGUAGE_NAMES
