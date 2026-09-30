"""Tests for the exploratory diagram lowering script."""

import base64
import importlib.util
import sys
import zlib
from pathlib import Path
from types import ModuleType
from urllib.parse import quote
from xml.sax.saxutils import quoteattr

from provedown import Status, VerificationContext, parse_document, verify_document

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
    report = verify_document(
        parse_document(html), context=VerificationContext(cwd=cwd)
    )
    return [finding.status for finding in report.findings]


def test_drawio_example_verifies() -> None:
    html = script.convert(EXAMPLES / "orders.drawio")

    assert _statuses(html) == [Status.PASS, Status.PASS, Status.PASS]


def test_svg_example_verifies_and_keeps_line_numbers() -> None:
    source = (EXAMPLES / "orders.svg").read_text(encoding="utf-8")
    html = script.convert(EXAMPLES / "orders.svg")

    assert html.count("\n") == source.count("\n")
    assert _statuses(html) == [Status.PASS, Status.PASS, Status.PASS]
    result_lines = [
        event.location.line
        for event in parse_document(html).events
        if type(event).__name__ == "ResultAssertion"
    ]
    source_lines = [
        number
        for number, line in enumerate(source.splitlines(), start=1)
        if 'class="result"' in line
    ]
    assert result_lines == source_lines


def test_stale_drawio_property_fails() -> None:
    source = (EXAMPLES / "orders.drawio").read_text(encoding="utf-8")
    stale = source.replace('result="4"', 'result="5"')

    html = script.drawio_to_html(stale)

    assert _statuses(html) == [Status.PASS, Status.FAIL, Status.PASS]


def test_compressed_drawio_page() -> None:
    model = (
        '<mxGraphModel><root><mxCell id="0"/>'
        '<object id="c" label="code" provedown-code="x = 40 + 2">'
        '<mxCell vertex="1" parent="0"/></object>'
        '<object id="r" label="42" data-code="x">'
        '<mxCell vertex="1" parent="0"/></object>'
        "</root></mxGraphModel>"
    )
    deflate = zlib.compressobj(wbits=-15)
    packed = deflate.compress(quote(model).encode()) + deflate.flush()
    payload = base64.b64encode(packed).decode()
    source = f'<mxfile><diagram name="p">{payload}</diagram></mxfile>'

    assert _statuses(script.drawio_to_html(source)) == [Status.PASS]


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

    html = script.convert(svg)

    assert _statuses(html, cwd=tmp_path / "sub") == [Status.PASS] * 3


def test_html_label_contract_is_passed_through() -> None:
    source = (
        "<mxfile><diagram name=\"p\"><mxGraphModel><root>"
        '<mxCell id="c" style="text;html=1;" '
        'value="&lt;pre&gt;&lt;code&gt;x = 2&lt;/code&gt;&lt;/pre&gt;"/>'
        '<mxCell id="r" style="html=1;" value="Total: &lt;span '
        'class=&quot;result&quot; data-code=&quot;x&quot;&gt;2&lt;/span&gt;"/>'
        '<mxCell id="plain" style="html=1;" value="Just a label"/>'
        "</root></mxGraphModel></diagram></mxfile>"
    )

    html = script.drawio_to_html(source)

    assert "Just a label" not in html
    assert _statuses(html) == [Status.PASS]
