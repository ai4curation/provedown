"""Tests for the exploratory diagram lowering script."""

import base64
import importlib.util
import sys
import zlib
from pathlib import Path
from types import ModuleType
from urllib.parse import quote
from xml.sax.saxutils import quoteattr

import pytest

from provedown import Status, VerificationContext, parse_document, verify_document
from provedown.model import ResultAssertion

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/diagrams"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "diagram_to_provedown", ROOT / "scripts/diagram_to_provedown.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


def _statuses(html: str, cwd: Path = EXAMPLES) -> list[Status]:
    report = verify_document(parse_document(html), context=VerificationContext(cwd=cwd))
    return [finding.status for finding in report.findings]


def _drawio(cells: str) -> str:
    return (
        '<mxfile><diagram name="p"><mxGraphModel><root>'
        f"{cells}</root></mxGraphModel></diagram></mxfile>"
    )


def _object(cell_id: str, **attributes: str) -> str:
    attrs = "".join(
        f" {key.replace('_', '-')}={quoteattr(value)}"
        for key, value in attributes.items()
    )
    return f'<object id="{cell_id}"{attrs}><mxCell vertex="1"/></object>'


def test_drawio_example_verifies() -> None:
    lowering = script.convert(EXAMPLES / "orders.drawio")

    assert lowering.ok
    assert lowering.claims == 3
    assert _statuses(lowering.html) == [Status.PASS, Status.PASS, Status.PASS]


def test_svg_example_verifies_and_keeps_line_numbers() -> None:
    source = (EXAMPLES / "orders.svg").read_text(encoding="utf-8")
    lowering = script.convert(EXAMPLES / "orders.svg")

    assert lowering.ok
    assert lowering.html.count("\n") == source.count("\n")
    assert _statuses(lowering.html) == [Status.PASS, Status.PASS, Status.PASS]
    result_lines = [
        event.location.line
        for event in parse_document(lowering.html).events
        if isinstance(event, ResultAssertion)
    ]
    source_lines = [
        number
        for number, line in enumerate(source.splitlines(), start=1)
        if 'class="result"' in line
    ]
    assert result_lines == source_lines


def test_svg_text_result_and_camel_case_tags() -> None:
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        "<defs><clipPath id='c'><rect/></clipPath></defs>"
        "<metadata><code>x = 2</code></metadata>"
        '<text class="label result" data-code="x">2</text>'
        "</svg>"
    )

    lowering = script.normalize_svg(source)

    assert lowering.ok
    assert "<clipPath id='c'><rect/></clipPath>" in lowering.html
    assert '<span class="label result" data-code="x">2</span>' in lowering.html
    assert _statuses(lowering.html) == [Status.PASS]


def test_svg_without_claims_fails_closed() -> None:
    lowering = script.normalize_svg('<svg><text class="no-result">2</text></svg>')

    assert not lowering.ok
    assert lowering.diagnostics == ("<svg>: no claims found",)


def test_svg_mismatched_end_tag_is_reported() -> None:
    lowering = script.normalize_svg(
        '<svg><text><tspan class="result" data-code="1">1</text></tspan></svg>'
    )

    assert not lowering.ok
    assert any("unexpected </text>" in d for d in lowering.diagnostics)


def test_stale_drawio_property_fails() -> None:
    source = (EXAMPLES / "orders.drawio").read_text(encoding="utf-8")
    stale = source.replace('provedown-result="4"', 'provedown-result="5"')

    lowering = script.drawio_to_html(stale)

    assert _statuses(lowering.html) == [Status.PASS, Status.FAIL, Status.PASS]


def test_compressed_drawio_page() -> None:
    model = (
        '<mxGraphModel><root><mxCell id="0"/>'
        + _object("c", label="code", provedown_code="x = 40 + 2")
        + _object("r", label="42", data_code="x")
        + "</root></mxGraphModel>"
    )
    deflate = zlib.compressobj(wbits=-15)
    packed = deflate.compress(quote(model).encode()) + deflate.flush()
    payload = base64.b64encode(packed).decode()
    source = f'<mxfile><diagram name="p">{payload}</diagram></mxfile>'

    assert _statuses(script.drawio_to_html(source).html) == [Status.PASS]


def test_drawio_svg_export_reads_embedded_content(tmp_path: Path) -> None:
    drawio = (EXAMPLES / "orders.drawio").read_text(encoding="utf-8")
    svg = tmp_path / "orders.drawio.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f"content={quoteattr(drawio)}><g/></svg>",
        encoding="utf-8",
    )
    (tmp_path / "data").mkdir()
    (tmp_path / "sub").mkdir()
    csv = ROOT / "examples/data/orders.csv"
    (tmp_path / "data/orders.csv").write_text(csv.read_text(encoding="utf-8"))

    lowering = script.convert(svg)

    assert _statuses(lowering.html, cwd=tmp_path / "sub") == [Status.PASS] * 3


def test_svg_without_drawio_content_is_rejected(tmp_path: Path) -> None:
    svg = tmp_path / "plain.drawio.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")

    with pytest.raises(ValueError, match=r"no embedded draw\.io content"):
        script.convert(svg)


def test_html_label_evidence_is_emitted_before_claims() -> None:
    # The claim comes first in file (z-) order; evidence must still run first.
    source = _drawio(
        '<mxCell id="r" style="html=1;" value="&lt;span '
        'class=&quot;result&quot; data-code=&quot;x&quot;&gt;2&lt;/span&gt;"/>'
        + _object("r2", label="3", data_code="x + 1")
        + '<mxCell id="c" style="text;html=1;" '
        'value="&lt;pre&gt;&lt;code&gt;x = 2&lt;/code&gt;&lt;/pre&gt;"/>'
        '<mxCell id="plain" style="html=1;" value="Just a label"/>'
    )

    lowering = script.drawio_to_html(source)

    assert lowering.ok
    assert "Just a label" not in lowering.html
    assert _statuses(lowering.html) == [Status.PASS, Status.PASS]


@pytest.mark.parametrize(
    ("cells", "message"),
    [
        (_object("r", label="4", provedown_result="4"), "no data-code"),
        (
            _object("both", label="4", provedown_code="x = 4", data_code="x"),
            "both provedown-code and data-code",
        ),
        (
            '<mxCell id="m" style="html=1;" value="&lt;code&gt;x = 1&lt;/code&gt;'
            "&lt;span class=&quot;result&quot; data-code=&quot;x&quot;&gt;1"
            '&lt;/span&gt;"/>',
            "mixes evidence and claims",
        ),
        (_object("typo", label="4", datacode="x"), "no claims found"),
        ('<mxCell id="plain" value="Just a label"/>', "no claims found"),
        (
            '<mxCell id="p" style="rounded=1;" value="&lt;span '
            'class=&quot;result&quot; data-code=&quot;1&quot;&gt;1&lt;/span&gt;"/>'
            + _object("ok", label="1", data_code="1"),
            "lacks html=1",
        ),
    ],
)
def test_drawio_authoring_mistakes_fail_closed(cells: str, message: str) -> None:
    lowering = script.drawio_to_html(_drawio(cells))

    assert not lowering.ok
    assert any(message in diagnostic for diagnostic in lowering.diagnostics)


def test_empty_result_property_falls_back_to_label() -> None:
    source = _drawio(
        _object("c", label="code", provedown_code="x = 4")
        + _object("r", label="4", provedown_result="", data_code="x")
    )

    assert _statuses(script.drawio_to_html(source).html) == [Status.PASS]


def test_main_writes_next_to_input_and_exit_status(tmp_path: Path) -> None:
    good = tmp_path / "good.drawio"
    good.write_text(
        _drawio(
            _object("c", label="code", provedown_code="x = 4")
            + _object("r", label="4", data_code="x")
        ),
        encoding="utf-8",
    )
    empty = tmp_path / "empty.drawio"
    empty.write_text(_drawio(""), encoding="utf-8")

    assert script.main([str(good)]) == 0
    assert (tmp_path / "good.drawio.provedown.html").exists()
    assert script.main([str(empty)]) == 1


def test_html_label_evidence_keeps_line_breaks() -> None:
    source = _drawio(
        '<mxCell id="c" style="text;html=1;" value="&lt;pre&gt;&lt;code&gt;'
        'x = 2&lt;br&gt;y = 3&lt;br/&gt;z = x + y&lt;/code&gt;&lt;/pre&gt;"/>'
        + _object("r", label="5", data_code="z")
    )

    lowering = script.drawio_to_html(source)

    assert lowering.ok
    assert "x = 2\ny = 3\nz = x + y" in lowering.html
    assert _statuses(lowering.html) == [Status.PASS]


def test_unrelated_result_property_is_ignored() -> None:
    source = _drawio(
        _object("c", label="code", provedown_code="x = 4")
        + _object("r", label="4", data_code="x")
        + _object("test", label="Test run", result="passed")
    )

    lowering = script.drawio_to_html(source)

    assert lowering.ok
    assert _statuses(lowering.html) == [Status.PASS]


def test_svg_stray_end_tag_is_reported() -> None:
    lowering = script.normalize_svg(
        '<svg><text class="result" data-code="1">1</text></svg></clipPath>'
    )

    assert not lowering.ok
    assert any("with no open element" in d for d in lowering.diagnostics)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("missing.drawio", None),
        ("broken.drawio", "<mxfile><diagram>"),
        ("bad-base64.drawio", '<mxfile><diagram name="p">!!!</diagram></mxfile>'),
        ("plain.drawio.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>'),
    ],
)
def test_main_reports_unreadable_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    content: str | None,
) -> None:
    path = tmp_path / name
    if content is not None:
        path.write_text(content, encoding="utf-8")

    assert script.main([str(path)]) == 1
    assert capsys.readouterr().err.startswith(f"error: {path}: ")


def test_svg_void_elements_do_not_desynchronise_end_tags() -> None:
    source = (
        "<svg><foreignObject>"
        '<div xmlns="http://www.w3.org/1999/xhtml">a<br>b<img src="x"></div>'
        "</foreignObject>"
        '<text class="result" data-code="1">1</text></svg>'
    )

    lowering = script.normalize_svg(source)

    assert lowering.ok
    assert lowering.html == source.replace("<text", "<span").replace(
        "</text>", "</span>"
    )


def test_svg_counts_html_span_claims_in_foreign_object() -> None:
    lowering = script.normalize_svg(
        "<svg><foreignObject><div>Total "
        '<span class="result" data-code="2">2</span></div></foreignObject></svg>'
    )

    assert lowering.ok
    assert lowering.claims == 1
    assert _statuses(lowering.html) == [Status.PASS]


def test_svg_prefixed_code_element_round_trips() -> None:
    source = (
        '<svg xmlns:pd="https://ai4curation.io/provedown">'
        "<metadata><pd:code>x = 1</pd:code></metadata>"
        '<text class="result" data-code="1">1</text></svg>'
    )

    lowering = script.normalize_svg(source)

    assert lowering.ok
    assert "<pd:code>x = 1</pd:code>" in lowering.html


def test_legacy_result_property_next_to_data_code_is_reported() -> None:
    source = _drawio(
        _object("c", label="code", provedown_code="x = 4")
        + _object("r", label="Paid %result%", result="4", data_code="x")
    )

    lowering = script.drawio_to_html(source)

    assert not lowering.ok
    assert any("now goes in 'provedown-result'" in d for d in lowering.diagnostics)


def test_main_removes_stale_output_when_input_is_unreadable(tmp_path: Path) -> None:
    broken = tmp_path / "broken.drawio"
    broken.write_text("<mxfile><diagram>", encoding="utf-8")
    stale = tmp_path / "broken.drawio.provedown.html"
    stale.write_text("<p>old</p>", encoding="utf-8")

    assert script.main([str(broken)]) == 1
    assert not stale.exists()


def test_main_reports_unwritable_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = tmp_path / "good.drawio"
    good.write_text(
        _drawio(
            _object("c", label="code", provedown_code="x = 4")
            + _object("r", label="4", data_code="x")
        ),
        encoding="utf-8",
    )
    output = tmp_path / "missing-dir" / "out.html"

    assert script.main([str(good), "-o", str(output)]) == 1
    assert capsys.readouterr().err.startswith(f"error: {output}: ")
