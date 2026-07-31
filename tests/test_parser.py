from pathlib import Path

from provedown import CodeBlock, CodeUse, ResultAssertion, parse_document


def test_parser_extracts_code_results_and_ignores_method_slot() -> None:
    document = parse_document(
        """
# Report

<code name="load">
x = 40 + 2
</code>

The answer is <span class="result" data-code="x">42<span class="method"></span></span>.
""".strip(),
        path=Path("report.md"),
    )

    assert document.diagnostics == []
    assert len(document.events) == 2

    code = document.events[0]
    assert isinstance(code, CodeBlock)
    assert code.name == "load"
    assert code.code == "x = 40 + 2"
    assert document.named_code["load"] == code

    result = document.events[1]
    assert isinstance(result, ResultAssertion)
    assert result.authored == "42"
    assert result.code == "x"
    assert result.compare == "exact"


def test_parser_extracts_forward_reference_use_site() -> None:
    document = parse_document(
        """
<code name="load">x = 42</code>
<code use="load"/>
The answer is <span class="result" data-code="x">42<span class="method"></span></span>.
""".strip()
    )

    assert len(document.events) == 3
    assert isinstance(document.events[0], CodeBlock)
    assert isinstance(document.events[1], CodeUse)
    assert isinstance(document.events[2], ResultAssertion)
    assert document.referenced_code_names() == ["load"]


def test_parser_preserves_unknown_attributes_and_language() -> None:
    document = parse_document(
        'The total is <span class="result" data-code="count()" '
        'data-language="r" data-custom="x">4'
        '<span class="method"></span></span>.'
    )

    result = document.events[0]
    assert isinstance(result, ResultAssertion)
    assert result.language == "r"
    assert result.attributes["data-custom"] == "x"


def test_parser_ignores_html_inside_markdown_fenced_code() -> None:
    document = parse_document(
        """
```markdown
<code>x = 1</code>
The answer is <span class="result" data-code="x">1</span>.
```

<code>y = 2</code>
The answer is <span class="result" data-code="y">2</span>.
""".strip()
    )

    assert len(document.events) == 2
    assert isinstance(document.events[0], CodeBlock)
    assert isinstance(document.events[1], ResultAssertion)


def test_parser_ignores_explicit_ignored_regions() -> None:
    document = parse_document(
        """
<div data-provedown-ignore="true">
<code>x = 1</code>
The answer is <span class="result" data-code="x">1</span>.
</div>

<code>y = 2</code>
The answer is <span class="result" data-code="y">2</span>.
""".strip()
    )

    assert len(document.events) == 2
    assert isinstance(document.events[0], CodeBlock)
    assert isinstance(document.events[1], ResultAssertion)


def test_parser_extracts_contract_from_pure_html() -> None:
    document = parse_document(
        """
<!doctype html>
<html lang="en">
  <body>
    <pre><code name="calc">
x = 21 * 2
    </code></pre>
    <p>
      The answer is
      <span class="result" data-code="x">42<span class="method"></span></span>.
    </p>
  </body>
</html>
""".strip(),
        path=Path("report.html"),
    )

    assert document.diagnostics == []
    assert len(document.events) == 2
    assert isinstance(document.events[0], CodeBlock)
    assert document.events[0].name == "calc"
    assert isinstance(document.events[1], ResultAssertion)
    assert document.events[1].authored == "42"


def test_parser_extracts_frontmatter_and_provedown_config() -> None:
    document = parse_document(
        """
---
title: Sales report
project:
  owners:
    - analytics
provedown:
  aliases:
    data: data
    cache: ../cache
  environments:
    python:
      requires-python: ">=3.11"
      dependencies:
        - pandas>=2
        - pyarrow>=15
    sql:
      extensions:
        - spatial
  last_validated: 2026-06-15
  default_language: py
  pyproject: ../pyproject.toml
---
<code>x = 42</code>
The answer is <span class="result" data-code="x">42</span>.
""".strip(),
        path=Path("report.md"),
    )

    assert document.frontmatter["title"] == "Sales report"
    assert document.frontmatter["project"] == {"owners": ["analytics"]}
    assert document.provedown.aliases == {"data": "data", "cache": "../cache"}
    assert document.provedown.environments == {
        "python": {
            "requires-python": ">=3.11",
            "dependencies": ["pandas>=2", "pyarrow>=15"],
        },
        "sql": {"extensions": ["spatial"]},
    }
    assert document.provedown.last_validated == "2026-06-15"
    assert document.provedown.default_language == "py"
    assert document.provedown.pyproject == "../pyproject.toml"

    assert len(document.events) == 2
    assert isinstance(document.events[0], CodeBlock)
    assert document.events[0].language == "py"
    assert isinstance(document.events[1], ResultAssertion)
    assert document.events[1].language == "py"


def test_parser_reports_invalid_environment_config() -> None:
    document = parse_document(
        """
---
provedown:
  environments:
    python:
      dependencies:
        - pandas
    sql: duckdb
---
<code>x = 42</code>
""".strip(),
        path=Path("report.md"),
    )

    assert document.provedown.environments == {
        "python": {"dependencies": ["pandas"]}
    }
    assert len(document.diagnostics) == 1
    assert "provedown environment 'sql' should be a mapping" in document.diagnostics[0]


def test_parser_reports_non_mapping_environments() -> None:
    document = parse_document(
        """
---
provedown:
  environments:
    - python
---
<code>x = 42</code>
""".strip(),
        path=Path("report.md"),
    )

    assert document.provedown.environments == {}
    assert len(document.diagnostics) == 1
    assert "provedown environments should be a mapping" in document.diagnostics[0]


def test_parser_ignores_html_inside_frontmatter() -> None:
    document = parse_document(
        """
---
title: "<code>x = 1</code>"
summary: "<span class='result' data-code='x'>1</span>"
---
<code>y = 2</code>
The answer is <span class="result" data-code="y">2</span>.
""".strip()
    )

    assert len(document.events) == 2
    assert isinstance(document.events[0], CodeBlock)
    assert document.events[0].code == "y = 2"
    assert isinstance(document.events[1], ResultAssertion)
    assert document.events[1].code == "y"


def test_parser_keeps_element_language_over_frontmatter_default() -> None:
    document = parse_document(
        """
---
provedown:
  default_language: r
---
<code data-language="python">x = 42</code>
The answer is <span class="result" data-code="x" data-language="python">42</span>.
""".strip()
    )

    assert isinstance(document.events[0], CodeBlock)
    assert document.events[0].language == "python"
    assert isinstance(document.events[1], ResultAssertion)
    assert document.events[1].language == "python"
