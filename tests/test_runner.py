import json
from collections.abc import Iterable
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from provedown import (
    Document,
    Finding,
    Status,
    VerificationContext,
    VerifierRegistry,
    inspect_document,
    lint_document,
    parse_document,
    verify_document,
    verify_file,
)
from provedown.cli import main
from provedown.model import SourceLocation
from provedown.runner import VERIFICATION_SKIPPED_MESSAGE
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


class RecordingVerifier:
    verifier_id = "recording"

    def __init__(self) -> None:
        self.called = False

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        del context
        self.called = True
        yield Finding(
            verifier_id=self.verifier_id,
            status=Status.PASS,
            location=SourceLocation(path=document.path, line=1, column=1),
            message="custom verifier ran",
        )


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
    assert report.summary() == {"pass": 0, "fail": 0, "skip": 1, "error": 1}
    assert report.findings[0].verifier_id == "parser"
    assert report.findings[-1].message == VERIFICATION_SKIPPED_MESSAGE


def test_diagnostic_free_documents_run_verifiers() -> None:
    verifier = RecordingVerifier()
    registry = VerifierRegistry()
    registry.register(verifier)
    document = parse_document("<code>x = 42</code>")

    report = verify_document(document, registry=registry)

    assert document.diagnostics == []
    assert verifier.called
    assert report.ok
    assert report.summary() == {"pass": 1, "fail": 0, "skip": 0, "error": 0}


def test_all_parser_errors_are_returned_before_verification() -> None:
    document = parse_document('<code name="value">1</code>\n<code name="value">2')

    report = verify_document(document)

    parser_findings = report.findings[:2]
    assert [finding.message for finding in parser_findings] == document.diagnostics
    assert [finding.verifier_id for finding in parser_findings] == ["parser", "parser"]
    assert [finding.status for finding in report.findings] == [
        Status.ERROR,
        Status.ERROR,
        Status.SKIP,
    ]
    assert report.findings[2].message == VERIFICATION_SKIPPED_MESSAGE


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
    assert [finding.status for finding in report.findings] == [
        Status.ERROR,
        Status.SKIP,
    ]
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
    assert [finding.status for finding in report.findings] == [
        Status.ERROR,
        Status.SKIP,
    ]
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
    assert [finding.status for finding in report.findings] == [
        Status.ERROR,
        Status.SKIP,
    ]


def test_cli_json_reports_blocked_verification(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text("<code>x = 42", encoding="utf-8")

    exit_code = main(["verify", "--format", "json", str(report_path)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert captured.err == ""
    assert payload["ok"] is False
    assert len(payload["reports"]) == 1
    report_payload = payload["reports"][0]
    assert report_payload["path"] == str(report_path)
    assert report_payload["ok"] is False
    assert report_payload["summary"] == {
        "error": 1,
        "fail": 0,
        "pass": 0,
        "skip": 1,
    }
    assert [finding["status"] for finding in report_payload["findings"]] == [
        "error",
        "skip",
    ]
    assert report_payload["findings"][0]["verifier_id"] == "parser"
    assert report_payload["findings"][1]["message"] == (
        "verification skipped: document has parser errors"
    )


def test_static_inspection_and_lint_continue_after_parser_errors() -> None:
    document = parse_document("<code>x = 42")

    inspection = inspect_document(document)
    lint = lint_document(document)

    assert len(inspection.events) == 1
    assert [issue.kind for issue in inspection.issues] == ["parser-diagnostic"]
    assert "parser-diagnostic" in {finding.code for finding in lint.findings}
