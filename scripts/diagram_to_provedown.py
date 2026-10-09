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
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

from provedown.model import ResultAssertion
from provedown.parser import parse_document

GENERATED_HEADER = "<!-- generated from"
# "<string>:LINE:COL: message", as rendered by SourceLocation for path=None.
PARSER_LOCATION = re.compile(
    r"<string>:(?P<line>\d+):(?P<column>\d+): (?P<message>.*)", re.DOTALL
)
# The line number in any rendered parser diagnostic, "<path>:LINE:COL: ...".
# Matches the first ":N:M: " in the message, which is the location prefix as
# long as the origin path itself contains no ":digits:digits: ".
DIAGNOSTIC_POSITION = re.compile(r".*?:(?P<line>\d+):(?P<column>\d+): ", re.DOTALL)
# Parser messages for an unclosed <code> and for each tag it swallowed.
UNCLOSED_CODE = "unclosed <code> block"
NESTED_TAG = "nested HTML tag inside <code>"
# Elements whose class="result" is a claim: verify only honours <span>, and
# the SVG rewriter renames <text> and <tspan> to <span>.
LABEL_RESULT_TAGS = {"span"}
SVG_RESULT_TAGS = {"text", "tspan", "span"}
# drawio_to_html wraps each HTML label in this element.
LABEL_WRAPPER = "<div>"
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
        markup = _label_markup(label)
        if CODE_PROPERTY in attributes:
            # Only the property becomes output, so anything else on the shape
            # (a claim, or evidence in the label) would be silently dropped.
            extras = [n for n in ("data-code", RESULT_PROPERTY) if n in attributes]
            extras += markup.describe()
            if extras:
                diagnostics.append(
                    f"{where}: has {CODE_PROPERTY} and also {_join(extras)}; "
                    "put each piece of evidence and each claim in its own shape"
                    + _html_note(cell, markup)
                )
            else:
                code.append(f"{comment}\n{_code_element(cell)}")
        elif "data-code" in attributes:
            if markup:
                diagnostics.append(
                    f"{where}: has data-code and also {_join(markup.describe())}; "
                    "put each piece of evidence and each claim in its own shape"
                    + (
                        f", with the value in {RESULT_PROPERTY}"
                        if markup.result
                        else ""
                    )
                    + _html_note(cell, markup)
                )
            elif LEGACY_RESULT_PROPERTY in attributes and (
                RESULT_PROPERTY not in attributes
            ):
                diagnostics.append(
                    f"{where}: has a {LEGACY_RESULT_PROPERTY!r} property; "
                    f"the authored value now goes in {RESULT_PROPERTY!r}"
                )
            else:
                claims.append(f"{comment}\n<p>{_result_element(cell)}</p>")
        elif RESULT_PROPERTY in attributes:
            diagnostics.append(
                f"{where}: has a {RESULT_PROPERTY} property but no data-code, "
                "so the value has no evidence"
            )
        elif markup:
            # Agent-authored HTML labels. draw.io's sanitizer drops data-*
            # attributes when a person edits such a label in the editor.
            if not cell.html_label:
                diagnostics.append(
                    f"{where}: label contains Provedown markup but the shape "
                    "style lacks html=1, so draw.io shows it as literal text"
                )
            elif markup.unchecked:
                diagnostics.extend(
                    f"{where}: {problem}" for problem in markup.unchecked
                )
            elif markup.code and markup.result:
                diagnostics.append(
                    f"{where}: HTML label mixes evidence and claims; "
                    "split them into separate shapes"
                )
            elif markup.result:
                claims.append(f"{comment}\n{LABEL_WRAPPER}{label}</div>")
            else:
                # draw.io stores label line breaks as <br>; the parser rejects
                # tags nested in <code>, so turn them back into newlines. Labels
                # routed here hold only evidence, so the whole label is safe.
                code.append(f"{comment}\n{LABEL_WRAPPER}{_br_to_newline(label)}</div>")

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
    parser_diagnostics = _without_unclosed_code_cascade(parsed.diagnostics)
    for diagnostic in parser_diagnostics:
        match = None if keeps_source_lines else PARSER_LOCATION.match(diagnostic)
        if match:
            line, column = int(match["line"]), int(match["column"])
            diagnostic = f"{_drawio_location(html, line, origin, column)}: "
            diagnostic += match["message"]
        if diagnostic not in diagnostics:
            diagnostics.append(diagnostic)
    # With parser errors, "no claims" is a consequence rather than the cause.
    if claims == 0 and not parser_diagnostics:
        diagnostics.append(f"{origin}: no claims found")
    return Lowering(html=html, claims=claims, diagnostics=tuple(diagnostics))


def _without_unclosed_code_cascade(diagnostics: list[str]) -> list[str]:
    """Drop the nested-tag errors an unclosed ``<code>`` caused.

    An unclosed ``<code>`` swallows every later tag, with one error per tag in
    whichever cells follow. Only nested-tag errors at or after the position
    (line and column) where that block opened are part of the cascade; earlier
    ones come from another, properly closed block and are kept. Columns matter
    because an HTML label's whole content sits on one generated line. The
    parser reports at most one unclosed block, since it tracks a single open
    ``<code>``.
    """

    unclosed = [_diagnostic_position(d) for d in diagnostics if UNCLOSED_CODE in d]
    if not unclosed or unclosed[0] is None:
        return list(diagnostics)
    opened = unclosed[0]
    return [
        d
        for d in diagnostics
        if NESTED_TAG not in d or (_diagnostic_position(d) or (0, 0)) < opened
    ]


def _diagnostic_position(diagnostic: str) -> tuple[int, int] | None:
    match = DIAGNOSTIC_POSITION.match(diagnostic)
    return (int(match["line"]), int(match["column"])) if match else None


def _drawio_location(html: str, line: int, origin: str, column: int) -> str:
    """Describe ``line`` of generated draw.io HTML by page, cell and offset.

    An HTML label is emitted as ``<div>`` followed by the label, so on its
    first line the column is shifted back to count from the label's start.
    """

    lines = html.splitlines()[:line]
    for index in range(len(lines) - 1, -1, -1):
        match = CELL_COMMENT.fullmatch(lines[index].strip())
        if match:
            offset = line - (index + 1)
            if offset == 1 and lines[-1].startswith(LABEL_WRAPPER):
                column = max(1, column - len(LABEL_WRAPPER))
            return (
                f"{unescape(match['where'])} "
                f"(line {offset} of its block, column {column})"
            )
    return f"{origin} (generated HTML line {line}, column {column})"


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


@dataclass
class LabelMarkup:
    """The Provedown markup found in a draw.io label."""

    code: bool = False
    result: bool = False
    # Elements verify would not check: data-code without class="result", or
    # class="result" on a tag other than <span>.
    unchecked: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.code or self.result or bool(self.unchecked)

    def describe(self) -> list[str]:
        """Name what was found, for diagnostics."""

        found = []
        if self.code:
            found.append("a <code> label")
        if self.result:
            found.append('a class="result" label')
        found += self.unchecked
        return found


def _label_markup(label: str) -> LabelMarkup:
    """Find the Provedown markup in a label by parsing it as HTML.

    Parsing rather than pattern-matching accepts every spelling the core
    parser does (such as an unquoted ``class=result``). It also catches markup
    that verify would silently ignore: a ``data-code`` element whose result
    class is missing or misspelled, and ``class="result"`` on a tag other than
    ``<span>``.
    """

    scanner = _LabelScanner()
    scanner.feed(label)
    scanner.close()
    return scanner.markup


class _LabelScanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.markup = LabelMarkup()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "code":
            self.markup.code = True
        problem = _unchecked_markup(tag, attrs, LABEL_RESULT_TAGS)
        if problem:
            self.markup.unchecked.append(problem)
        elif _is_result(attrs):
            self.markup.result = True

    handle_startendtag = handle_starttag


def _unchecked_markup(
    tag: str, attrs: list[tuple[str, str | None]], result_tags: set[str]
) -> str | None:
    """Describe markup on this element that verify would silently skip."""

    if _is_result(attrs) and tag not in result_tags:
        allowed = " or ".join(f"<{t}>" for t in sorted(result_tags))
        return f'class="result" on <{tag}>, which is only checked on {allowed}'
    if "data-code" in dict(attrs) and not _is_result(attrs):
        return f'data-code on <{tag}> without class="result", so it is not checked'
    return None


def _join(items: list[str]) -> str:
    """Join one or more names as "a", "a and b" or "a, b and c"."""

    if not items:
        raise ValueError("_join needs at least one item")
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _html_note(cell: Cell, markup: LabelMarkup) -> str:
    if markup and not cell.html_label:
        return "; its style also lacks html=1, so draw.io shows the label as text"
    return ""


def _br_to_newline(label: str) -> str:
    return re.sub(r"<br\s*/?>", "\n", label, flags=re.IGNORECASE)


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
        # Stack depth at which a provedown-ignore region opened, if inside one.
        self._ignored_from: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or ""
        self._check_unchecked_markup(tag, attrs)
        if (
            self._ignored_from is None
            and tag not in HTML_VOID_ELEMENTS
            and _is_ignored_region(attrs)
        ):
            self._ignored_from = len(self._stack)
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
        if not _is_ignored_region(attrs):
            self._check_unchecked_markup(tag, attrs)
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
        if self._ignored_from is not None and len(self._stack) <= self._ignored_from:
            self._ignored_from = None
        if original.lower() != tag:
            self._error(f"unexpected </{tag}>")
        self._parts.append("</span>" if renamed else f"</{original}>")

    def _check_unchecked_markup(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # Markup that neither this rewriter nor the core parser would check
        # passes unverified, so report it, except inside ignored regions,
        # which verify skips too.
        if self._ignored_from is not None or _is_ignored_region(attrs):
            return
        problem = _unchecked_markup(tag, attrs, SVG_RESULT_TAGS)
        if problem:
            self._error(problem)

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


def _is_ignored_region(attrs: list[tuple[str, str | None]]) -> bool:
    # Mirrors the core parser's provedown-ignore check.
    values = dict(attrs)
    return (values.get("data-provedown-ignore") or "").lower() in {
        "1",
        "true",
        "yes",
    } or "provedown-ignore" in (values.get("class") or "").split()


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
