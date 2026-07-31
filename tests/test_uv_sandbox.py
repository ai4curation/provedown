import shutil
from pathlib import Path

import pytest
from pytest import CaptureFixture

from provedown import Status, VerificationContext, parse_document, verify_document
from provedown.cli import main
from provedown.verifiers.python_uv import UVPythonRunner

UV_AVAILABLE = shutil.which("uv") is not None


@pytest.mark.skipif(not UV_AVAILABLE, reason="uv is required for sandbox integration")
def test_cli_uv_sandbox_verifies_document_relative_file(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    (tmp_path / "value.txt").write_text("42\n", encoding="utf-8")
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
---
provedown:
  environments:
    python:
      requires-python: ">=3.10"
---
<code>
from pathlib import Path
value = Path("value.txt").read_text(encoding="utf-8").strip()
</code>
Answer: <span class="result" data-code="value">42<span class="method"></span></span>
""".strip(),
        encoding="utf-8",
    )

    exit_code = main(["verify", "--sandbox", "uv", str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "[pass] python-results" in captured.out


@pytest.mark.skipif(not UV_AVAILABLE, reason="uv is required for sandbox integration")
def test_uv_sandbox_does_not_inherit_host_packages(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code>
import yaml
</code>
Answer: <span class="result" data-code="1 + 1">2</span>
""".strip(),
        encoding="utf-8",
    )

    document = parse_document(report_path.read_text(encoding="utf-8"), report_path)
    report = verify_document(
        document,
        context=VerificationContext(cwd=tmp_path, sandbox="uv"),
        verifier_ids=["python-results"],
    )

    assert not report.ok
    assert report.count(Status.ERROR) == 1
    assert "ModuleNotFoundError" in report.findings[0].message


def test_uv_sandbox_command_uses_python_environment_metadata(tmp_path: Path) -> None:
    document = parse_document(
        """
---
provedown:
  environments:
    python:
      requires-python: ">=3.11"
      dependencies:
        - pandas>=2
        - pyarrow>=15
---
<code>x = 42</code>
""".strip(),
        path=tmp_path / "report.md",
    )
    runner = UVPythonRunner(
        document=document,
        context=VerificationContext(cwd=tmp_path, sandbox="uv"),
    )

    command = runner._sandbox_command()

    assert isinstance(command, list)
    assert "--isolated" in command
    assert "--no-project" in command
    assert command[command.index("--python") + 1] == ">=3.11"
    assert [
        command[index + 1]
        for index, item in enumerate(command)
        if item == "--with"
    ] == ["pandas>=2", "pyarrow>=15"]


def test_uv_sandbox_reports_invalid_dependency_metadata() -> None:
    document = parse_document(
        """
---
provedown:
  environments:
    python:
      dependencies: pandas
---
<code>x = 42</code>
Answer: <span class="result" data-code="x">42</span>
""".strip()
    )

    report = verify_document(
        document,
        context=VerificationContext(sandbox="uv"),
        verifier_ids=["python-results"],
    )

    assert not report.ok
    assert report.count(Status.ERROR) == 1
    assert "dependencies must be a list" in report.findings[0].message


def test_cli_uv_sandbox_rejects_non_python_verifier(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n", encoding="utf-8")

    exit_code = main(
        [
            "verify",
            "--sandbox",
            "uv",
            "--verifier",
            "sql-results",
            str(report_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "currently supports only" in captured.err


def test_sql_verifier_does_not_ignore_requested_sandbox() -> None:
    document = parse_document(
        """
<code data-language="sql">create table values_table(value integer)</code>
Answer: <span class="result" data-language="sql" data-code="select 42">42</span>
""".strip()
    )

    report = verify_document(
        document,
        context=VerificationContext(sandbox="uv"),
        verifier_ids=["sql-results"],
    )

    assert not report.ok
    assert report.count(Status.ERROR) == 1
    assert "does not support sandbox mode" in report.findings[0].message
