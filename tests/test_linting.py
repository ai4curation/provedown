from pathlib import Path

from pytest import CaptureFixture

from provedown import lint_document, parse_document
from provedown.cli import main


def test_lint_warns_on_unjustified_none_comparison() -> None:
    document = parse_document(
        'Value: <span class="result" data-code="status()" '
        'data-compare="none">unknown<span class="method"></span></span>'
    )

    report = lint_document(document)

    assert report.ok
    assert report.summary() == {"errors": 0, "warnings": 1}
    assert report.findings[0].code == "unjustified-none-compare"


def test_lint_accepts_justified_none_comparison() -> None:
    document = parse_document(
        'Value: <span class="result" data-code="status()" '
        'data-compare="none" data-reason="external API">unknown'
        '<span class="method"></span></span>'
    )

    report = lint_document(document)

    assert report.ok
    assert report.findings == []


def test_lint_reports_relationship_errors_and_unused_names() -> None:
    document = parse_document(
        "\n".join(
            [
                '<code name="unused">x = 42</code>',
                '<code use="missing"/>',
            ]
        ),
        path=Path("report.md"),
    )

    report = lint_document(document)

    assert not report.ok
    assert report.summary() == {"errors": 1, "warnings": 1}
    assert [finding.code for finding in report.findings] == [
        "unresolved-code-use",
        "unused-named-code",
    ]


def test_lint_warns_on_fragile_python_sources() -> None:
    document = parse_document(
        """
<code>
import random
import time

draw = random.randint(1, 10)
stamp = time.time()
</code>
""".strip()
    )

    report = lint_document(document)

    assert report.ok
    assert report.summary() == {"errors": 0, "warnings": 2}
    assert [finding.message for finding in report.findings] == [
        "uses random values without an explicit seed attribute nearby",
        "uses wall-clock or process-clock time",
    ]


def test_lint_respects_seeded_result_expression() -> None:
    document = parse_document(
        "\n".join(
            [
                "<code>import random</code>",
                'Draw: <span class="result" data-code="random.randint(1, 10)" '
                'seed="7">6<span class="method"></span></span>',
            ]
        )
    )

    report = lint_document(document)

    assert report.ok
    assert report.findings == []


def test_cli_lint_json_output(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(
        '<code name="unused">x = 42</code>',
        encoding="utf-8",
    )

    exit_code = main(["lint", "--format", "json", str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"code": "unused-named-code"' in captured.out
    assert '"warnings": 1' in captured.out


def test_cli_lint_exits_nonzero_for_errors(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text('<code use="missing"/>', encoding="utf-8")

    exit_code = main(["lint", str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "unresolved-code-use" in captured.out
