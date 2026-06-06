from collections.abc import Iterable
from pathlib import Path

from pytest import CaptureFixture

from provedown import Document, Finding, Status, VerificationContext, VerifierRegistry
from provedown.cli import main
from provedown.model import SourceLocation


class AlwaysPassVerifier:
    verifier_id = "always-pass"

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        del context
        yield Finding(
            verifier_id=self.verifier_id,
            status=Status.PASS,
            location=SourceLocation(path=document.path, line=1, column=1),
            message="custom verifier ran",
        )


def test_verifier_registry_runs_custom_verifier() -> None:
    registry = VerifierRegistry()
    registry.register(AlwaysPassVerifier())
    document = Document(source="", path=None, events=[], named_code={})

    report = registry.verify(document)

    assert report.ok
    assert report.count(Status.PASS) == 1
    assert report.findings[0].verifier_id == "always-pass"


def test_cli_verify_text_output(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code>x = 42</code>
Answer: <span class="result" data-code="x">42<span class="method"></span></span>
""".strip(),
        encoding="utf-8",
    )

    exit_code = main(["verify", str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "ok" in captured.out
    assert "[pass] python-results" in captured.out


def test_cli_verify_json_output_fails_on_mismatch(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code>x = 42</code>
Answer: <span class="result" data-code="x">41<span class="method"></span></span>
""".strip(),
        encoding="utf-8",
    )

    exit_code = main(["verify", "--format", "json", str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert '"ok": false' in captured.out
    assert '"status": "fail"' in captured.out
