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
