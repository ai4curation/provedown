"""Parser for the Provedown HTML contract in Markdown or HTML documents."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml

from provedown.model import (
    CodeBlock,
    CodeUse,
    Document,
    DocumentEvent,
    ProvedownConfig,
    QuoteClaim,
    ResultAssertion,
    SourceLocation,
)

# A reference id in citation text: a CURIE-like ``prefix:local`` token such as
# ``PMID:18467591``, ``DOI:10.1016/...``, ``Reactome:R-HSA-75899`` or
# ``file:genes/x.txt``. Commas and semicolons separate ids from each other and
# from the quote, so they never belong to one.
# Markdown code and emphasis markers around an id (`PMID:1`, **PMID:1**,
# _PMID:1_) are not part of it, so they are excluded from the body or trimmed.
_SOURCE_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9/:.-])[A-Za-z][\w.-]*:[^\s,;\[\]`*]+"
)
_VALID_SOURCE_ID = re.compile(r"[A-Za-z][\w.-]*:[\w.\-/():#%+=&?@]*[\w/)#]")
# The target of a Markdown link, ``[text](target "title")``: the id is the link
# text. A target may hold one level of balanced parentheses, as DOIs often do.
_MARKDOWN_LINK_TARGET = re.compile(
    r'\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+"[^"]*")?\)'
)
# A bare link (http, ftp, mailto) is where a source lives, not a reference id
# for it; a URL source is written with a ``url:`` prefix.
_WEB_LINK_PREFIXES = frozenset({"http", "https", "ftp", "mailto"})
_SOURCE_ID_TRAILING = ".:_"
_CLOSING_BRACKETS = {")": "(", "]": "[", "}": "{"}
# Start tags that, skipped inside an ignored region, lose markup that would
# otherwise be parsed: quotations, citations and code.
_SWALLOWABLE_TAGS = frozenset({"q", "blockquote", "cite", "figure", "code"})


def _is_swallowable(tag: str, attr_map: Mapping[str, str]) -> bool:
    """Whether skipping this start tag loses markup that would be parsed."""

    is_result = tag == "span" and _has_class(attr_map, "result")
    return tag in _SWALLOWABLE_TAGS or is_result


# Elements whose boundaries separate words in quoted and citation text.
_QUOTE_WORD_BREAK_TAGS = frozenset(
    {"br", "p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}
)


class ParseError(ValueError):
    """Raised when source cannot be parsed into a coherent Provedown document."""


@dataclass
class _CodeBuilder:
    location: SourceLocation
    name: str | None
    language: str
    attributes: Mapping[str, str]
    parts: list[str] = field(default_factory=list)

    def build(self) -> CodeBlock:
        return CodeBlock(
            code="".join(self.parts).strip("\n"),
            location=self.location,
            name=self.name,
            language=self.language,
            attributes=self.attributes,
        )


@dataclass
class _ResultBuilder:
    location: SourceLocation
    code: str
    compare: str
    language: str
    attributes: Mapping[str, str]
    span_depth: int = 1
    method_depth: int = 0
    parts: list[str] = field(default_factory=list)

    def build(self) -> ResultAssertion:
        return ResultAssertion(
            authored="".join(self.parts).strip(),
            code=self.code,
            compare=self.compare,
            language=self.language,
            location=self.location,
            attributes=self.attributes,
        )


@dataclass
class _QuoteBuilder:
    location: SourceLocation
    element: str
    owner: _CiteBuilder | _FigureBuilder | None
    depth: int = 1
    parts: list[str] = field(default_factory=list)
    unclosed: bool = False
    citation_unclosed: bool = False
    contains_executable_markup: bool = False

    def build(
        self,
        citation: str | None = None,
        citation_location: SourceLocation | None = None,
        citation_executable: bool = False,
    ) -> QuoteClaim:
        sources, rejected = (
            _source_id_candidates(citation) if citation is not None else ((), ())
        )
        return QuoteClaim(
            text=_collapse_whitespace("".join(self.parts)),
            location=self.location,
            element=self.element,
            citation=citation,
            citation_location=citation_location,
            sources=sources,
            rejected_sources=rejected,
            unclosed=self.unclosed,
            citation_unclosed=self.citation_unclosed,
            contains_executable_markup=(
                self.contains_executable_markup or citation_executable
            ),
        )


@dataclass
class _CiteBuilder:
    location: SourceLocation
    parts: list[str] = field(default_factory=list)
    quotes: list[_QuoteBuilder] = field(default_factory=list)
    contains_executable_markup: bool = False
    # The tag of an ignore-marked element of its own kind opened inside it.
    ignored_own_kind: str = ""
    # An ignored region inside it ended on another element's end tag.
    ignored_region_leaked: bool = False

    @property
    def text(self) -> str:
        return _collapse_whitespace("".join(self.parts))


@dataclass
class _FigureBuilder:
    location: SourceLocation
    caption_depth: int = 0
    quotes: list[_QuoteBuilder] = field(default_factory=list)
    captions: list[_CiteBuilder] = field(default_factory=list)
    # The tag of an ignore-marked element of its own kind opened inside it.
    ignored_own_kind: str = ""
    # An ignored region inside it ended on another element's end tag.
    ignored_region_leaked: bool = False


@dataclass(frozen=True)
class _Frontmatter:
    data: Mapping[str, Any] = field(default_factory=dict)
    provedown: ProvedownConfig = field(default_factory=ProvedownConfig)
    diagnostics: list[str] = field(default_factory=list)
    end_line: int = 0


class _ProvedownHTMLParser(HTMLParser):
    def __init__(
        self,
        source: str,
        path: Path | None,
        default_language: str,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.path = path
        self.default_language = default_language
        self.events: list[DocumentEvent] = []
        self.named_code: dict[str, CodeBlock] = {}
        self.diagnostics: list[str] = []
        self._code: _CodeBuilder | None = None
        self._results: list[_ResultBuilder] = []
        self._ignore_depth = 0
        # Set while a parse_* override copies a markup span into open code, so
        # a nested parse_* call (end tag -> bogus comment) does not copy twice.
        self._keeping_in_code = False
        self._ignore_location: SourceLocation | None = None
        # The quote or citation markup the current ignored region began in, the
        # end tags that can end it, and how many of those were opened inside the
        # region, so the owner's own end tag still closes it if the region was
        # left open; that region is then reported as unclosed.
        self._ignore_owner: _QuoteBuilder | _CiteBuilder | _FigureBuilder | None = None
        self._ignore_owner_ends: frozenset[str] = frozenset()
        self._ignored_owner_tags: dict[str, int] = {}
        self._ignore_opening_tag = ""
        # The owner-kind end tag the region consumed, if any.
        self._region_took_owner_end_tag = ""
        # Whether the region's own end tag came while an owner-kind element
        # opened inside it was still open.
        self._region_closed_over_owner_kind = False
        # Whether the current region skipped markup that would otherwise be
        # parsed: a quotation, citation, code block or result span.
        self._region_skipped_markup = False
        self.quotes: list[QuoteClaim] = []
        self._quote: _QuoteBuilder | None = None
        self._quote_containers: list[_CiteBuilder | _FigureBuilder] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: Sequence[tuple[str, str | None]],
    ) -> None:
        attr_map = _attrs_to_dict(attrs)
        location = self._location()

        if self._ignore_depth > 0:
            self._ignore_depth += 1
            if tag in _QUOTE_WORD_BREAK_TAGS:
                self._append_quotation_text(" ")
            if self._ignore_owner is not None and tag in self._ignore_owner_ends:
                # Counted, so its own end tag is accounted for: not skipped markup.
                self._ignored_owner_tags[tag] = self._ignored_owner_tags.get(tag, 0) + 1
            elif _is_swallowable(tag, attr_map):
                self._region_skipped_markup = True
            return

        if self._code is not None:
            # Checked before the ignore marker: nothing inside code is markup.
            self.diagnostics.append(
                f"{location.display()}: nested HTML tag inside <code> was ignored"
            )
            return

        if _is_ignored_region(attr_map):
            if tag in _QUOTE_WORD_BREAK_TAGS:
                self._append_quotation_text(" ")
            self._start_ignored_region(tag, location)
            return

        if tag == "code":
            self._mark_executable_in_quote()
            self._start_code(attr_map, location)
            return

        self._start_quote_markup(tag, location)

        if tag == "span" and self._results:
            self._results[-1].span_depth += 1
            if _has_class(attr_map, "method"):
                self._results[-1].method_depth += 1

        if tag == "span" and _has_class(attr_map, "result"):
            self._start_result(attr_map, location)

    def handle_startendtag(
        self,
        tag: str,
        attrs: Sequence[tuple[str, str | None]],
    ) -> None:
        attr_map = _attrs_to_dict(attrs)
        location = self._location()

        if self._ignore_depth > 0:
            # Ignored markup still separates the visible words around it.
            if tag in _QUOTE_WORD_BREAK_TAGS:
                self._append_quotation_text(" ")
            if _is_swallowable(tag, attr_map):
                self._region_skipped_markup = True
            return

        if self._code is not None:
            # Like any other tag inside code: no event, and a blocking diagnostic.
            self.diagnostics.append(
                f"{location.display()}: nested HTML tag inside <code> was ignored"
            )
            return

        if tag in _QUOTE_WORD_BREAK_TAGS:
            self._append_quotation_text(" ")

        if _is_ignored_region(attr_map):
            return

        if tag == "code":
            self._mark_executable_in_quote()
            if "use" in attr_map:
                self._append_code_use(attr_map, location)
            else:
                self._append_code_block(
                    CodeBlock(
                        code="",
                        location=location,
                        name=_empty_to_none(attr_map.get("name")),
                        language=_language(attr_map, self.default_language),
                        attributes=attr_map,
                    )
                )
            return

        if tag == "span" and _has_class(attr_map, "result"):
            self._start_result(attr_map, location)
            self._finish_result()

    def handle_data(self, data: str) -> None:
        # Visible text belongs to a quote or citation around it, even inside an
        # ignored region or a code block: the ignore marker keeps markup out of
        # the executable contract, never words out of a verbatim quote.
        self._append_quotation_text(data)

        if self._ignore_depth > 0:
            return

        if self._code is not None:
            self._code.parts.append(data)
            return

        if self._results and self._results[-1].method_depth == 0:
            self._results[-1].parts.append(data)

    # End tags, comments, declarations and processing instructions inside
    # <code> are code text, exactly as written: dropping one would turn a check
    # on "</p>" or "<!-- x -->" into a check on "". The base parser hands these
    # to handlers without their source text (or, for "</>", to no handler), so
    # these overrides of internal HTMLParser hooks copy the span it consumed.
    # Tests pin "</P >", "</>", "</ p>", comments, declarations and PIs.

    def parse_endtag(self, i: int) -> int:
        return self._keep_in_code(super().parse_endtag, i)

    def parse_comment(self, i: int, report: bool = True) -> int:
        return self._keep_in_code(
            lambda j: HTMLParser.parse_comment(self, j, report), i
        )

    def parse_bogus_comment(self, i: int, report: bool = True) -> int:
        return self._keep_in_code(
            lambda j: HTMLParser.parse_bogus_comment(self, j, report), i
        )

    def parse_html_declaration(self, i: int) -> int:
        return self._keep_in_code(super().parse_html_declaration, i)

    def parse_pi(self, i: int) -> int:
        return self._keep_in_code(super().parse_pi, i)

    def _keep_in_code(self, parse: Callable[[int], int], i: int) -> int:
        if self._keeping_in_code:
            return parse(i)
        code_before = self._code
        self._keeping_in_code = True
        try:
            end = parse(i)
        finally:
            self._keeping_in_code = False
        # Not for the </code> that closes the block, which ends the code.
        if end > i and code_before is not None and self._code is code_before:
            code_before.parts.append(self.rawdata[i:end])
        return end

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")

    def handle_endtag(self, tag: str) -> None:
        if self._ignore_depth > 0:
            if self._is_owner_end_tag(tag):
                # The quote or citation the region began in ends here while the
                # region is still open: end the region too, and report it.
                self._report_unclosed_ignored_region()
                self._end_ignored_region()
            else:
                if (
                    tag == self._ignore_opening_tag
                    and tag not in self._ignore_owner_ends
                    and any(self._ignored_owner_tags.values())
                ):
                    # The region's own end tag, while an owner-kind element
                    # opened inside it is still open: that element's end tag,
                    # when it comes, is most likely the owner's.
                    self._region_closed_over_owner_kind = True
                if self._ignored_owner_tags.get(tag, 0) > 0:
                    # It closes the same tag opened inside the region. If that
                    # element lacked its own end tag, this is the owner's; what
                    # that loses is decided when the region ends.
                    self._ignored_owner_tags[tag] -= 1
                    if (
                        tag == self._ignore_opening_tag
                        or self._region_closed_over_owner_kind
                    ):
                        self._region_took_owner_end_tag = tag
                self._ignore_depth -= 1
                if self._ignore_depth == 0:
                    self._mark_owner_losses(tag)
                    self._end_ignored_region()
                if tag in _QUOTE_WORD_BREAK_TAGS:
                    self._append_quotation_text(" ")
                return

        if tag == "code" and self._code is not None:
            code = self._code.build()
            self._code = None
            self._append_code_block(code)
            return

        if self._code is not None:
            # Code text; parse_endtag copies its exact source span.
            return

        self._end_quote_markup(tag)

        if tag == "span" and self._results:
            current = self._results[-1]
            if current.method_depth > 0:
                current.method_depth -= 1
            current.span_depth -= 1
            if current.span_depth <= 0:
                self._finish_result()

    def close(self) -> None:
        super().close()
        if self._ignore_depth > 0:
            # Everything after it was skipped, so nothing there was checked.
            self._report_unclosed_ignored_region()
        if self._code is not None:
            self.diagnostics.append(
                f"{self._code.location.display()}: unclosed <code> block"
            )
            code = self._code.build()
            self._code = None
            self._append_code_block(code)
        while self._results:
            result = self._results[-1]
            self.diagnostics.append(
                f"{result.location.display()}: unclosed result span"
            )
            self._finish_result()
        # Unclosed quote markup is reported by lint rather than as a parser
        # diagnostic, so it never blocks the document's executable checks.
        if self._quote is not None:
            self._quote.unclosed = True
            self._finish_quote()
        while self._quote_containers:
            container = self._quote_containers[-1]
            kind = container.ignored_own_kind
            if kind and not container.quotes:
                # No quotation can carry the unclosed-citation lint: its end tag
                # most likely closed an ignored element of the same kind that
                # lacked one, so what the region skipped was lost.
                outer = "cite" if isinstance(container, _CiteBuilder) else "figure"
                self.diagnostics.append(
                    f"{container.location.display()}: unclosed <{outer}> holding "
                    f"no quotation; most likely a <{kind}> in an ignored region "
                    "inside it has no end tag"
                )
            # An unclosed container is reported above, or by lint through its
            # quotations; finishing it below must not report it again.
            container.ignored_region_leaked = False
            for quote in container.quotes:
                # An unclosed quote already says its text is untrustworthy.
                quote.citation_unclosed = not quote.unclosed
            self._finish_quote_container()

    def _start_quote_markup(self, tag: str, location: SourceLocation) -> None:
        """Track the elements that make up a cited quotation.

        Markup inside an open quote is part of the quoted text, so only a
        nested quote of the same element is tracked there, to find its end.
        Even a ``</cite>`` or ``</figure>`` end tag does not close an open
        quote: a stray end tag cannot be told apart from a missing ``</q>``
        without reading ahead, and treating it as quoted text never truncates
        the quote. A quote whose end tag is missing runs to the end of the
        document and is marked ``unclosed``.
        """

        if tag in _QUOTE_WORD_BREAK_TAGS:
            self._append_quotation_text(" ")

        if self._quote is not None:
            if tag == self._quote.element:
                self._quote.depth += 1
            return

        if tag in {"q", "blockquote"}:
            owner = self._quote_containers[-1] if self._quote_containers else None
            self._quote = _QuoteBuilder(location=location, element=tag, owner=owner)
        elif tag == "cite":
            self._quote_containers.append(_CiteBuilder(location=location))
        elif tag == "figure":
            self._quote_containers.append(_FigureBuilder(location=location))
        elif tag == "figcaption" and self._quote_containers:
            container = self._quote_containers[-1]
            if isinstance(container, _FigureBuilder):
                container.caption_depth += 1

    def _end_quote_markup(self, tag: str) -> None:
        if tag in _QUOTE_WORD_BREAK_TAGS:
            self._append_quotation_text(" ")

        if self._quote is not None:
            if tag == self._quote.element:
                self._quote.depth -= 1
                if self._quote.depth == 0:
                    self._finish_quote()
            return

        if not self._quote_containers:
            return
        container = self._quote_containers[-1]
        if _closes_container(tag, container):
            if (
                isinstance(container, _FigureBuilder)
                and container.caption_depth > 0
                and container.ignored_own_kind == "figcaption"
            ):
                # An ignored <figcaption> took the caption's end tag, and the
                # caption's citation was skipped with it.
                self.diagnostics.append(
                    f"{container.location.display()}: unclosed <figcaption>; "
                    "most likely a <figcaption> in an ignored region inside it "
                    "has no end tag"
                )
                # Reported once: finishing it below must not report it again.
                container.ignored_region_leaked = False
            self._finish_quote_container()
        elif (
            tag == "figcaption"
            and isinstance(container, _FigureBuilder)
            and container.caption_depth > 0
        ):
            container.caption_depth -= 1

    def _finish_quote(self) -> None:
        assert self._quote is not None
        quote = self._quote
        self._quote = None
        if quote.owner is None:
            self.quotes.append(quote.build())
        else:
            quote.owner.quotes.append(quote)

    def _finish_quote_container(self) -> None:
        container = self._quote_containers.pop()
        if container.ignored_region_leaked:
            # A leaked ignored region skipped quotation markup; a stray end tag
            # closed the container after the region took the real one. Any
            # quotation that survived carries no lint for the ones lost.
            kind = "cite" if isinstance(container, _CiteBuilder) else "figure"
            self.diagnostics.append(
                f"{container.location.display()}: <{kind}> lost the quotation "
                "markup an ignored region inside it skipped; most likely an "
                "element in that region has no end tag"
            )
        if isinstance(container, _CiteBuilder):
            for quote in container.quotes:
                self.quotes.append(
                    quote.build(
                        container.text,
                        container.location,
                        container.contains_executable_markup,
                    )
                )
            parent = self._quote_containers[-1] if self._quote_containers else None
            if isinstance(parent, _FigureBuilder) and parent.caption_depth > 0:
                parent.captions.append(container)
            elif isinstance(parent, _CiteBuilder):
                # A nested citation's text is part of the enclosing citation,
                # kept apart from the words around it.
                parent.parts.append(f" {container.text} ")
            return

        citation = (
            " ".join(caption.text for caption in container.captions)
            if container.captions
            else None
        )
        citation_location = (
            container.captions[0].location if container.captions else None
        )
        citation_executable = any(
            caption.contains_executable_markup for caption in container.captions
        )
        for quote in container.quotes:
            self.quotes.append(
                quote.build(citation, citation_location, citation_executable)
            )

    def _start_code(
        self,
        attr_map: Mapping[str, str],
        location: SourceLocation,
    ) -> None:
        if "use" in attr_map:
            self._append_code_use(attr_map, location)
            return

        self._code = _CodeBuilder(
            location=location,
            name=_empty_to_none(attr_map.get("name")),
            language=_language(attr_map, self.default_language),
            attributes=attr_map,
        )

    def _start_ignored_region(self, tag: str, location: SourceLocation) -> None:
        self._ignore_depth = 1
        self._ignore_location = location
        self._ignore_opening_tag = tag
        if self._quote is not None:
            self._ignore_owner = self._quote
            self._ignore_owner_ends = frozenset({self._quote.element})
        elif self._quote_containers:
            container = self._quote_containers[-1]
            self._ignore_owner = container
            if isinstance(container, _CiteBuilder):
                self._ignore_owner_ends = frozenset({"cite"})
            elif container.caption_depth > 0:
                # Inside a caption, its end tag comes first, but the figure's
                # still ends the region if the caption's is missing.
                self._ignore_owner_ends = frozenset({"figcaption", "figure"})
            else:
                self._ignore_owner_ends = frozenset({"figure"})
        else:
            self._ignore_owner = None
            self._ignore_owner_ends = frozenset()
        # The opening element counts too when it is of the owner's own kind, so
        # its end tag is not taken for the owner's.
        self._ignored_owner_tags = {tag: 1} if tag in self._ignore_owner_ends else {}
        self._region_skipped_markup = False
        self._region_took_owner_end_tag = ""
        self._region_closed_over_owner_kind = False

    def _mark_owner_losses(self, ending_tag: str) -> None:
        """Record on the owner container what a region that took its end tag lost.

        Only a region that skipped markup lost anything. Its owner may still be
        reported at the end of the document (``ignored_own_kind``) or, if the
        region ended on another element's end tag so its own was taken earlier,
        even when a stray end tag closes the owner later (``ignored_region_leaked``).
        """

        owner = self._ignore_owner
        took = self._region_took_owner_end_tag
        if not took or not self._region_skipped_markup:
            return
        if isinstance(owner, _QuoteBuilder | None):
            return
        owner.ignored_own_kind = took
        if ending_tag != self._ignore_opening_tag:
            owner.ignored_region_leaked = True

    def _end_ignored_region(self) -> None:
        self._ignore_depth = 0
        self._ignore_location = None
        self._ignore_owner = None
        self._ignore_owner_ends = frozenset()
        self._ignored_owner_tags = {}
        self._region_skipped_markup = False
        self._ignore_opening_tag = ""
        self._region_took_owner_end_tag = ""
        self._region_closed_over_owner_kind = False

    def _is_owner_end_tag(self, tag: str) -> bool:
        """Whether ``tag`` ends the markup the current ignored region began in."""

        owner = self._ignore_owner
        if owner is None or tag not in self._ignore_owner_ends:
            return False
        if self._ignored_owner_tags.get(tag, 0) > 0:
            return False
        if isinstance(owner, _QuoteBuilder):
            return owner is self._quote
        return bool(self._quote_containers) and owner is self._quote_containers[-1]

    def _report_unclosed_ignored_region(self) -> None:
        assert self._ignore_location is not None
        self.diagnostics.append(
            f"{self._ignore_location.display()}: unclosed ignored region; "
            "most likely a void element such as <br> inside or carrying the "
            "ignore marker, which counts as an open element, or a missing end tag"
        )

    def _append_quotation_text(self, text: str) -> None:
        """Add visible text to the open quote, or else to the open citation."""

        if self._quote is not None:
            self._quote.parts.append(text)
        elif self._quote_containers and isinstance(
            self._quote_containers[-1], _CiteBuilder
        ):
            self._quote_containers[-1].parts.append(text)

    def _mark_executable_in_quote(self) -> None:
        """Record executable markup inside the open quote or citation text.

        Quote markup never changes what is executable: a ``<code>`` or result
        span runs wherever it is. This only lets lint warn about it, since
        quoted code is better marked up with ``<samp>`` and an id should not be
        executable code.
        """

        if self._quote is not None:
            self._quote.contains_executable_markup = True
        elif self._quote_containers and isinstance(
            self._quote_containers[-1], _CiteBuilder
        ):
            self._quote_containers[-1].contains_executable_markup = True

    def _append_code_use(
        self,
        attr_map: Mapping[str, str],
        location: SourceLocation,
    ) -> None:
        name = attr_map.get("use", "").strip()
        if not name:
            self.diagnostics.append(f"{location.display()}: empty code use")
            return
        self.events.append(
            CodeUse(
                name=name,
                location=location,
                language=_language(attr_map, self.default_language),
                attributes=attr_map,
            )
        )

    def _append_code_block(self, code: CodeBlock) -> None:
        self.events.append(code)
        if code.name is None:
            return
        if code.name in self.named_code:
            self.diagnostics.append(
                f"{code.location.display()}: duplicate code block name "
                f"{code.name!r}; later definition wins"
            )
        self.named_code[code.name] = code

    def _start_result(
        self,
        attr_map: Mapping[str, str],
        location: SourceLocation,
    ) -> None:
        self._mark_executable_in_quote()
        code = attr_map.get("data-code", "").strip()
        if not code:
            self.diagnostics.append(
                f"{location.display()}: result span missing data-code"
            )
        self._results.append(
            _ResultBuilder(
                location=location,
                code=code,
                compare=_compare_policy(attr_map),
                language=_language(attr_map, self.default_language),
                attributes=attr_map,
            )
        )

    def _finish_result(self) -> None:
        result = self._results.pop().build()
        self.events.append(result)

    def _location(self) -> SourceLocation:
        line, column = self.getpos()
        return SourceLocation(path=self.path, line=line, column=column + 1)


def parse_document(source: str, path: Path | None = None) -> Document:
    """Parse a Markdown or HTML document containing Provedown HTML contracts."""

    frontmatter = _extract_frontmatter(source, path)
    parser = _ProvedownHTMLParser(
        source=source,
        path=path,
        default_language=frontmatter.provedown.default_language,
    )
    parser.diagnostics.extend(frontmatter.diagnostics)
    try:
        masked = _mask_markdown_fenced_code(
            _mask_frontmatter(source, frontmatter.end_line)
        )
        parser.feed(masked)
        parser.close()
    except Exception as exc:  # pragma: no cover - HTMLParser is broad by design.
        raise ParseError(str(exc)) from exc

    return Document(
        source=source,
        path=path,
        events=parser.events,
        named_code=parser.named_code,
        frontmatter=frontmatter.data,
        provedown=frontmatter.provedown,
        diagnostics=parser.diagnostics,
        quotes=sorted(
            parser.quotes,
            key=lambda quote: (quote.location.line, quote.location.column),
        ),
    )


def parse_file(path: Path) -> Document:
    return parse_document(path.read_text(encoding="utf-8"), path=path)


def source_ids(citation: str) -> tuple[str, ...]:
    """Return the reference ids named in a citation's text, in order.

    >>> source_ids("PMID:18467591,")
    ('PMID:18467591',)
    >>> source_ids("Smith et al. (DOI:10.1016/S0092-8674(00)81141-4).")
    ('DOI:10.1016/S0092-8674(00)81141-4',)
    >>> source_ids("PMID:1; Reactome:R-HSA-75899 and file:genes/x.txt")
    ('PMID:1', 'Reactome:R-HSA-75899', 'file:genes/x.txt')
    >>> source_ids("[PMID:123](https://pubmed.ncbi.nlm.nih.gov/123/),")
    ('PMID:123',)
    >>> source_ids("PMID:1 (https://pubmed.ncbi.nlm.nih.gov/1/)")
    ('PMID:1',)
    >>> source_ids("Smith 2020, 10:30, Figure:.")
    ()
    """

    return _source_id_candidates(citation)[0]


def _source_id_candidates(citation: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split a citation's id-shaped tokens into valid ids and rejected ones.

    A web link is neither: it is where a source lives, so it is skipped. A
    rejected token looks like an id but holds a character an id cannot, such
    as leftover markup; lint names it so the author can see what was refused.
    """

    valid: list[str] = []
    rejected: list[str] = []
    for match in _SOURCE_ID_PATTERN.finditer(_MARKDOWN_LINK_TARGET.sub("]", citation)):
        candidate = _trim_source_id(match.group(0))
        if candidate.split(":", 1)[0].lower() in _WEB_LINK_PREFIXES:
            continue
        if _VALID_SOURCE_ID.fullmatch(candidate):
            valid.append(candidate)
        elif ":" in candidate and candidate.split(":", 1)[1]:
            rejected.append(candidate)
    # A repeated id names the same source once.
    return tuple(dict.fromkeys(valid)), tuple(dict.fromkeys(rejected))


def _trim_source_id(token: str) -> str:
    """Drop sentence punctuation and unbalanced closing brackets from an id."""

    while token:
        last = token[-1]
        unbalanced = last in _CLOSING_BRACKETS and token.count(last) > token.count(
            _CLOSING_BRACKETS[last]
        )
        if last not in _SOURCE_ID_TRAILING and not unbalanced:
            break
        token = token[:-1]
    return token


def _closes_container(tag: str, container: _CiteBuilder | _FigureBuilder) -> bool:
    if isinstance(container, _CiteBuilder):
        return tag == "cite"
    return tag == "figure"


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _extract_frontmatter(source: str, path: Path | None) -> _Frontmatter:
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return _Frontmatter()

    closing_line = _frontmatter_closing_line(lines)
    if closing_line is None:
        return _Frontmatter(
            diagnostics=[
                f"{_frontmatter_location(path).display()}: "
                "unterminated YAML frontmatter block"
            ],
            end_line=len(lines),
        )

    diagnostics: list[str] = []
    text = "".join(lines[1:closing_line])
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: invalid YAML frontmatter: "
            f"{exc}"
        )
        return _Frontmatter(diagnostics=diagnostics, end_line=closing_line + 1)

    if loaded is None:
        data: dict[str, Any] = {}
    elif isinstance(loaded, Mapping):
        data = {str(key): value for key, value in loaded.items()}
    else:
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: YAML frontmatter "
            "should be a mapping"
        )
        data = {}

    return _Frontmatter(
        data=data,
        provedown=_provedown_config(data, path, diagnostics),
        diagnostics=diagnostics,
        end_line=closing_line + 1,
    )


def _frontmatter_closing_line(lines: Sequence[str]) -> int | None:
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() in {"---", "..."}:
            return index
    return None


def _provedown_config(
    frontmatter: Mapping[str, Any],
    path: Path | None,
    diagnostics: list[str],
) -> ProvedownConfig:
    raw = frontmatter.get("provedown")
    if raw is None:
        return ProvedownConfig()

    if not isinstance(raw, Mapping):
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: provedown frontmatter "
            "should be a mapping"
        )
        return ProvedownConfig()

    aliases: dict[str, str] = {}
    aliases.update(_aliases(raw.get("data_aliases"), path, diagnostics))
    aliases.update(_aliases(raw.get("aliases"), path, diagnostics))

    return ProvedownConfig(
        aliases=aliases,
        environments=_environments(raw.get("environments"), path, diagnostics),
        last_validated=_optional_text(raw.get("last_validated")),
        default_language=(
            _optional_text(raw.get("default_language")) or "python"
        ),
        pyproject=(
            _optional_text(raw.get("pyproject"))
            or _optional_text(raw.get("pyproject_toml"))
        ),
    )


def _environments(
    raw: object,
    path: Path | None,
    diagnostics: list[str],
) -> dict[str, Mapping[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: provedown environments "
            "should be a mapping"
        )
        return {}

    environments: dict[str, Mapping[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            diagnostics.append(
                f"{_frontmatter_location(path).display()}: provedown environment "
                f"name {key!r} should be a string"
            )
            continue
        name = key.strip()
        if not name:
            diagnostics.append(
                f"{_frontmatter_location(path).display()}: provedown environment "
                "name should not be empty"
            )
            continue
        if not isinstance(value, Mapping):
            diagnostics.append(
                f"{_frontmatter_location(path).display()}: provedown environment "
                f"{name!r} should be a mapping"
            )
            continue
        if name in environments:
            diagnostics.append(
                f"{_frontmatter_location(path).display()}: duplicate provedown "
                f"environment name {name!r}"
            )
            continue

        metadata: dict[str, Any] = {}
        for item_key, item in value.items():
            if not isinstance(item_key, str):
                diagnostics.append(
                    f"{_frontmatter_location(path).display()}: provedown environment "
                    f"{name!r} metadata key {item_key!r} should be a string"
                )
                continue
            metadata[item_key] = item
        environments[name] = metadata
    return environments


def _aliases(
    raw: object,
    path: Path | None,
    diagnostics: list[str],
) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: provedown aliases "
            "should be a mapping"
        )
        return {}

    aliases: dict[str, str] = {}
    for key, value in raw.items():
        if key is None or value is None:
            continue
        alias = str(key).strip()
        target = str(value).strip()
        if alias and target:
            aliases[alias] = target
    return aliases


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _frontmatter_location(path: Path | None) -> SourceLocation:
    return SourceLocation(path=path, line=1, column=1)


def _mask_frontmatter(source: str, end_line: int) -> str:
    if end_line <= 0:
        return source

    lines = source.splitlines(keepends=True)
    return "".join(
        _mask_line_preserving_newline(line) if index < end_line else line
        for index, line in enumerate(lines)
    )


def _attrs_to_dict(attrs: Sequence[tuple[str, str | None]]) -> dict[str, str]:
    return {name: value or "" for name, value in attrs}


def _has_class(attrs: Mapping[str, str], class_name: str) -> bool:
    return class_name in attrs.get("class", "").split()


def _is_ignored_region(attrs: Mapping[str, str]) -> bool:
    return attrs.get("data-provedown-ignore", "").lower() in {
        "1",
        "true",
        "yes",
    } or _has_class(attrs, "provedown-ignore")


def _language(attrs: Mapping[str, str], default_language: str) -> str:
    return (
        attrs.get("data-language")
        or attrs.get("language")
        or attrs.get("lang")
        or default_language
        or "python"
    ).strip() or "python"


def _compare_policy(attrs: Mapping[str, str]) -> str:
    if "data-compare" in attrs and attrs["data-compare"].strip():
        return attrs["data-compare"].strip()
    if "tol" in attrs or "data-tol" in attrs:
        return "tol"
    if "seed" in attrs or "data-seed" in attrs:
        return "seed"
    return "exact"


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _mask_markdown_fenced_code(source: str) -> str:
    """Hide Markdown fenced-code contents from the HTML parser.

    Provedown's contract is expressed as HTML in Markdown, but documentation
    often needs to show that raw HTML contract inside fenced code blocks. The
    parser does not otherwise understand Markdown, so this lightweight mask
    prevents examples from becoming live assertions while preserving line and
    column positions for real HTML outside the fences.
    """

    lines = source.splitlines(keepends=True)
    masked: list[str] = []
    fence_char: str | None = None
    fence_len = 0

    for line in lines:
        marker = fence_marker(line)
        if fence_char is None:
            masked.append(line)
            if marker is not None:
                fence_char, fence_len = marker
            continue

        if (
            marker is not None
            and marker[0] == fence_char
            and marker[1] >= fence_len
        ):
            masked.append(line)
            fence_char = None
            fence_len = 0
        else:
            masked.append(_mask_line_preserving_newline(line))

    return "".join(masked)


def fence_marker(line: str) -> tuple[str, int] | None:
    """Return the fence character and run length when ``line`` opens or closes a fence.

    Shared with integrations that need to agree with the parser about which
    lines delimit Markdown fenced code, so a document region is never masked by
    one and treated as live markup by the other.
    """

    stripped = line.lstrip()
    if not stripped.startswith(("```", "~~~")):
        return None

    char = stripped[0]
    count = 0
    for character in stripped:
        if character != char:
            break
        count += 1
    if count < 3:
        return None
    return char, count


def _mask_line_preserving_newline(line: str) -> str:
    return "".join("\n" if character == "\n" else " " for character in line)
