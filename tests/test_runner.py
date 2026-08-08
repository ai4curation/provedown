from collections.abc import Iterable
from pathlib import Path

from pytest import MonkeyPatch

from provedown import (
    Document,
    Finding,
    VerificationContext,
    VerifierRegistry,
    inspect_document,
    lint_document,
    parse_document,
    verify_document,
    verify_file,
)
from provedown.verifiers.python_uv import UVPythonRunner


class UnexpectedVerifier:
    verifier_id = "unexpected"

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        del document, context
        raise AssertionError("verifier ran after a parser error")


def test_parser_errors_prevent_custom_verifier_execution() -> None:
    registry = VerifierRegistry()
    registry.register(UnexpectedVerifier())
    document = Document(
        source="",
        path=Path("report.md"),
        events=[],
        named_code={},
        diagnostics=["report.md:1:1: malformed document"],
    )

    report = verify_document(document, registry=registry)

    assert not report.ok
    assert report.summary() == {"pass": 0, "fail": 0, "skip": 0, "error": 1}
    assert report.findings[0].verifier_id == "parser"


def test_parser_errors_block_python_side_effects(tmp_path: Path) -> None:
    marker = tmp_path / "python-ran.txt"
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code>
from pathlib import Path
Path("python-ran.txt").write_text("ran", encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )

    report = verify_file(report_path, verifier_ids=["python-results"])

    assert not report.ok
    assert [finding.verifier_id for finding in report.findings] == ["parser"]
    assert not marker.exists()


def test_parser_errors_block_sql_side_effects(tmp_path: Path) -> None:
    marker = tmp_path / "sql-ran.csv"
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code data-language="sql">
copy (select 1 as value) to 'sql-ran.csv' (format csv, header);
</code>
<span class="result" data-language="sql">malformed</span>
""".strip(),
        encoding="utf-8",
    )

    report = verify_file(report_path, verifier_ids=["sql-results"])

    assert not report.ok
    assert [finding.verifier_id for finding in report.findings] == ["parser"]
    assert not marker.exists()


def test_parser_errors_block_uv_sandbox_setup(monkeypatch: MonkeyPatch) -> None:
    def unexpected_verify(runner: UVPythonRunner) -> list[Finding]:
        del runner
        raise AssertionError("uv sandbox ran after a parser error")

    monkeypatch.setattr(UVPythonRunner, "verify", unexpected_verify)
    document = parse_document("<code>x = 42")

    report = verify_document(
        document,
        context=VerificationContext(sandbox="uv"),
        verifier_ids=["python-results"],
    )

    assert not report.ok
    assert [finding.verifier_id for finding in report.findings] == ["parser"]


def test_static_inspection_and_lint_continue_after_parser_errors() -> None:
    document = parse_document("<code>x = 42")

    inspection = inspect_document(document)
    lint = lint_document(document)

    assert len(inspection.events) == 1
    assert [issue.kind for issue in inspection.issues] == ["parser-diagnostic"]
    assert "parser-diagnostic" in {finding.code for finding in lint.findings}
