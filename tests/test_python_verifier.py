from pathlib import Path

from provedown import Status, parse_document, verify_document, verify_file


def test_python_verifier_passes_inline_result() -> None:
    document = parse_document(
        """
<code>
x = 40 + 2
</code>
Answer: <span class="result" data-code="x">42<span class="method"></span></span>
""".strip()
    )

    report = verify_document(document)

    assert report.ok
    assert report.summary() == {"pass": 1, "fail": 0, "skip": 0, "error": 0}
    assert report.findings[0].actual == "42"


def test_python_verifier_reports_mismatch() -> None:
    document = parse_document(
        """
<code>x = 42</code>
Answer: <span class="result" data-code="x">41<span class="method"></span></span>
""".strip()
    )

    report = verify_document(document)

    assert not report.ok
    assert report.count(Status.FAIL) == 1
    assert report.findings[0].expected == "41"
    assert report.findings[0].actual == "42"


def test_named_code_used_by_result_is_evaluated_at_result_site() -> None:
    document = parse_document(
        "<code>x = 40 + 2</code>\n"
        'The answer is <span class="result" data-code="#answer">42'
        '<span class="method"></span></span>.\n'
        '<code name="answer">x</code>'
    )

    report = verify_document(document)

    assert report.ok
    assert report.count(Status.PASS) == 1


def test_forward_reference_definition_executes_at_use_site() -> None:
    document = parse_document(
        """
<code name="load">x = 40 + 2</code>
<code use="load"/>
The answer is <span class="result" data-code="x">42<span class="method"></span></span>.
""".strip()
    )

    report = verify_document(document)

    assert report.ok


def test_numeric_tolerance_and_set_comparisons() -> None:
    document = parse_document(
        "<code>\n"
        "value = 42.0\n"
        "ratio = 0.3333333333\n"
        'items = ["b", "a"]\n'
        "</code>\n"
        'Numeric: <span class="result" data-code="value" '
        'data-compare="numeric">42'
        '<span class="method"></span></span>\n'
        'Tolerance: <span class="result" data-code="ratio" '
        'tol="1e-6">0.333333'
        '<span class="method"></span></span>\n'
        'Set: <span class="result" data-code="items" '
        'data-compare="set">a,b'
        '<span class="method"></span></span>'
    )

    report = verify_document(document)

    assert report.ok
    assert report.count(Status.PASS) == 3


def test_none_comparison_skips_without_evaluating_expression() -> None:
    document = parse_document(
        'Unverified: <span class="result" data-code="missing_name" '
        'data-compare="none">unknown'
        '<span class="method"></span></span>'
    )

    report = verify_document(document)

    assert report.ok
    assert report.count(Status.SKIP) == 1
    assert report.findings[0].actual is None


def test_verify_file_runs_relative_to_document_directory(tmp_path: Path) -> None:
    data = tmp_path / "value.txt"
    data.write_text("42\n", encoding="utf-8")
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code>
from pathlib import Path
x = Path("value.txt").read_text(encoding="utf-8").strip()
</code>
Answer: <span class="result" data-code="x">42<span class="method"></span></span>
""".strip(),
        encoding="utf-8",
    )

    report = verify_file(report_path)

    assert report.ok
