"""Prototype: lower draw.io and SVG diagrams to Provedown HTML.

This is an exploration aid for ``docs/ideas/diagram-markup.md``. It is not
shipped in the ``provedown`` package, but imports its parser. It converts a
diagram into an ordinary Provedown HTML document that the existing
``provedown verify`` command can check:

    python scripts/diagram_to_provedown.py examples/diagrams/orders.drawio
    provedown verify examples/diagrams/orders.drawio.provedown.html

Supported inputs:

``.drawio`` / ``.xml``
    draw.io files, with plain or compressed ``<diagram>`` pages. Shapes carry
    Provedown markup as shape properties (``<object>`` attributes).

``.drawio.svg``
    draw.io "editable SVG" exports. The embedded ``content`` attribute is read
    as a draw.io file; the rendered SVG is ignored.

``.svg``
    Hand-written or tool-generated SVG. ``<tspan class="result">`` and
    ``<text class="result">`` are rewritten to ``<span class="result">`` and
    CDATA sections are escaped, preserving line numbers so findings point at
    the original SVG.
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

from provedown.model import ResultAssertion
from provedown.parser import parse_document

GENERATED_HEADER = "<!-- generated from"
# "<string>:LINE:COL: message", as rendered by SourceLocation for path=None.
PARSER_LOCATION = re.compile(r"<string>:(?P<line>\d+):\d+: (?P<message>.*)", re.DOTALL)
# Parser messages for an unclosed <code> and for each tag it swallowed.
UNCLOSED_CODE = "unclosed <code> block"
NESTED_TAG = "nested HTML tag inside <code>"
# The comment drawio_to_html writes before each cell's block.
CELL_COMMENT = re.compile(r"<!-- (?P<where>.*: page .* cell .*) -->")
CODE_PROPERTY = "provedown-code"
RESULT_PROPERTY = "provedown-result"
# Earlier name of RESULT_PROPERTY; only an error next to data-code, since a bare
# "result" is common in unrelated shape data.
LEGACY_RESULT_PROPERTY = "result"
RESULT_ATTRIBUTES = {
    "data-code",
    "data-compare",
    "data-language",
    "language",
    "lang",
    "tol",
    "data-tol",
    "seed",
    "data-seed",
}
# HTML elements that never take an end tag. HTMLParser has no notion of them,
# so an unclosed <br> inside a foreignObject must not be pushed on the stack.
HTML_VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
CODE_ATTRIBUTES = {"name", "data-language", "language", "lang"}


@dataclass(frozen=True)
class Lowering:
    """Generated Provedown HTML plus what the lowering found along the way."""

    html: str
    claims: int
    diagnostics: tuple[str, ...]

    @property
    def ok(self) -> bool:
        # Fail closed: a diagram with no claims would otherwise verify as ok.
        return self.claims > 0 and not self.diagnostics


@dataclass(frozen=True)
class Cell:
    page: str
    cell_id: str
    attributes: dict[str, str]
    html_label: bool


def convert(path: Path) -> Lowering:
    """Lower a draw.io or SVG diagram to Provedown HTML."""

    source = path.read_text(encoding="utf-8")
    name = path.name.lower()
    if name.endswith(".drawio.svg"):
        return drawio_to_html(_drawio_svg_content(source), origin=str(path))
    if name.endswith(".svg"):
        return normalize_svg(source, origin=str(path))
    return drawio_to_html(source, origin=str(path))


def drawio_to_html(source: str, origin: str = "<diagram>") -> Lowering:
    """Lower draw.io XML to Provedown HTML.

    A diagram has no reading order, so all evidence cells are emitted before
    all claim cells. Within each group, pages and cells keep file order.
    """

    code: list[str] = []
    claims: list[str] = []
    diagnostics: list[str] = []
    for cell in _drawio_cells(source):
        where = f"{origin}: page {cell.page!r} cell {cell.cell_id!r}"
        comment = f"<!-- {escape(where)} -->"
        attributes = cell.attributes
        label = attributes.get("label", "")
        if CODE_PROPERTY in attributes and "data-code" in attributes:
            diagnostics.append(
                f"{where}: has both {CODE_PROPERTY} and data-code; "
                "split evidence and claim into separate shapes"
            )
        elif CODE_PROPERTY in attributes:
            code.append(f"{comment}\n{_code_element(cell)}")
        elif (
            "data-code" in attributes
            and LEGACY_RESULT_PROPERTY in attributes
            and (RESULT_PROPERTY not in attributes)
        ):
            diagnostics.append(
                f"{where}: has a {LEGACY_RESULT_PROPERTY!r} property; "
                f"the authored value now goes in {RESULT_PROPERTY!r}"
            )
        elif "data-code" in attributes:
            claims.append(f"{comment}\n<p>{_result_element(cell)}</p>")
        elif RESULT_PROPERTY in attributes:
            diagnostics.append(
                f"{where}: has a {RESULT_PROPERTY} property but no data-code, "
                "so the value has no evidence"
            )
        elif _has_result_class(label) or "<code" in label:
            # Agent-authored HTML labels. draw.io's sanitizer drops data-*
            # attributes when a person edits such a label in the editor.
            if not cell.html_label:
                diagnostics.append(
                    f"{where}: label contains Provedown markup but the shape "
                    "style lacks html=1, so draw.io shows it as literal text"
                )
            elif _has_result_class(label) and "<code" in label:
                diagnostics.append(
                    f"{where}: HTML label mixes evidence and claims; "
                    "split them into separate shapes"
                )
            elif _has_result_class(label):
                claims.append(f"{comment}\n<div>{label}</div>")
            else:
                # draw.io stores label line breaks as <br>; the parser rejects
                # tags nested in <code>, so turn them back into newlines. Labels
                # routed here hold only evidence, so the whole label is safe.
                code.append(f"{comment}\n<div>{_br_to_newline(label)}</div>")

    header = f"{GENERATED_HEADER} {escape(origin)} by diagram_to_provedown.py -->"
    html = "\n\n".join([header, *code, *claims]) + "\n"
    return _lowering(html, origin, diagnostics, keeps_source_lines=False)


def normalize_svg(source: str, origin: str = "<svg>") -> Lowering:
    """Rewrite SVG-native Provedown markup to the HTML contract in place."""

    source = re.sub(
        r"<!\[CDATA\[(.*?)\]\]>",
        lambda match: escape(match.group(1), quote=False),
        source,
        flags=re.DOTALL,
    )
    rewriter = _SvgResultRewriter(origin)
    rewriter.feed(source)
    rewriter.close()
    # The header shares line 1 so line numbers still match the original SVG.
    header = f"{GENERATED_HEADER} {escape(origin)} by diagram_to_provedown.py -->"
    return _lowering(
        header + rewriter.output(),
        origin,
        rewriter.diagnostics,
        keeps_source_lines=True,
    )


def _lowering(
    html: str,
    origin: str,
    diagnostics: list[str],
    *,
    keeps_source_lines: bool,
) -> Lowering:
    """Parse the output the way verify will.

    Counts only claims verify will check (not ones in ignored regions) and
    surfaces the parser's errors, since verify refuses to run a document with
    any of them. When the output keeps the source's line numbers (SVG), errors
    cite the source file directly. Otherwise (draw.io) each error is mapped
    back to the cell that produced that line of the generated HTML.
    """

    diagnostics = list(diagnostics)
    parsed = parse_document(html, path=Path(origin) if keeps_source_lines else None)
    claims = sum(isinstance(event, ResultAssertion) for event in parsed.events)
    parser_diagnostics = parsed.diagnostics
    if any(UNCLOSED_CODE in d for d in parser_diagnostics):
        # An unclosed <code> swallows every later tag, one error per tag, in
        # whichever cells follow. Report the cause, not that cascade.
        parser_diagnostics = [d for d in parser_diagnostics if NESTED_TAG not in d]
    for diagnostic in parser_diagnostics:
        match = None if keeps_source_lines else PARSER_LOCATION.match(diagnostic)
        if match:
            diagnostic = f"{_drawio_location(html, int(match['line']), origin)}: "
            diagnostic += match["message"]
        if diagnostic not in diagnostics:
            diagnostics.append(diagnostic)
    # With parser errors, "no claims" is a consequence rather than the cause.
    if claims == 0 and not parser_diagnostics:
        diagnostics.append(f"{origin}: no claims found")
    return Lowering(html=html, claims=claims, diagnostics=tuple(diagnostics))


def _drawio_location(html: str, line: int, origin: str) -> str:
    """Describe ``line`` of generated draw.io HTML by page, cell and offset."""

    lines = html.splitlines()[:line]
    for index in range(len(lines) - 1, -1, -1):
        match = CELL_COMMENT.fullmatch(lines[index].strip())
        if match:
            offset = line - (index + 1)
            return f"{unescape(match['where'])} (line {offset} of its block)"
    return f"{origin} (generated HTML line {line})"


def _drawio_cells(source: str) -> Iterator[Cell]:
    root = ElementTree.fromstring(source)
    diagrams = root.findall("diagram") if root.tag == "mxfile" else [root]
    for index, diagram in enumerate(diagrams, start=1):
        page = diagram.get("name") or f"Page-{index}"
        model = _diagram_model(diagram)
        if model is None:
            continue
        for element in model.iter():
            if element.tag in {"object", "UserObject"}:
                yield _object_cell(page, element)
            elif element.tag == "mxCell" and element.get("value"):
                yield Cell(
                    page=page,
                    cell_id=element.get("id", ""),
                    attributes={"label": element.get("value", "")},
                    html_label="html=1" in (element.get("style") or ""),
                )


def _diagram_model(diagram: ElementTree.Element) -> ElementTree.Element | None:
    if diagram.tag == "mxGraphModel":
        return diagram
    model = diagram.find("mxGraphModel")
    if model is not None:
        return model
    text = (diagram.text or "").strip()
    if not text:
        return None
    # Compressed pages: base64, raw deflate, then URI encoding.
    inflated = zlib.decompress(base64.b64decode(text), -15).decode("utf-8")
    return ElementTree.fromstring(unquote(inflated))


def _object_cell(page: str, element: ElementTree.Element) -> Cell:
    inner = element.find("mxCell")
    style = inner.get("style", "") if inner is not None else ""
    return Cell(
        page=page,
        cell_id=element.get("id", ""),
        attributes=dict(element.attrib),
        html_label="html=1" in style,
    )


def _drawio_svg_content(source: str) -> str:
    root = ElementTree.fromstring(source)
    content = root.get("content")
    if not content:
        raise ValueError("SVG has no embedded draw.io content attribute")
    return content


def _code_element(cell: Cell) -> str:
    attrs = _copy_attributes(cell.attributes, CODE_ATTRIBUTES)
    code = escape(cell.attributes[CODE_PROPERTY], quote=False)
    return f"<pre><code{attrs}>\n{code}\n</code></pre>"


def _result_element(cell: Cell) -> str:
    attrs = _copy_attributes(cell.attributes, RESULT_ATTRIBUTES)
    # Without a result property the whole visible label is the authored value,
    # so the label must be exactly the value (e.g. "$461.00", not "Total: …").
    authored = cell.attributes.get(RESULT_PROPERTY) or _label_text(cell)
    return (
        f'<span class="result"{attrs}>{escape(authored, quote=False)}'
        '<span class="method"></span></span>'
    )


def _copy_attributes(attributes: dict[str, str], allowed: set[str]) -> str:
    return "".join(
        f' {key}="{escape(value)}"'
        for key, value in attributes.items()
        if key in allowed
    )


def _label_text(cell: Cell) -> str:
    label = cell.attributes.get("label", "")
    if not cell.html_label:
        return label.strip()
    extractor = _TextExtractor()
    extractor.feed(label)
    extractor.close()
    return extractor.text().strip()


def _br_to_newline(label: str) -> str:
    return re.sub(r"<br\s*/?>", "\n", label, flags=re.IGNORECASE)


def _has_result_class(label: str) -> bool:
    pattern = r"class=[\"'](?:[^\"']*\s)?result(?:\s[^\"']*)?[\"']"
    return re.search(pattern, label) is not None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return " ".join("".join(self._parts).split())


class _SvgResultRewriter(HTMLParser):
    """Rename SVG result elements to ``span`` without moving any text."""

    def __init__(self, origin: str) -> None:
        super().__init__(convert_charrefs=False)
        self.origin = origin
        self.diagnostics: list[str] = []
        self._parts: list[str] = []
        # Original (case-preserved) tag name and whether it became a span.
        self._stack: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or ""
        if tag in {"text", "tspan"} and _is_result(attrs):
            self._stack.append((tag, True))
            self._parts.append(_rename_tag(raw, "span"))
            return
        if tag in HTML_VOID_ELEMENTS:
            self._parts.append(raw)
        else:
            self._stack.append((_tag_name(raw) or tag, False))
            self._parts.append(raw)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or ""
        if tag in {"text", "tspan"} and _is_result(attrs):
            raw = _rename_tag(raw, "span")
        self._parts.append(raw)

    def handle_endtag(self, tag: str) -> None:
        if tag in HTML_VOID_ELEMENTS:
            # Void start tags are never pushed, so an end tag such as the
            # XML-style <br></br> closes nothing on the stack. Only one
            # outside any element is worth reporting.
            if not self._stack:
                self._error(f"unexpected </{tag}> with no open element")
            self._parts.append(f"</{tag}>")
            return
        if not self._stack:
            self._error(f"unexpected </{tag}> with no open element")
            self._parts.append(f"</{tag}>")
            return
        original, renamed = self._stack.pop()
        if original.lower() != tag:
            self._error(f"unexpected </{tag}>")
        self._parts.append("</span>" if renamed else f"</{original}>")

    def _error(self, message: str) -> None:
        line, column = self.getpos()
        self.diagnostics.append(f"{self.origin}:{line}:{column + 1}: {message}")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._parts.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._parts.append(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self._parts.append(f"<![{data}]>")

    def output(self) -> str:
        return "".join(self._parts)


def _is_result(attrs: list[tuple[str, str | None]]) -> bool:
    classes = dict(attrs).get("class") or ""
    return "result" in classes.split()


def _tag_name(raw: str) -> str | None:
    # HTMLParser lowercases tag names; keep SVG camelCase such as clipPath.
    match = re.match(r"<\s*([\w:-]+)", raw)
    return match.group(1) if match else None


def _rename_tag(raw: str, new: str) -> str:
    return re.sub(r"^<\s*[\w:-]+", f"<{new}", raw)


def _remove_stale_output(output: Path) -> None:
    """Remove output from an earlier run so a later verify can't check it.

    Only files this script wrote (identified by the header) are removed, so a
    mistyped input path never deletes an unrelated --output target. A write
    that fails partway can still leave an unrelated -o target truncated, as
    with any tool that overwrites its output path.
    """

    try:
        with output.open(encoding="utf-8") as handle:
            ours = handle.read(len(GENERATED_HEADER)) == GENERATED_HEADER
    except (OSError, UnicodeDecodeError):
        return  # Missing, unreadable or not text: not output we wrote.
    if not ours:
        return
    try:
        output.unlink()
    except OSError as exc:
        print(f"error: could not remove stale {output}: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output path (default: <input>.provedown.html next to the input, "
        "so relative data paths still resolve)",
    )
    args = parser.parse_args(argv)
    output = args.output or args.path.with_name(args.path.name + ".provedown.html")
    try:
        lowering = convert(args.path)
    except (OSError, ValueError, ElementTree.ParseError, zlib.error) as exc:
        # binascii.Error (bad base64) is a ValueError subclass.
        print(f"error: {args.path}: {exc}", file=sys.stderr)
        _remove_stale_output(output)
        return 1
    try:
        output.write_text(lowering.html, encoding="utf-8")
    except OSError as exc:
        print(f"error: {output}: {exc}", file=sys.stderr)
        # A partial write still starts with the header; don't leave it.
        _remove_stale_output(output)
        return 1
    print(f"{output}: {lowering.claims} claim(s)")
    for diagnostic in lowering.diagnostics:
        print(f"error: {diagnostic}", file=sys.stderr)
    return 0 if lowering.ok else 1


if __name__ == "__main__":
    sys.exit(main())
