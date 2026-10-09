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
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

from provedown.model import DocumentEvent, ResultAssertion
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

    code: list[_Block] = []
    claims: list[_Block] = []
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
                code.append(_Block(f"{comment}\n{_code_element(cell)}"))
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
                prefix = f"{comment}\n<p>"
                claim = LabelClaim(attributes["data-code"].strip(), 1, 1, False)
                claims.append(
                    _Block(
                        f"{prefix}{_result_element(cell)}</p>",
                        [(claim, where, _end_position(prefix))],
                    )
                )
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
                    f"{where}: {problem}, which verify would not check"
                    for problem in markup.unchecked
                )
            elif markup.code and markup.result:
                diagnostics.append(
                    f"{where}: HTML label mixes evidence and claims; "
                    "split them into separate shapes"
                )
            elif markup.result:
                claims.append(_label_block(comment, where, label))
            else:
                # draw.io stores label line breaks as <br>; the parser rejects
                # tags nested in <code>, so turn them back into newlines. Labels
                # routed here hold only evidence (and perhaps ignored claims),
                # so the whole label is safe.
                code.append(_label_block(comment, where, _br_to_newline(label)))

    header = f"{GENERATED_HEADER} {escape(origin)} by diagram_to_provedown.py -->"
    html = header
    records: list[ClaimRecord] = []
    for block in [*code, *claims]:
        html += "\n\n"
        start = html.count("\n") + 1
        for claim, where, (line, column) in block.claims:
            records.append(
                ClaimRecord(
                    claim.code,
                    where,
                    claim.ignored,
                    (start + line - 1, column),
                )
            )
        html += block.text
    html += "\n"
    return _lowering(
        html, origin, diagnostics, keeps_source_lines=False, records=records
    )


@dataclass
class _Block:
    """A piece of generated HTML and the claims in it.

    Each claim carries where the author wrote it and its position within
    ``text``, which ``drawio_to_html`` shifts to the whole document's.
    """

    text: str
    claims: list[tuple[LabelClaim, str, tuple[int, int]]] = field(default_factory=list)


def _label_block(comment: str, where: str, label: str) -> _Block:
    prefix = f"{comment}\n{LABEL_WRAPPER}"
    prefix_line, prefix_column = _end_position(prefix)
    claims = []
    for claim in _label_markup(label).claims:
        if claim.line > 1:
            described = f"{where} (label line {claim.line}, column {claim.column})"
            position = (prefix_line + claim.line - 1, claim.column)
        else:
            described = f"{where} (label column {claim.column})"
            position = (prefix_line, prefix_column + claim.column - 1)
        claims.append((claim, described, position))
    return _Block(f"{prefix}{label}</div>", claims)


def _end_position(text: str) -> tuple[int, int]:
    """The 1-based line and column of the character that would follow text."""

    return text.count("\n") + 1, len(text) - text.rfind("\n")


def normalize_svg(source: str, origin: str = "<svg>") -> Lowering:
    """Rewrite SVG-native Provedown markup to the HTML contract in place."""

    source, source_column = _unwrap_cdata(source)
    # The header shares line 1 so line numbers still match the original SVG.
    header = f"{GENERATED_HEADER} {escape(origin)} by diagram_to_provedown.py -->"
    rewriter = _SvgResultRewriter(origin, source_column, len(header))
    rewriter.feed(source)
    rewriter.close()
    return _lowering(
        header + rewriter.output(),
        origin,
        rewriter.diagnostics,
        keeps_source_lines=True,
        records=rewriter.claims,
    )


def _unwrap_cdata(source: str) -> tuple[str, Callable[[int, int], int]]:
    """Replace CDATA sections with escaped text, keeping every line number.

    Returns the new text and a function mapping a 1-based (line, column) in it
    back to the column in the original, so messages cite the author's file.
    """

    parts: list[str] = []
    # Per line: (column in the new text, offset to add from that column on).
    shifts: dict[int, list[tuple[int, int]]] = {}
    end = 0
    for match in re.finditer(r"<!\[CDATA\[(.*?)\]\]>", source, flags=re.DOTALL):
        parts += [source[end : match.start()], escape(match[1], quote=False)]
        end = match.end()
        line, new_column = _end_position("".join(parts))
        _, old_column = _end_position(source[:end])
        shifts.setdefault(line, []).append((new_column, old_column - new_column))
    parts.append(source[end:])

    def source_column(line: int, column: int) -> int:
        offset = 0
        for start, shift in shifts.get(line, []):
            if column >= start:
                offset = shift
        return column + offset

    return "".join(parts), source_column


def _lowering(
    html: str,
    origin: str,
    diagnostics: list[str],
    *,
    keeps_source_lines: bool,
    records: list[ClaimRecord],
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
    # With parser errors, a claim mismatch is a consequence, not the cause.
    # Checked before "no claims found", so a diagram whose every claim was
    # dropped gets this explanation instead.
    mismatches = _claim_mismatches(parsed.events, records, origin)
    if mismatches and not parser_diagnostics:
        diagnostics += mismatches
    elif claims == 0 and not parser_diagnostics:
        diagnostics.append(f"{origin}: no claims found")
    return Lowering(html=html, claims=claims, diagnostics=tuple(diagnostics))


def _claim_mismatches(
    events: list[DocumentEvent], records: list[ClaimRecord], origin: str
) -> list[str]:
    """Describe where verify and the converter disagree on the claims.

    Claims are matched by their position in the generated HTML, which is
    unique per claim, so a claim gained in one region cannot hide one lost in
    another, even when the two share a data-code. Each message cites where the
    author wrote the first claim of its kind, and how many more follow.
    """

    checked = {
        (event.location.line, event.location.column)
        for event in events
        if isinstance(event, ResultAssertion)
    }
    known = {record.position for record in records}
    lost = [r for r in records if not r.ignored and r.position not in checked]
    gained = [r.where for r in records if r.ignored and r.position in checked]
    # A claim verify found where the converter recorded none; not expected,
    # but reported rather than trusted.
    gained += [
        f"{origin}: generated line {line}, column {column}"
        for line, column in sorted(checked - known)
    ]
    messages = []
    if lost:
        messages.append(
            f"{lost[0].where}: verify would skip this claim"
            + _and_more(len(lost) - 1)
            + "; most likely a void element such as <br> inside or carrying "
            "provedown-ignore, or an ignored region left open, makes verify "
            "skip everything after it"
        )
    if gained:
        # Only an end tag can make verify stop ignoring before the converter
        # does; every void-element skew makes verify ignore more, not less.
        messages.append(
            f"{gained[0]}: verify would check this claim inside an ignored "
            "region"
            + _and_more(len(gained) - 1)
            + "; most likely an end tag with no matching start tag, such as a "
            "stray </br>, makes verify stop ignoring early"
        )
    return messages


def _and_more(count: int) -> str:
    if count == 0:
        return ""
    return f" and {count} later {'one' if count == 1 else 'ones'}"


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


@dataclass(frozen=True)
class ClaimRecord:
    """A result element the converter emitted, for checking against verify."""

    code: str
    # Where the author wrote it, for messages: "file:line:col" or a cell.
    where: str
    # Inside a provedown-ignore region, so verify should not check it.
    ignored: bool
    # Line and column of its start tag in the generated HTML, where the core
    # parser reports it. Unique per claim, unlike data-code, so it is the key
    # claims are matched on.
    position: tuple[int, int]


@dataclass(frozen=True)
class LabelClaim:
    """A class="result" element in a draw.io label."""

    code: str
    line: int
    column: int
    # Inside a provedown-ignore region, so verify should not check it.
    ignored: bool


@dataclass
class LabelMarkup:
    """The Provedown markup found in a draw.io label."""

    code: bool = False
    # class="result" elements; only those outside ignored regions are checked.
    claims: list[LabelClaim] = field(default_factory=list)
    # Elements verify would not check: data-code without class="result", or
    # class="result" on a tag other than <span>.
    unchecked: list[str] = field(default_factory=list)

    @property
    def result(self) -> bool:
        """Whether the label has a claim verify should check."""

        return any(not claim.ignored for claim in self.claims)

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
    ``<span>``. Markup inside a ``provedown-ignore`` region is skipped, as
    verify skips it.
    """

    scanner = _LabelScanner()
    scanner.feed(label)
    scanner.close()
    return scanner.markup


class _LabelScanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.markup = LabelMarkup()
        self._regions = _IgnoredRegions()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._regions.enter(tag, attrs):
            self._record_ignored_claim(tag, attrs)
        else:
            self._classify(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._regions.self_closing(attrs):
            self._record_ignored_claim(tag, attrs)
        else:
            self._classify(tag, attrs)

    def _record_ignored_claim(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # Kept so a claim verify checks despite the region can be located.
        if tag in LABEL_RESULT_TAGS and _is_result(attrs):
            line, column = self.getpos()
            code = (dict(attrs).get("data-code") or "").strip()
            self.markup.claims.append(LabelClaim(code, line, column + 1, True))

    def handle_endtag(self, tag: str) -> None:
        self._regions.leave(tag)

    def _classify(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "code":
            self.markup.code = True
        shown = _tag_name(self.get_starttag_text() or "")
        problem = _unchecked_markup(tag, attrs, LABEL_RESULT_TAGS, shown)
        if problem:
            # The position keeps separate elements apart in the messages.
            line, column = self.getpos()
            where = f" at label column {column + 1}"
            if line > 1:
                where = f" at label line {line}, column {column + 1}"
            self.markup.unchecked.append(problem + where)
        elif _is_result(attrs):
            line, column = self.getpos()
            code = (dict(attrs).get("data-code") or "").strip()
            self.markup.claims.append(LabelClaim(code, line, column + 1, False))


class _IgnoredRegions:
    """Track whether a parser is inside a ``provedown-ignore`` region.

    Counts open elements, skipping HTML void elements such as ``<br>``, which
    never get an end tag. (The core parser counts every start tag, so a
    ``<br>`` inside an ignored region leaves it ignoring later content; see
    ``docs/ideas/diagram-markup.md``.)
    """

    def __init__(self) -> None:
        self._depth = 0
        self._ignored_from: int | None = None

    @property
    def ignoring(self) -> bool:
        return self._ignored_from is not None

    def enter(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        """Open an element; return whether it is ignored."""

        if tag in HTML_VOID_ELEMENTS:
            return self.ignoring or _is_ignored_region(attrs)
        if not self.ignoring and _is_ignored_region(attrs):
            self._ignored_from = self._depth
        self._depth += 1
        return self.ignoring

    def self_closing(self, attrs: list[tuple[str, str | None]]) -> bool:
        """Note a self-closing element; return whether it is ignored.

        It opens and closes at once, so it never changes the depth.
        """

        return self.ignoring or _is_ignored_region(attrs)

    def leave(self, tag: str) -> None:
        if tag in HTML_VOID_ELEMENTS or self._depth == 0:
            return
        self._depth -= 1
        if self._ignored_from is not None and self._depth <= self._ignored_from:
            self._ignored_from = None


def _unchecked_markup(
    tag: str,
    attrs: list[tuple[str, str | None]],
    result_tags: set[str],
    shown_tag: str | None = None,
) -> str | None:
    """Name markup on this element that verify would silently skip."""

    shown = shown_tag or tag
    if _is_result(attrs) and tag not in result_tags:
        allowed = _join([f"<{t}>" for t in sorted(result_tags)], "or")
        return f'class="result" on <{shown}> (only checked on {allowed})'
    if "data-code" in dict(attrs) and not _is_result(attrs):
        return f'data-code on <{shown}> without class="result"'
    return None


def _join(items: list[str], conjunction: str = "and") -> str:
    """Join one or more names as "a", "a and b" or "a, b and c"."""

    if not items:
        raise ValueError("_join needs at least one item")
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {conjunction} {items[-1]}"


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

    def __init__(
        self,
        origin: str,
        source_column: Callable[[int, int], int],
        header_length: int,
    ) -> None:
        super().__init__(convert_charrefs=False)
        self.origin = origin
        self.diagnostics: list[str] = []
        self._source_column = source_column
        self._parts: list[str] = []
        # Where the next output character lands, after the header on line 1.
        self._line = 1
        self._column = header_length + 1
        # Original (case-preserved) tag name and whether it became a span.
        self._stack: list[tuple[str, bool]] = []
        self._regions = _IgnoredRegions()
        # Every result element, with whether it sits in an ignored region.
        self.claims: list[ClaimRecord] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or ""
        if self._regions.enter(tag, attrs):
            self._record_claim(tag, attrs, ignored=True)
        else:
            self._check_markup(tag, attrs, raw)
        if tag in {"text", "tspan"} and _is_result(attrs):
            self._stack.append((tag, True))
            self._emit(_rename_tag(raw, "span"))
            return
        if tag in HTML_VOID_ELEMENTS:
            self._emit(raw)
        else:
            self._stack.append((_tag_name(raw) or tag, False))
            self._emit(raw)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or ""
        if self._regions.self_closing(attrs):
            self._record_claim(tag, attrs, ignored=True)
        else:
            self._check_markup(tag, attrs, raw)
        if tag in {"text", "tspan"} and _is_result(attrs):
            raw = _rename_tag(raw, "span")
        self._emit(raw)

    def handle_endtag(self, tag: str) -> None:
        self._regions.leave(tag)
        if tag in HTML_VOID_ELEMENTS:
            # Void start tags are never pushed, so an end tag such as the
            # XML-style <br></br> closes nothing on the stack. Only one
            # outside any element is worth reporting.
            if not self._stack:
                self._error(f"unexpected </{tag}> with no open element")
            self._emit(f"</{tag}>")
            return
        if not self._stack:
            self._error(f"unexpected </{tag}> with no open element")
            self._emit(f"</{tag}>")
            return
        original, renamed = self._stack.pop()
        if original.lower() != tag:
            self._error(f"unexpected </{tag}>")
        self._emit("</span>" if renamed else f"</{original}>")

    def _check_markup(
        self, tag: str, attrs: list[tuple[str, str | None]], raw: str
    ) -> None:
        # Called only outside ignored regions, which verify skips too. Markup
        # that neither this rewriter nor the core parser would check passes
        # unverified, so report it; count the rest as claims verify should see.
        problem = _unchecked_markup(tag, attrs, SVG_RESULT_TAGS, _tag_name(raw))
        if problem:
            self._error(f"{problem}, which verify would not check")
        else:
            self._record_claim(tag, attrs, ignored=False)

    def _record_claim(
        self, tag: str, attrs: list[tuple[str, str | None]], *, ignored: bool
    ) -> None:
        if tag in SVG_RESULT_TAGS and _is_result(attrs):
            code = (dict(attrs).get("data-code") or "").strip()
            position = (self._line, self._column)
            self.claims.append(ClaimRecord(code, self._where(), ignored, position))

    def _error(self, message: str) -> None:
        self.diagnostics.append(f"{self._where()}: {message}")

    def _where(self) -> str:
        line, column = self.getpos()
        return f"{self.origin}:{line}:{self._source_column(line, column + 1)}"

    def handle_data(self, data: str) -> None:
        self._emit(data)

    def handle_entityref(self, name: str) -> None:
        self._emit(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._emit(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._emit(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._emit(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._emit(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self._emit(f"<![{data}]>")

    def _emit(self, text: str) -> None:
        self._parts.append(text)
        if "\n" in text:
            self._line += text.count("\n")
            self._column = len(text) - text.rfind("\n")
        else:
            self._column += len(text)

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
