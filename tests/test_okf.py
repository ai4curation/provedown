from datetime import date
from pathlib import Path

from provedown import (
    Status,
    inspect_document,
    lint_document,
    parse_document,
    verify_document,
    verify_file,
)
from provedown.integrations.okf import (
    TRUST_HUMAN_REVIEWED,
    TRUST_MACHINE_CONFIRMED,
    TRUST_UNVERIFIED,
    parse_okf_document,
    parse_okf_file,
    verify_okf_file,
)

COMPUTATION_DOC = """---
type: Attested Computation
title: Revenue for a fiscal year
runtime: duckdb
parameters:
  - { name: year, type: integer, required: true }
provedown:
  okf:
    bindings:
      fy2025: { year: 2025 }
      fy2026: { year: 2026 }
---

# Computation

```sql
SELECT @year + 1
```

# Examples

FY2025 yields
<span class="result" data-code="#fy2025">2026<span class="method"></span></span>
and FY2026 yields
<span class="result" data-code="#fy2026">2027<span class="method"></span></span>.
"""


def test_okf_frontmatter_survives_the_plain_parser() -> None:
    document = parse_document(COMPUTATION_DOC)

    assert document.diagnostics == []
    assert document.frontmatter["type"] == "Attested Computation"
    assert document.frontmatter["runtime"] == "duckdb"


def test_fenced_computation_is_not_executable_without_the_shim() -> None:
    report = verify_document(parse_document(COMPUTATION_DOC))

    assert not report.ok
    assert report.count(Status.ERROR) == 2
    assert all(
        "unknown result code reference" in finding.message
        for finding in report.findings
    )


def test_shim_lifts_a_fenced_computation_and_binds_parameters() -> None:
    okf = parse_okf_document(COMPUTATION_DOC)

    assert okf.document.diagnostics == []
    assert okf.computation is not None
    assert okf.computation.code == "SELECT @year + 1"
    assert okf.computation.language == "duckdb"
    assert set(okf.bindings) == {"fy2025", "fy2026"}
    assert okf.bindings["fy2025"].code == "SELECT 2025 + 1"

    report = verify_document(okf.document)

    assert report.ok
    assert report.summary() == {"pass": 2, "fail": 0, "skip": 0, "error": 0}


def test_lifted_blocks_are_definitions_not_events() -> None:
    okf = parse_okf_document(COMPUTATION_DOC)

    assert "fy2025" in okf.document.named_code
    assert "fy2026" in okf.document.named_code
    assert [type(event).__name__ for event in okf.document.events] == [
        "ResultAssertion",
        "ResultAssertion",
    ]


def test_unreferenced_template_computation_is_not_registered() -> None:
    okf = parse_okf_document(COMPUTATION_DOC)

    assert okf.computation is not None
    assert "computation" not in okf.document.named_code
    assert lint_document(okf.document).ok
    assert inspect_document(okf.document).issues == []


def test_directly_referenced_computation_is_registered() -> None:
    source = COMPUTATION_DOC.replace(
        "FY2025 yields",
        'Unbound: <span class="result" data-code="#computation">?<span'
        ' class="method"></span></span>. FY2025 yields',
    )

    okf = parse_okf_document(source)

    assert "computation" in okf.document.named_code
    assert okf.document.named_code["computation"].code == "SELECT @year + 1"


def test_unparameterised_computation_is_always_registered() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
---

# Computation

```sql
SELECT 41 + 1
```

Answer:
<span class="result" data-code="#computation">42<span class="method"></span></span>
"""

    okf = parse_okf_document(source)

    assert "computation" in okf.document.named_code
    assert verify_document(okf.document).ok


def test_runtime_sets_the_default_language_for_claims() -> None:
    okf = parse_okf_document(COMPUTATION_DOC)

    assert okf.document.provedown.default_language == "duckdb"
    assert all(event.language == "duckdb" for event in okf.document.events)


def test_explicit_default_language_wins_over_runtime() -> None:
    source = COMPUTATION_DOC.replace(
        "provedown:\n  okf:",
        "provedown:\n  default_language: sql\n  okf:",
    )

    okf = parse_okf_document(source)

    assert okf.document.provedown.default_language == "sql"
    assert all(event.language == "sql" for event in okf.document.events)


def test_element_language_attribute_wins_over_runtime() -> None:
    source = COMPUTATION_DOC.replace(
        '<span class="result" data-code="#fy2025">',
        '<span class="result" data-language="python" data-code="#fy2025">',
    )

    okf = parse_okf_document(source)

    assert [event.language for event in okf.document.events] == ["python", "duckdb"]


def test_mismatched_claim_fails() -> None:
    okf = parse_okf_document(COMPUTATION_DOC.replace(">2026<", ">9999<"))

    report = verify_document(okf.document)

    assert not report.ok
    assert report.count(Status.FAIL) == 1


def test_binding_may_not_supply_an_undeclared_parameter() -> None:
    source = COMPUTATION_DOC.replace(
        "fy2025: { year: 2025 }",
        "fy2025: { year: 2025, quarter: 3 }",
    )

    okf = parse_okf_document(source)

    assert any("does not declare" in item for item in okf.document.diagnostics)
    assert "fy2025" not in okf.bindings
    assert not verify_document(okf.document).ok


def test_binding_must_supply_required_parameters() -> None:
    source = COMPUTATION_DOC.replace("fy2025: { year: 2025 }", "fy2025: {}")

    okf = parse_okf_document(source)

    assert any(
        "missing required parameter" in item for item in okf.document.diagnostics
    )
    assert "fy2025" not in okf.bindings


def test_binding_value_must_match_the_declared_type() -> None:
    source = COMPUTATION_DOC.replace("fy2025: { year: 2025 }", "fy2025: { year: nope }")

    okf = parse_okf_document(source)

    assert any("is not a valid integer" in item for item in okf.document.diagnostics)


PREFIX_DOC = """---
type: Attested Computation
runtime: duckdb
parameters:
  - { name: year, type: integer, required: true }
  - { name: year_end, type: integer, required: true }
provedown:
  okf:
    bindings:
      span: { year: 2025, year_end: 2027 }
---

# Computation

```sql
SELECT @year_end - @year
```

Span:
<span class="result" data-code="#span">2<span class="method"></span></span>
"""


def test_a_shorter_parameter_name_does_not_rewrite_a_longer_one() -> None:
    okf = parse_okf_document(PREFIX_DOC)

    assert okf.document.diagnostics == []
    assert okf.bindings["span"].code == "SELECT 2027 - 2025"
    assert verify_document(okf.document).ok


def test_parameter_names_are_matched_at_a_boundary() -> None:
    source = PREFIX_DOC.replace(
        "SELECT @year_end - @year",
        "SELECT @year_end - @year, 'ops@yearly.example'",
    )

    okf = parse_okf_document(source)

    assert okf.bindings["span"].code == (
        "SELECT 2027 - 2025, 'ops@yearly.example'"
    )


def test_placeholders_inside_sql_string_literals_are_left_alone() -> None:
    source = PREFIX_DOC.replace(
        "SELECT @year_end - @year",
        "SELECT @year_end - @year, '@year'",
    )

    okf = parse_okf_document(source)

    assert okf.bindings["span"].code == "SELECT 2027 - 2025, '@year'"


def test_a_name_only_inside_a_literal_does_not_count_as_referenced() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
parameters:
  - { name: year, type: integer }
  - { name: n, type: integer, required: true }
provedown:
  okf:
    bindings:
      only_n: { n: 1 }
---

# Computation

```sql
SELECT @n, 'filed @year'
```
"""

    okf = parse_okf_document(source)

    assert okf.document.diagnostics == []
    assert okf.bindings["only_n"].code == "SELECT 1, 'filed @year'"


def test_string_parameters_are_quoted_and_escaped() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
parameters:
  - { name: status, type: string, required: true }
provedown:
  okf:
    bindings:
      quoted: { status: "it's delivered" }
---

# Computation

```sql
SELECT @status
```

Value:
<span class="result" data-code="#quoted">it's delivered<span
  class="method"></span></span>
"""

    okf = parse_okf_document(source)

    assert okf.bindings["quoted"].code == "SELECT 'it''s delivered'"
    assert verify_document(okf.document).ok


def test_boolean_parameters_reject_non_boolean_values() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
parameters:
  - { name: flag, type: boolean, required: true }
provedown:
  okf:
    bindings:
      good: { flag: false }
      bad: { flag: nonsense }
---

# Computation

```sql
SELECT @flag
```
"""

    okf = parse_okf_document(source)

    assert okf.bindings["good"].code == "SELECT FALSE"
    assert "bad" not in okf.bindings
    assert any("not a valid boolean" in item for item in okf.document.diagnostics)


def test_integer_parameters_reject_non_integral_values() -> None:
    source = COMPUTATION_DOC.replace(
        "fy2025: { year: 2025 }", "fy2025: { year: 2025.9 }"
    )

    okf = parse_okf_document(source)

    assert any("not a valid integer" in item for item in okf.document.diagnostics)


def test_untyped_parameters_follow_the_value_type() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
parameters:
  - { name: year }
provedown:
  okf:
    bindings:
      y: { year: 2026 }
---

# Computation

```sql
SELECT @year + 1
```

Next:
<span class="result" data-code="#y">2027<span class="method"></span></span>
"""

    okf = parse_okf_document(source)

    assert okf.bindings["y"].code == "SELECT 2026 + 1"
    assert verify_document(okf.document).ok


def test_a_fence_tagged_for_the_runtime_wins() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
---

# Computation

```text
a note, not the computation
```

```sql
SELECT 41 + 1
```

Answer:
<span class="result" data-code="#computation">42<span class="method"></span></span>
"""

    okf = parse_okf_document(source)

    assert okf.computation is not None
    assert okf.computation.code == "SELECT 41 + 1"
    assert verify_document(okf.document).ok


def test_an_untagged_fence_is_used_when_none_matches_the_runtime() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
---

# Computation

```
SELECT 41 + 1
```

Answer:
<span class="result" data-code="#computation">42<span class="method"></span></span>
"""

    okf = parse_okf_document(source)

    assert okf.computation is not None
    assert okf.computation.code == "SELECT 41 + 1"


def test_computation_name_override_renames_the_lifted_block() -> None:
    source = COMPUTATION_DOC.replace(
        "  okf:\n", "  okf:\n    computation_name: sanctioned\n"
    ).replace('data-code="#fy2025"', 'data-code="#sanctioned"')

    okf = parse_okf_document(source)

    assert okf.computation is not None
    assert okf.computation.name == "sanctioned"
    assert "sanctioned" in okf.document.named_code
    assert "computation" not in okf.document.named_code


def test_a_binding_may_not_take_the_computation_name() -> None:
    source = COMPUTATION_DOC.replace(
        "fy2025: { year: 2025 }", "computation: { year: 2025 }"
    )

    okf = parse_okf_document(source)

    assert "computation" not in okf.bindings
    assert any("collides with" in item for item in okf.document.diagnostics)


def test_unrunnable_runtime_is_reported_rather_than_guessed() -> None:
    source = COMPUTATION_DOC.replace("runtime: duckdb", "runtime: bigquery")

    okf = parse_okf_document(source)
    report = verify_document(okf.document)

    assert okf.computation is None
    assert any("bigquery" in item for item in okf.document.diagnostics)
    assert not report.ok


def test_runtime_language_override_enables_an_unmapped_runtime() -> None:
    source = COMPUTATION_DOC.replace("runtime: duckdb", "runtime: bigquery").replace(
        "  okf:\n", "  okf:\n    runtime_language: duckdb\n"
    )

    okf = parse_okf_document(source)

    assert okf.document.diagnostics == []
    assert verify_document(okf.document).ok


def test_missing_computation_is_reported() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
---

# Examples

Nothing to run here.
"""

    okf = parse_okf_document(source)

    assert okf.computation is None
    assert any("no computation" in item for item in okf.document.diagnostics)


def test_computation_name_collision_is_reported() -> None:
    source = COMPUTATION_DOC.replace(
        "# Examples",
        '# Examples\n\n<pre><code name="computation">SELECT 1</code></pre>',
    )

    okf = parse_okf_document(source)

    assert okf.computation is None
    assert any("already defines" in item for item in okf.document.diagnostics)


def test_heading_inside_a_fence_is_not_the_computation_section() -> None:
    source = """---
type: Attested Computation
runtime: duckdb
---

````markdown
# Computation

```sql
SELECT 'documentation example'
```
````

# Computation

```sql
SELECT 41 + 1
```

Answer:
<span class="result" data-code="#computation">42<span class="method"></span></span>
"""

    okf = parse_okf_document(source)

    assert okf.computation is not None
    assert okf.computation.code == "SELECT 41 + 1"
    assert verify_document(okf.document).ok


def test_python_runtime_computation_runs_through_a_code_use() -> None:
    source = """---
type: Attested Computation
runtime: python
parameters:
  - { name: rate, type: number, required: true }
provedown:
  okf:
    bindings:
      standard: { rate: 0.2 }
---

# Computation

```python
margin = round(1000 * @rate, 2)
```

<code use="standard"/>

Margin is
<span class="result" data-code="margin">200.0<span class="method"></span></span>.
"""

    okf = parse_okf_document(source)

    assert okf.bindings["standard"].code == "margin = round(1000 * 0.2, 2)"
    assert verify_document(okf.document).ok


def test_external_computation_file_is_lifted(tmp_path: Path) -> None:
    (tmp_path / "revenue.sql").write_text("SELECT 41 + 1\n", encoding="utf-8")
    document = tmp_path / "revenue.md"
    document.write_text(
        """---
type: Attested Computation
runtime: duckdb
computation: revenue.sql
---

Answer:
<span class="result" data-code="#computation">42<span class="method"></span></span>
""",
        encoding="utf-8",
    )

    okf = parse_okf_file(document)

    assert okf.computation is not None
    assert okf.computation.code == "SELECT 41 + 1"
    assert okf.computation.location.path == tmp_path / "revenue.sql"
    assert verify_okf_file(document).ok


def _bundle_with_computation_key(
    tmp_path: Path,
    reference: str,
    extra: str = "",
) -> Path:
    (tmp_path / "bundle").mkdir(exist_ok=True)
    (tmp_path / "outside.sql").write_text("SELECT 1\n", encoding="utf-8")
    document = tmp_path / "bundle" / "revenue.md"
    document.write_text(
        f"""---
type: Attested Computation
runtime: duckdb
computation: {reference}
{extra}---
""",
        encoding="utf-8",
    )
    return document


def test_a_computation_outside_the_bundle_root_is_refused(tmp_path: Path) -> None:
    document = _bundle_with_computation_key(tmp_path, "../outside.sql")

    okf = parse_okf_file(document)

    assert okf.computation is None
    assert any("outside the bundle root" in i for i in okf.document.diagnostics)
    assert not verify_okf_file(document).ok


def test_an_absolute_computation_path_is_refused(tmp_path: Path) -> None:
    document = _bundle_with_computation_key(
        tmp_path, str((tmp_path / "outside.sql").resolve())
    )

    okf = parse_okf_file(document)

    assert okf.computation is None
    assert any("outside the bundle root" in i for i in okf.document.diagnostics)


def test_bundle_root_widens_the_allowed_area(tmp_path: Path) -> None:
    document = _bundle_with_computation_key(
        tmp_path,
        "../outside.sql",
        extra="provedown:\n  okf:\n    bundle_root: ..\n",
    )

    okf = parse_okf_file(document)

    assert okf.document.diagnostics == []
    assert okf.computation is not None
    assert okf.computation.code == "SELECT 1"


def test_the_computation_key_is_not_backfilled_by_a_fence(tmp_path: Path) -> None:
    document = tmp_path / "revenue.md"
    document.write_text(
        """---
type: Attested Computation
runtime: duckdb
computation: missing.sql
---

# Computation

```sql
SELECT 'the fence must not stand in for the named file'
```
""",
        encoding="utf-8",
    )

    okf = parse_okf_file(document)

    assert okf.computation is None
    assert len(okf.document.diagnostics) == 1
    assert "cannot read computation" in okf.document.diagnostics[0]


def test_unreadable_external_computation_is_reported(tmp_path: Path) -> None:
    document = tmp_path / "revenue.md"
    document.write_text(
        """---
type: Attested Computation
runtime: duckdb
computation: missing.sql
---
""",
        encoding="utf-8",
    )

    okf = parse_okf_file(document)

    assert okf.computation is None
    assert any("cannot read computation" in item for item in okf.document.diagnostics)


def test_non_computation_documents_pass_through_untouched(tmp_path: Path) -> None:
    document = tmp_path / "orders.md"
    document.write_text(
        """---
type: BigQuery Table
title: Customer Orders
tags: [sales]
provedown:
  default_language: duckdb
---

The table holds
<span class="result" data-code="SELECT 3">3<span class="method"></span></span>
orders.
""",
        encoding="utf-8",
    )

    okf = parse_okf_file(document)

    assert okf.computation is None
    assert okf.document.diagnostics == []
    assert okf.metadata.type == "BigQuery Table"
    assert verify_okf_file(document).to_dict() == verify_file(document).to_dict()


def test_trust_tier_and_staleness_derive_from_frontmatter() -> None:
    source = """---
type: Metric
title: Revenue
generated: { by: reference_agent/example, at: 2026-06-30T14:00:00Z }
verified:
  - { by: agent:checker, at: 2026-07-01T09:00:00Z }
stale_after: 2026-12-31
sources:
  - id: revenue-policy
    resource: policies/revenue-recognition.md
---
"""

    metadata = parse_okf_document(source).metadata

    assert metadata.trust_tier() == TRUST_MACHINE_CONFIRMED
    assert metadata.status == "stable"
    assert metadata.stale_after == "2026-12-31"
    assert not metadata.is_stale(date(2026, 9, 13))
    assert metadata.is_stale(date(2027, 1, 1))
    assert metadata.sources[0]["id"] == "revenue-policy"
    assert metadata.generated is not None


def test_stale_after_accepts_the_timestamp_form_bundles_use() -> None:
    source = """---
type: Metric
stale_after: 2026-12-31T00:00:00Z
---
"""

    metadata = parse_okf_document(source).metadata

    assert metadata.stale_after == "2026-12-31T00:00:00+00:00"
    assert not metadata.is_stale(date(2026, 12, 31))
    assert metadata.is_stale(date(2027, 1, 1))


def test_unparsable_stale_after_is_never_reported_stale() -> None:
    source = "---\ntype: Metric\nstale_after: whenever\n---\n"

    assert not parse_okf_document(source).metadata.is_stale(date(2030, 1, 1))


def test_trust_tier_prefers_human_actors() -> None:
    source = """---
type: Metric
verified:
  - { by: agent:checker, at: 2026-07-01T09:00:00Z }
  - { by: human:jsmith@acme, at: 2026-07-02T09:00:00Z }
---
"""

    assert parse_okf_document(source).metadata.trust_tier() == TRUST_HUMAN_REVIEWED


def test_unverified_documents_report_the_lowest_tier() -> None:
    assert parse_okf_document("---\ntype: Metric\n---\n").metadata.trust_tier() == (
        TRUST_UNVERIFIED
    )
