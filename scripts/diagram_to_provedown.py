"""Prototype: lower draw.io and SVG diagrams to Provedown HTML.

This is an exploration aid for ``docs/ideas/diagram-markup.md``, not part of
the ``provedown`` package. It converts a diagram into an ordinary Provedown
HTML document that the existing ``provedown verify`` command can check:

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
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

CODE_PROPERTY = "provedown-code"
RESULT_PROPERTY = "result"
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
CODE_ATTRIBUTES = {"name", "data-language", "language", "lang"}


@dataclass(frozen=True)
class Lowering:
    """Generated Provedown HTML plus what the lowering found along the way."""

    html: str
    claims: int
    diagnostics: list[str]

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
        return drawio_to_html(_drawio_svg_content(source), origin=path.name)
    if name.endswith(".svg"):
        return normalize_svg(source, origin=path.name)
    return drawio_to_html(source, origin=path.name)


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
        elif "data-code" in attributes:
            claims.append(f"{comment}\n<p>{_result_element(cell)}</p>")
        elif RESULT_PROPERTY in attributes:
            diagnostics.append(
                f"{where}: has a {RESULT_PROPERTY} property but no data-code, "
                "so the value has no evidence"
            )
        elif cell.html_label and (_has_result_class(label) or "<code" in label):
            # Agent-authored HTML labels. draw.io's sanitizer drops data-*
            # attributes when a person edits such a label in the editor.
            if _has_result_class(label) and "<code" in label:
                diagnostics.append(
                    f"{where}: HTML label mixes evidence and claims; "
                    "split them into separate shapes"
                )
            elif _has_result_class(label):
                claims.append(f"{comment}\n<div>{label}</div>")
            else:
                code.append(f"{comment}\n<div>{label}</div>")

    if not claims:
        diagnostics.append(f"{origin}: no claims found")
    header = f"<!-- generated from {escape(origin)} by diagram_to_provedown.py -->"
    html = "\n\n".join([header, *code, *claims]) + "\n"
    return Lowering(html=html, claims=len(claims), diagnostics=diagnostics)


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
    diagnostics = list(rewriter.diagnostics)
    if rewriter.claims == 0:
        diagnostics.append(f"{origin}: no claims found")
    return Lowering(
        html=rewriter.output(), claims=rewriter.claims, diagnostics=diagnostics
    )


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
        self.claims = 0
        self.diagnostics: list[str] = []
        self._parts: list[str] = []
        # Original (case-preserved) tag name and whether it became a span.
        self._stack: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or ""
        if tag in {"text", "tspan"} and _is_result(attrs):
            self.claims += 1
            self._stack.append((tag, True))
            self._parts.append(_rename_tag(raw, "span"))
        else:
            self._stack.append((_tag_name(raw) or tag, False))
            self._parts.append(raw)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or ""
        if tag in {"text", "tspan"} and _is_result(attrs):
            self.claims += 1
            raw = _rename_tag(raw, "span")
        self._parts.append(raw)

    def handle_endtag(self, tag: str) -> None:
        original, renamed = self._stack.pop() if self._stack else (tag, False)
        if original.lower() != tag:
            line, column = self.getpos()
            self.diagnostics.append(
                f"{self.origin}:{line}:{column + 1}: unexpected </{tag}>"
            )
        self._parts.append("</span>" if renamed else f"</{original}>")

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
    lowering = convert(args.path)
    output.write_text(lowering.html, encoding="utf-8")
    print(f"{output}: {lowering.claims} claim(s)")
    for diagnostic in lowering.diagnostics:
        print(f"error: {diagnostic}", file=sys.stderr)
    return 0 if lowering.ok else 1


if __name__ == "__main__":
    sys.exit(main())
