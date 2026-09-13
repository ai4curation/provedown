import shutil
from pathlib import Path

import pytest

from provedown import (
    Status,
    VerificationContext,
    parse_document,
    verify_document,
    verify_file,
)
from provedown.verifiers.lean import (
    _VALUE_BEGIN,
    _VALUE_END,
    _extract_value,
    _split_imports,
    _summarize,
)

LEAN_AVAILABLE = shutil.which("lean") is not None
requires_lean = pytest.mark.skipif(
    not LEAN_AVAILABLE,
    reason="lean is required for Lean verifier integration",
)


def test_lean_verifier_ignores_documents_without_lean_events() -> None:
    document = parse_document(
        """
<code>
value = 42
</code>
Answer: <span class="result" data-code="value">42<span class="method"></span></span>
""".strip()
    )

    report = verify_document(document)

    assert report.ok
    assert {finding.verifier_id for finding in report.findings} == {"python-results"}


def test_split_imports_hoists_import_lines() -> None:
    imports, body = _split_imports("def a : Nat := 1\nimport Lean\ndef b : Nat := 2")

    assert imports == ["import Lean"]
    assert body == "def a : Nat := 1\ndef b : Nat := 2"


def test_split_imports_leaves_non_import_lines_alone() -> None:
    imports, body = _split_imports("  import Lean\ndef a : Nat := 1")

    assert imports == []
    assert body == "  import Lean\ndef a : Nat := 1"


def test_extract_value_ignores_surrounding_diagnostics() -> None:
    """Lean emits warnings on stdout even when the run succeeds."""
    output = "\n".join(
        [
            "report.lean:1:8: warning: declaration uses 'sorry'",
            _VALUE_BEGIN,
            "195",
            _VALUE_END,
        ]
    )

    assert _extract_value(output) == "195"


def test_extract_value_preserves_multiline_values() -> None:
    output = "\n".join([_VALUE_BEGIN, "line one", "line two", _VALUE_END])

    assert _extract_value(output) == "line one\nline two"


def test_extract_value_returns_none_without_sentinels() -> None:
    assert _extract_value("195") is None
    assert _extract_value(f"{_VALUE_BEGIN}\n195") is None


def test_summarize_reports_first_line_and_remaining_count() -> None:
    assert _summarize("") == "no diagnostic output"
    assert _summarize("only line") == "only line"
    assert _summarize("first\nsecond\nthird") == "first (2 more line(s))"


def test_lean_verifier_rejects_sandbox_mode() -> None:
    document = parse_document(
        """
Answer:
<span class="result" data-language="lean" data-code="1 + 1">2</span>
""".strip()
    )

    report = verify_document(document, context=VerificationContext(sandbox="uv"))

    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert len(findings) == 1
    assert findings[0].status == Status.ERROR
    assert "does not support sandbox mode" in findings[0].message


def test_lean_verifier_skips_compare_none_without_toolchain() -> None:
    """`compare="none"` is resolved before any Lean process is started."""
    document = parse_document(
        """
Answer:
<span
  class="result"
  data-language="lean"
  data-code="1 + 1"
  data-compare="none"
>2</span>
""".strip()
    )

    report = verify_document(document)

    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert len(findings) == 1
    if LEAN_AVAILABLE:
        assert findings[0].status == Status.SKIP
        assert "explicitly marked as not verified" in findings[0].message


@requires_lean
def test_lean_verifier_passes_inline_scalar_results() -> None:
    document = parse_document(
        """
<code data-language="lean">
def fib : Nat -> Nat
  | 0 => 0
  | 1 => 1
  | n + 2 => fib n + fib (n + 1)
</code>

The thirtieth Fibonacci number is
<span
  class="result"
  data-language="lean"
  data-code="fib 30"
>832040<span class="method"></span></span>.
""".strip()
    )

    report = verify_document(document)

    assert report.ok
    assert report.summary() == {"pass": 1, "fail": 0, "skip": 0, "error": 0}
    assert {finding.verifier_id for finding in report.findings} == {"lean-results"}


@requires_lean
def test_lean_verifier_reports_mismatch() -> None:
    document = parse_document(
        """
<code data-language="lean">
def total : Nat := 120 + 75
</code>
Answer:
<span class="result" data-language="lean" data-code="total">194</span>
""".strip()
    )

    report = verify_document(document)

    assert not report.ok
    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert len(findings) == 1
    assert findings[0].status == Status.FAIL
    assert findings[0].expected == "194"
    assert findings[0].actual == "195"


@requires_lean
def test_lean_verifier_uses_tostring_semantics_for_strings() -> None:
    """`#eval` would render this as `"hi there"`; prose wants `hi there`."""
    document = parse_document(
        """
Answer:
<span
  class="result"
  data-language="lean"
  data-code="String.append &quot;hi &quot; &quot;there&quot;"
>hi there</span>
""".strip()
    )

    report = verify_document(document)

    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert len(findings) == 1
    assert findings[0].status == Status.PASS
    assert findings[0].actual == "hi there"


@requires_lean
def test_lean_verifier_hoists_imports_from_later_cells() -> None:
    document = parse_document(
        """
<code data-language="lean">
def base : Nat := 1
</code>
<code data-language="lean">
import Lean
def derived : Nat := base + 1
</code>
Answer:
<span class="result" data-language="lean" data-code="derived">2</span>
""".strip()
    )

    report = verify_document(document)

    assert report.ok, [f.message for f in report.findings]
    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert [f.status for f in findings] == [Status.PASS]


@requires_lean
def test_lean_verifier_reports_elaboration_error_at_the_failing_cell() -> None:
    document = parse_document(
        """
<code data-language="lean">
def broken : Nat := "not a number"
</code>
Answer:
<span class="result" data-language="lean" data-code="broken">1</span>
""".strip()
    )

    report = verify_document(document)

    assert not report.ok
    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert [f.status for f in findings] == [Status.ERROR, Status.ERROR]
    assert "failed to elaborate" in findings[0].message
    assert "preceding lean cell failed" in findings[1].message


@requires_lean
def test_lean_verifier_flags_sorry_as_incomplete_evidence() -> None:
    document = parse_document(
        """
<code data-language="lean">
theorem always : 1 = 1 := by sorry
def total : Nat := 2
</code>
Answer:
<span class="result" data-language="lean" data-code="total">2</span>
""".strip()
    )

    report = verify_document(document)

    assert not report.ok
    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert findings[0].status == Status.FAIL
    assert "sorry" in findings[0].message
    # The claim itself still verifies; only the evidence is flagged.
    assert findings[1].status == Status.PASS


@requires_lean
def test_lean_verifier_falls_back_to_repr_without_tostring_instance() -> None:
    document = parse_document(
        """
<code data-language="lean">
structure Point where
  x : Nat
  y : Nat
deriving Repr
</code>
Answer:
<span
  class="result"
  data-language="lean"
  data-code="({ x := 1, y := 2 } : Point)"
>{ x := 1, y := 2 }</span>
""".strip()
    )

    report = verify_document(document)

    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert len(findings) == 1
    assert findings[0].status == Status.PASS, findings[0].message


@requires_lean
def test_lean_verifier_detects_main_collision() -> None:
    document = parse_document(
        """
<code data-language="lean">
def main : IO Unit := IO.println "user entry point"
</code>
Answer:
<span class="result" data-language="lean" data-code="1 + 1">2</span>
""".strip()
    )

    report = verify_document(document)

    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert findings[-1].status == Status.ERROR
    assert "collides with the entry point" in findings[-1].message


@requires_lean
def test_lean_verifier_supports_named_code_forward_reference() -> None:
    document = parse_document(
        """
<code name="cohort-size" data-language="lean">
List.length [1, 2, 3, 4]
</code>
The cohort has
<span
  class="result"
  data-language="lean"
  data-code="#cohort-size"
>4<span class="method"></span></span>
samples.
""".strip()
    )

    report = verify_document(document)

    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert len(findings) == 1
    assert findings[0].status == Status.PASS, findings[0].message


@requires_lean
def test_lean_verifier_honours_numeric_comparison() -> None:
    document = parse_document(
        """
Answer:
<span
  class="result"
  data-language="lean"
  data-code="(2 : Nat) + 2"
  data-compare="numeric"
>4.0</span>
""".strip()
    )

    report = verify_document(document)

    findings = [f for f in report.findings if f.verifier_id == "lean-results"]
    assert findings[0].status == Status.PASS


@requires_lean
def test_lean_verifier_mixes_with_python_in_one_document(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code data-language="lean">
def leanTotal : Nat := 195
</code>
<code>
python_total = 195
</code>
Lean says
<span class="result" data-language="lean" data-code="leanTotal">195</span>
and Python agrees:
<span class="result" data-code="python_total">195</span>.
""".strip(),
        encoding="utf-8",
    )

    report = verify_file(report_path)

    assert report.ok, [f.message for f in report.findings]
    assert {f.verifier_id for f in report.findings} == {
        "lean-results",
        "python-results",
    }
