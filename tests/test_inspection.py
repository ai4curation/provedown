from pathlib import Path

from pytest import CaptureFixture

from provedown import inspect_document, parse_document
from provedown.cli import main


def test_inspection_reports_code_use_and_result_references() -> None:
    document = parse_document(
        "\n".join(
            [
                '<code name="load">x = 42</code>',
                '<code use="load"/>',
                'The answer is <span class="result" data-code="#answer">42'
                '<span class="method"></span></span>.',
                '<code name="answer">x</code>',
            ]
        ),
        path=Path("report.md"),
    )

    report = inspect_document(document)

    assert report.ok
    assert report.summary() == {"events": 4, "errors": 0, "warnings": 0}
    assert [event.kind for event in report.events] == [
        "code",
        "code-use",
        "result",
        "code",
    ]
    assert report.events[0].execution == "deferred"
    assert report.events[1].target_location is not None
    assert report.events[2].reference == "answer"
    assert report.events[2].target_location is not None
    assert report.events[3].execution == "deferred"


def test_inspection_reports_unresolved_references_and_unused_names() -> None:
    document = parse_document(
        "\n".join(
            [
                '<code name="unused">x = 42</code>',
                '<code use="missing"/>',
                'The answer is <span class="result" '
                'data-code="#missing-result">42'
                '<span class="method"></span></span>.',
            ]
        ),
        path=Path("report.md"),
    )

    report = inspect_document(document)

    assert not report.ok
    assert report.summary() == {"events": 3, "errors": 2, "warnings": 1}
    assert [issue.kind for issue in report.issues] == [
        "unresolved-code-use",
        "unresolved-result-reference",
        "unused-named-code",
    ]


def test_cli_inspect_json_output(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code>x = 42</code>
Answer: <span class="result" data-code="x">42<span class="method"></span></span>
""".strip(),
        encoding="utf-8",
    )

    exit_code = main(["inspect", "--format", "json", str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"kind": "code"' in captured.out
    assert '"kind": "result"' in captured.out
    assert '"ok": true' in captured.out


def test_cli_inspect_exits_nonzero_for_unresolved_reference(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text('<code use="missing"/>', encoding="utf-8")

    exit_code = main(["inspect", str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "unresolved-code-use" in captured.out
