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
            "has provedown-code and also data-code;",
        ),
        (
            '<mxCell id="m" style="html=1;" value="&lt;code&gt;x = 1&lt;/code&gt;'
            "&lt;span class=&quot;result&quot; data-code=&quot;x&quot;&gt;1"
            '&lt;/span&gt;"/>',
            "mixes evidence and claims",
        ),
        (_object("typo", label="4", datacode="x"), "no claims found"),
        (
            _object(
                "note",
                label='<span class="result">4</span> paid',
                provedown_code="x = 4",
            )
            + _object("r", label="4", data_code="x"),
            'has provedown-code and also a class="result" label; '
            "put each piece of evidence and each claim in its own shape; its "
            "style also lacks html=1",
        ),
        (
            _object("note", label="4", provedown_code="x = 4", provedown_result="4")
            + _object("r", label="4", data_code="x"),
            "has provedown-code and also provedown-result;",
        ),
        ('<mxCell id="plain" value="Just a label"/>', "no claims found"),
        (
            # Evidence in the label next to a code property: the label's
            # assert would otherwise be dropped and never run.
            _object(
                "ev",
                label="<pre><code>assert total == 999</code></pre>",
                provedown_code="total = 461.0",
            )
            + _object("r", label="461.0", data_code="total"),
            "has provedown-code and also a <code> label;",
        ),
        (
            _object("c", label="code", provedown_code="total = 461.0")
            + _object(
                "r",
                label="<pre><code>assert total == 999</code></pre>",
                provedown_result="461.0",
                data_code="total",
            ),
            "has data-code and also a <code> label;",
        ),
        (
            _object("c", label="code", provedown_code="x = 4")
            + _object("r", label='<span class="result">4</span> paid', data_code="x"),
            'has data-code and also a class="result" label; put the value in '
            "provedown-result",
        ),
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
    assert lowering.html.endswith(
        source.replace("<text", "<span").replace("</text>", "</span>")
    )


def test_svg_xml_style_closed_void_element() -> None:
    source = (
        "<svg><foreignObject><div>a<br></br>b</div></foreignObject>"
        '<text class="result" data-code="1">1</text></svg>'
    )

    lowering = script.normalize_svg(source)

    assert lowering.ok
    assert lowering.html.endswith(
        "<svg><foreignObject><div>a<br></br>b</div></foreignObject>"
        '<span class="result" data-code="1">1</span></svg>'
    )


def test_svg_claims_in_ignored_regions_do_not_count() -> None:
    lowering = script.normalize_svg(
        '<svg><g class="provedown-ignore">'
        '<text class="result" data-code="1">1</text></g></svg>'
    )

    assert not lowering.ok
    assert lowering.claims == 0
    assert lowering.diagnostics == ("<svg>: no claims found",)


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
    stale.write_text(
        "<!-- generated from broken.drawio by diagram_to_provedown.py -->\n<p>old</p>",
        encoding="utf-8",
    )

    assert script.main([str(broken)]) == 1
    assert not stale.exists()


def test_main_keeps_unrelated_output_when_input_is_unreadable(tmp_path: Path) -> None:
    unrelated = tmp_path / "report.provedown.html"
    unrelated.write_text("<p>hand-written</p>", encoding="utf-8")

    assert script.main([str(tmp_path / "typo.drawi"), "-o", str(unrelated)]) == 1
    assert unrelated.read_text(encoding="utf-8") == "<p>hand-written</p>"


def test_main_reports_unreadable_input_with_directory_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    assert script.main([str(tmp_path / "missing.drawio"), "-o", str(out_dir)]) == 1
    assert capsys.readouterr().err.startswith("error: ")
    assert out_dir.is_dir()


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


@pytest.mark.parametrize(
    ("evidence", "message"),
    [
        ("&lt;pre&gt;&lt;code&gt;x = 2", "column 6): unclosed <code> block"),
        (
            "&lt;code&gt;x = &lt;b&gt;2&lt;/b&gt;&lt;/code&gt;",
            "column 11): nested HTML tag inside <code> was ignored",
        ),
    ],
)
def test_parser_errors_in_lowered_output_are_reported(
    evidence: str, message: str
) -> None:
    source = _drawio(
        f'<mxCell id="ev" style="html=1;" value="{evidence}"/>'
        + _object("r", label="2", data_code="x")
        + _object("r2", label="2", data_code="x")
    )

    lowering = script.drawio_to_html(source, origin="t.drawio")

    # One error naming the evidence cell: no cascade blamed on the claim cells
    # after an unclosed <code>, no repeats, and no "no claims found" follow-on.
    assert lowering.diagnostics == (
        f"t.drawio: page 'p' cell 'ev' (line 1 of its block, {message}",
    )


def test_drawio_location_reports_offset_and_falls_back() -> None:
    html = "<!-- generated -->\n\n<!-- t.drawio: page 'p' cell 'c' -->\na\nb\n"

    assert script._drawio_location(html, 5, "t.drawio", 1) == (
        "t.drawio: page 'p' cell 'c' (line 2 of its block, column 1)"
    )
    assert script._drawio_location(html, 1, "t.drawio", 1) == (
        "t.drawio (generated HTML line 1, column 1)"
    )


def test_svg_stray_void_end_tag_is_reported() -> None:
    lowering = script.normalize_svg(
        '<svg><text class="result" data-code="1">1</text></svg></br>'
    )

    assert not lowering.ok
    assert any(
        "unexpected </br> with no open element" in d for d in lowering.diagnostics
    )


def _good_drawio(tmp_path: Path) -> Path:
    good = tmp_path / "good.drawio"
    good.write_text(
        _drawio(
            _object("c", label="code", provedown_code="x = 4")
            + _object("r", label="4", data_code="x")
        ),
        encoding="utf-8",
    )
    return good


def test_main_removes_partial_output_after_failed_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = _good_drawio(tmp_path)
    output = tmp_path / "good.drawio.provedown.html"

    def partial_write(self: Path, data: str, encoding: str | None = None) -> int:
        with self.open("w", encoding=encoding) as handle:
            handle.write(data[:40])
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", partial_write)

    assert script.main([str(good)]) == 1
    assert not output.exists()


def test_main_reports_failed_stale_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stale = tmp_path / "missing.drawio.provedown.html"
    stale.write_text(
        "<!-- generated from missing.drawio by diagram_to_provedown.py -->",
        encoding="utf-8",
    )

    def deny(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("read-only directory")

    monkeypatch.setattr(Path, "unlink", deny)

    assert script.main([str(tmp_path / "missing.drawio")]) == 1
    assert "could not remove stale" in capsys.readouterr().err


def test_unclosed_code_keeps_unrelated_earlier_errors() -> None:
    # Cell 'a' has two nested tags in a properly closed block; cell 'b' leaves
    # its <code> open. Only the tags after 'b' are cascade and get dropped.
    source = _drawio(
        '<mxCell id="a" style="html=1;" value="&lt;code&gt;x = &lt;b&gt;2&lt;/b&gt;'
        ' + &lt;i&gt;3&lt;/i&gt;&lt;/code&gt;"/>'
        '<mxCell id="b" style="html=1;" value="&lt;pre&gt;&lt;code&gt;y = 3"/>'
        + _object("r", label="2", data_code="x")
    )

    lowering = script.drawio_to_html(source, origin="t.drawio")

    nested = "nested HTML tag inside <code> was ignored"
    assert lowering.diagnostics == (
        f"t.drawio: page 'p' cell 'a' (line 1 of its block, column 11): {nested}",
        f"t.drawio: page 'p' cell 'a' (line 1 of its block, column 22): {nested}",
        "t.drawio: page 'p' cell 'b' (line 1 of its block, column 6): "
        "unclosed <code> block",
    )


def test_cascade_filter_matches_parser_wording() -> None:
    # The filter keys on these parser messages; fail loudly if they change.
    unclosed = parse_document("<code>x = 1").diagnostics
    nested = parse_document("<code>x = <b>1</b></code>").diagnostics

    assert any(script.UNCLOSED_CODE in d for d in unclosed)
    assert any(script.NESTED_TAG in d for d in nested)
    # ...and on the location prefix the filter reads positions from.
    unclosed_error = next(d for d in unclosed if script.UNCLOSED_CODE in d)
    nested_error = next(d for d in nested if script.NESTED_TAG in d)
    assert script._diagnostic_position(unclosed_error) == (1, 1)
    assert script.PARSER_LOCATION.match(nested_error) is not None


def test_unclosed_code_keeps_earlier_error_on_the_same_line() -> None:
    # One label, so one generated line: a closed block with a nested tag, then
    # an unclosed block. The earlier error is not part of the cascade.
    source = _drawio(
        '<mxCell id="ev" style="html=1;" value="&lt;code&gt;x = &lt;b&gt;2'
        '&lt;/b&gt;&lt;/code&gt;&lt;code&gt;y = 3"/>'
        + _object("r", label="2", data_code="x")
    )

    lowering = script.drawio_to_html(source, origin="t.drawio")

    assert lowering.diagnostics == (
        "t.drawio: page 'p' cell 'ev' (line 1 of its block, column 11): "
        "nested HTML tag inside <code> was ignored",
        "t.drawio: page 'p' cell 'ev' (line 1 of its block, column 26): "
        "unclosed <code> block",
    )


def test_svg_unclosed_code_keeps_earlier_error_on_the_same_line() -> None:
    # Line 2 has a closed block with a nested tag, then an unclosed block.
    lowering = script.normalize_svg(
        '<svg><text class="result" data-code="1">1</text>\n'
        "<p><code>z = <i>4</i></code><code>w = 5",
        origin="o.svg",
    )

    assert lowering.diagnostics == (
        "o.svg:2:14: nested HTML tag inside <code> was ignored",
        "o.svg:2:29: unclosed <code> block",
    )
