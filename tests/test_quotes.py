from pathlib import Path

from provedown import (
    CodeBlock,
    QuoteClaim,
    SourceLocation,
    Status,
    lint_document,
    parse_document,
    verify_document,
)


def test_quote_inside_cite_takes_its_source_from_the_citation_text() -> None:
    document = parse_document(
        "IL-34 signals through CSF1R "
        "<cite>PMID:18467591, <q>IL-34 binds the CSF-1 receptor</q></cite>.",
        path=Path("notes.md"),
    )

    assert document.diagnostics == []
    assert document.quotes == [
        QuoteClaim(
            text="IL-34 binds the CSF-1 receptor",
            location=SourceLocation(path=Path("notes.md"), line=1, column=50),
            element="q",
            citation="PMID:18467591,",
            citation_location=SourceLocation(path=Path("notes.md"), line=1, column=29),
            sources=("PMID:18467591",),
        )
    ]
    assert document.quotes[0].source == "PMID:18467591"
    # Quotes are not executable events.
    assert document.events == []


def test_each_quote_in_a_citation_is_a_separate_claim() -> None:
    document = parse_document(
        "<cite>PMID:1, <q>first excerpt</q> and <q>second excerpt</q></cite>"
    )

    assert [quote.text for quote in document.quotes] == [
        "first excerpt",
        "second excerpt",
    ]
    assert {quote.source for quote in document.quotes} == {"PMID:1"}


def test_link_text_and_local_sources_are_reference_ids() -> None:
    document = parse_document(
        "\n".join(
            [
                '<cite><a href="https://pubmed.ncbi.nlm.nih.gov/2/">PMID:2</a>, '
                "<q>linked</q></cite>",
                "<cite>file:genes/CANAL/ERG9/ERG9-uniprot.txt, <q>local</q></cite>",
                "<cite>Reactome:R-HSA-75899, <q>pathway</q></cite>",
                "<cite>Smith et al. (DOI:10.1016/S0092-8674(00)81141-4), "
                "<q>doi</q></cite>",
            ]
        )
    )

    assert [quote.source for quote in document.quotes] == [
        "PMID:2",
        "file:genes/CANAL/ERG9/ERG9-uniprot.txt",
        "Reactome:R-HSA-75899",
        "DOI:10.1016/S0092-8674(00)81141-4",
    ]


def test_quote_text_collapses_line_wraps_and_keeps_nested_quotes() -> None:
    document = parse_document(
        "<cite>PMID:3, <q>a quote that\n   wraps <q>with an inner</q> quote"
        " &amp; an entity</q></cite>"
    )

    assert len(document.quotes) == 1
    assert document.quotes[0].text == (
        "a quote that wraps with an inner quote & an entity"
    )


def test_blockquote_in_figure_takes_its_source_from_the_figcaption() -> None:
    document = parse_document(
        "\n".join(
            [
                "<figure>",
                "<blockquote>",
                "At the endoplasmic reticulum (ER) membrane,",
                "phosphatidic acid is dephosphorylated.",
                "</blockquote>",
                "<figcaption><cite>Reactome:R-HSA-1483203</cite></figcaption>",
                "</figure>",
            ]
        )
    )

    assert len(document.quotes) == 1
    quote = document.quotes[0]
    assert quote.element == "blockquote"
    assert quote.text == (
        "At the endoplasmic reticulum (ER) membrane, "
        "phosphatidic acid is dephosphorylated."
    )
    assert quote.source == "Reactome:R-HSA-1483203"
    assert quote.location.line == 2
    assert quote.citation_location is not None
    assert quote.citation_location.line == 6


def test_figcaption_may_come_before_the_blockquote() -> None:
    document = parse_document(
        "<figure><figcaption><cite>PMID:4</cite></figcaption>"
        "<blockquote>caption first</blockquote></figure>"
    )

    assert [(quote.text, quote.source) for quote in document.quotes] == [
        ("caption first", "PMID:4")
    ]


def test_quotes_without_a_citation_have_no_source() -> None:
    document = parse_document(
        "\n".join(
            [
                "He said <q>hello</q>.",
                "<blockquote>a bare block quotation</blockquote>",
                "<figure><blockquote>no caption</blockquote></figure>",
            ]
        )
    )

    assert [
        (quote.text, quote.citation, quote.source) for quote in document.quotes
    ] == [
        ("hello", None, None),
        ("a bare block quotation", None, None),
        ("no caption", None, None),
    ]


def test_citation_with_zero_or_several_reference_ids_has_no_source() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>Smith 2020, <q>no id</q></cite>",
                "<cite>PMID:5; PMID:6, <q>two ids</q></cite>",
            ]
        )
    )

    assert [quote.sources for quote in document.quotes] == [(), ("PMID:5", "PMID:6")]
    assert [quote.source for quote in document.quotes] == [None, None]


def test_quotes_are_reported_in_document_order() -> None:
    document = parse_document(
        "<q>first</q> <cite>PMID:7, <q>second</q></cite> <q>third</q>"
    )

    assert [quote.text for quote in document.quotes] == ["first", "second", "third"]


def test_quotes_in_fenced_code_and_ignored_regions_are_skipped() -> None:
    document = parse_document(
        "\n".join(
            [
                "```html",
                "<cite>PMID:8, <q>an example</q></cite>",
                "```",
                '<div data-provedown-ignore="true">',
                "<cite>PMID:9, <q>ignored</q></cite>",
                "</div>",
                '<cite class="provedown-ignore">PMID:10, <q>also ignored</q></cite>',
                "<cite>PMID:11, <q>live</q></cite>",
            ]
        )
    )

    assert [quote.text for quote in document.quotes] == ["live"]


def test_unclosed_quote_is_flagged_without_blocking_verification() -> None:
    document = parse_document(
        "<code>x = 1</code>\n"
        '<span class="result" data-code="x">1<span class="method"></span></span>\n'
        "<cite>PMID:12, <q>never closed</cite>"
    )

    assert document.diagnostics == []
    assert [(quote.text, quote.unclosed) for quote in document.quotes] == [
        ("never closed", True)
    ]
    report = verify_document(document)
    assert report.ok
    assert report.count(Status.PASS) == 1
    assert [finding.code for finding in lint_document(document).findings] == [
        "unclosed-quote"
    ]


def test_quote_in_an_unclosed_citation_keeps_its_text_trustworthy() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>PMID:20, <q>complete</q> but no end tag",
                "<figure><blockquote>A</blockquote>"
                "<figcaption><cite>PMID:21</cite></figcaption>",
            ]
        )
    )

    assert document.diagnostics == []
    assert [
        (quote.text, quote.unclosed, quote.citation_unclosed)
        for quote in document.quotes
    ] == [
        ("complete", False, True),
        ("A", False, True),
    ]
    assert [finding.code for finding in lint_document(document).findings] == [
        "unclosed-citation",
        "unclosed-citation",
    ]


def test_quotations_after_an_unclosed_quote_are_not_parsed() -> None:
    document = parse_document(
        "<cite>PMID:1, <q>never closed</cite>\n\n"
        "<cite>PMID:2, <q>a real claim</q></cite>"
    )

    assert [(quote.text, quote.unclosed) for quote in document.quotes] == [
        ("never closed PMID:2, a real claim", True)
    ]
    [finding] = lint_document(document).findings
    assert finding.code == "unclosed-quote"
    assert "quotations after it are not parsed" in finding.message


def test_nested_or_stray_cite_end_tag_does_not_truncate_a_quote() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>PMID:21, <q>he cited <cite>Nature</cite> here</q></cite>",
                "<cite>PMID:22, <q>a </cite> b</q></cite>",
            ]
        )
    )

    assert [
        (quote.text, quote.source, quote.unclosed) for quote in document.quotes
    ] == [
        ("he cited Nature here", "PMID:21", False),
        ("a b", "PMID:22", False),
    ]


def test_figure_nested_in_a_figure_blockquote_keeps_the_caption() -> None:
    document = parse_document(
        "<figure><blockquote>outer <figure>inner</figure> text</blockquote>"
        "<figcaption><cite>PMID:23</cite></figcaption></figure>"
    )

    assert [(quote.text, quote.source) for quote in document.quotes] == [
        ("outer inner text", "PMID:23")
    ]


def test_executable_markup_inside_a_quote_still_runs_and_is_flagged() -> None:
    document = parse_document(
        "\n".join(
            [
                "<code>x = 42</code>",
                "<cite>PMID:24, <q>the gene <code>y = 1</code> is required</q></cite>",
                '<cite>PMID:25, <q>the value was <span class="result" data-code="x">'
                "42</span></q></cite>",
                "<cite>PMID:26, <q>quoted with <samp>os.system()</samp></q></cite>",
            ]
        )
    )

    # Quote markup never changes what runs: <code> and result spans are
    # executable wherever they appear, and their text is part of the quote.
    assert [type(event).__name__ for event in document.events] == [
        "CodeBlock",
        "CodeBlock",
        "ResultAssertion",
    ]
    assert [quote.text for quote in document.quotes] == [
        "the gene y = 1 is required",
        "the value was 42",
        "quoted with os.system()",
    ]
    assert verify_document(document).ok
    findings = lint_document(document).findings
    assert [(f.level, f.code, f.location.line) for f in findings] == [
        ("warning", "executable-markup-in-quote", 2),
        ("warning", "executable-markup-in-quote", 3),
    ]


def test_unclosed_code_inside_a_quote_is_a_parser_diagnostic() -> None:
    document = parse_document("<cite>PMID:26, <q>see <code>gene X")

    assert any("unclosed <code> block" in d for d in document.diagnostics)
    assert document.quotes[0].text == "see gene X"


def test_quote_markup_alone_does_not_add_events_or_block_verification() -> None:
    document = parse_document(
        "<code>x = 1</code>\n"
        "<cite>PMID:13, <q>quoted</q></cite> "
        '<span class="result" data-code="x">1<span class="method"></span></span>'
    )

    assert document.diagnostics == []
    assert len(document.events) == 2
    assert len(document.quotes) == 1


def test_lint_accepts_a_quote_with_one_source() -> None:
    report = lint_document(parse_document("<cite>PMID:14, <q>fine</q></cite>"))

    assert report.findings == []


def test_lint_reports_quote_citation_problems() -> None:
    document = parse_document(
        "\n".join(
            [
                "<q>uncited</q>",
                "<cite>Smith 2020, <q>no id</q></cite>",
                "<cite>PMID:15; PMID:16, <q>two ids</q></cite>",
                "<cite>PMID:17, <q>  </q></cite>",
                "<q></q>",
            ]
        ),
        path=Path("notes.md"),
    )

    report = lint_document(document)

    assert [
        (finding.level, finding.code, finding.location.line)
        for finding in report.findings
    ] == [
        ("warning", "uncited-quote", 1),
        ("error", "quote-citation-without-source", 2),
        ("error", "quote-citation-with-several-sources", 3),
        ("error", "empty-quote", 4),
        ("warning", "uncited-quote", 5),
    ]
    assert report.findings[2].target == "PMID:15 PMID:16"


def test_block_boundaries_inside_a_quote_separate_words() -> None:
    document = parse_document(
        "<figure><blockquote><p>First paragraph.</p><p>Second<br>line<br/>"
        "with <i>E. coli</i>.</p></blockquote>"
        "<figcaption><cite>PMID:18</cite></figcaption></figure>"
    )

    assert document.quotes[0].text == ("First paragraph. Second line with E. coli.")


def test_stray_end_tag_does_not_close_a_quote() -> None:
    document = parse_document(
        "<figure><blockquote>kept </cite>open</blockquote>"
        "<figcaption><cite>PMID:19</cite></figcaption></figure>"
    )

    assert document.diagnostics == []
    assert [(quote.text, quote.source) for quote in document.quotes] == [
        ("kept open", "PMID:19")
    ]


def test_markdown_link_in_a_citation_names_its_link_text() -> None:
    document = parse_document(
        "<cite>[PMID:25](https://pubmed.ncbi.nlm.nih.gov/25/), <q>linked</q></cite>"
    )

    assert document.quotes[0].sources == ("PMID:25",)


def test_trimmed_tokens_without_a_local_part_are_not_sources() -> None:
    document = parse_document("<cite>see Figure:. PMID:26, <q>text</q></cite>")

    assert document.quotes[0].sources == ("PMID:26",)


def test_markdown_link_targets_with_titles_or_parentheses_are_not_sources() -> None:
    document = parse_document(
        "\n".join(
            [
                '<cite>[PMID:27](https://doi.org/10.1/x "title"), <q>a</q></cite>',
                "<cite>[DOI:10.1016/S0092-8674(00)81141-4]"
                "(https://doi.org/10.1016/S0092-8674(00)81141-4), <q>b</q></cite>",
            ]
        )
    )

    assert [quote.sources for quote in document.quotes] == [
        ("PMID:27",),
        ("DOI:10.1016/S0092-8674(00)81141-4",),
    ]


def test_bare_web_links_are_not_reference_ids() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>PMID:28 (https://pubmed.ncbi.nlm.nih.gov/28/), <q>a</q></cite>",
                "<cite>url:https://example.org/paper, <q>b</q></cite>",
            ]
        )
    )

    assert [quote.sources for quote in document.quotes] == [
        ("PMID:28",),
        ("url:https://example.org/paper",),
    ]


def test_quote_end_tag_inside_code_does_not_close_the_quote() -> None:
    document = parse_document(
        "<cite>PMID:29, <q>the gene <code>ERG9 is required</q></cite> after"
    )

    # The </q> inside the code is code text, so the quote is not closed and
    # the unclosed <code> blocks verification, instead of a truncated quote.
    assert any("unclosed <code> block" in d for d in document.diagnostics)
    assert [(quote.text, quote.unclosed) for quote in document.quotes] == [
        ("the gene ERG9 is required after", True)
    ]


def test_executable_markup_in_citation_text_is_flagged() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite><code>PMID:30</code>, <q>x</q></cite>",
                "<figure><blockquote>y</blockquote><figcaption><cite>PMID:31 "
                "<code>z = 1</code></cite></figcaption></figure>",
            ]
        )
    )

    assert len(document.events) == 2
    assert document.quotes[0].sources == ("PMID:30",)
    assert [quote.contains_executable_markup for quote in document.quotes] == [
        True,
        True,
    ]
    assert [f.code for f in lint_document(document).findings] == [
        "executable-markup-in-quote",
        "executable-markup-in-quote",
    ]


def test_code_in_a_figure_outside_its_blockquote_stays_executable() -> None:
    document = parse_document(
        "<figure><pre><code>x = 1</code></pre>"
        "<figcaption>Listing 1</figcaption></figure>"
    )

    assert len(document.events) == 1
    assert document.quotes == []


def test_markup_inside_quoted_code_is_code_text() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>PMID:31, <q>a <code>x<br/>y</code></q></cite>",
                "<cite>PMID:32, <q>b <code>p<br>q</code></q></cite>",
            ]
        )
    )

    # Inside <code>, any tag is a blocking parser diagnostic, as everywhere else.
    assert [quote.text for quote in document.quotes] == ["a xy", "b pq"]
    assert [
        event.code for event in document.events if isinstance(event, CodeBlock)
    ] == ["xy", "pq"]
    assert len(document.diagnostics) == 2
    assert all("nested HTML tag inside <code>" in d for d in document.diagnostics)


def test_markdown_inline_markup_around_a_reference_id_is_not_part_of_it() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>`PMID:32`, <q>a</q></cite>",
                "<cite>**PMID:33**, <q>b</q></cite>",
                "<cite>_PMID:34_, <q>c</q></cite>",
                "<cite>file:genes/x_y.txt, <q>d</q></cite>",
            ]
        )
    )

    assert [quote.sources for quote in document.quotes] == [
        ("PMID:32",),
        ("PMID:33",),
        ("PMID:34",),
        ("file:genes/x_y.txt",),
    ]


def test_unclosed_quote_is_not_also_citation_unclosed() -> None:
    document = parse_document("<cite>PMID:35, <q>never closed")

    assert [(quote.unclosed, quote.citation_unclosed) for quote in document.quotes] == [
        (True, False)
    ]
    [finding] = lint_document(document).findings
    assert finding.code == "unclosed-quote"
    assert finding.target == "PMID:35,"


def test_other_url_schemes_are_not_reference_ids() -> None:
    document = parse_document(
        "<cite>PMID:36 mailto:a@example.org ftp://example.org/x, <q>a</q></cite>"
    )

    assert document.quotes[0].sources == ("PMID:36",)


def test_unclosed_cite_or_quote_never_stops_later_code_from_running() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>Darwin, On the Origin of Species",
                '<pre><code name="load">data = [1, 2, 3]</code></pre>',
                "<cite>PMID:1, <q>never closed",
                "<pre><code>total = 42</code></pre>",
                '<p>The total is <span class="result" data-code="total">42</span>.</p>',
            ]
        )
    )

    assert [type(event).__name__ for event in document.events] == [
        "CodeBlock",
        "CodeBlock",
        "ResultAssertion",
    ]
    assert verify_document(document).ok


def test_rejected_reference_ids_are_named_by_lint() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>~~PMID:37~~, <q>a</q></cite>",
                '<cite>"PMID:38", <q>b</q></cite>',
                "<cite>DOI:10.1002/(SICI)1097-0258(19980430)17:8&lt;857::AID>3.0, "
                "<q>c</q></cite>",
            ]
        )
    )

    assert [quote.sources for quote in document.quotes] == [(), (), ()]
    assert [quote.rejected_sources for quote in document.quotes] == [
        ("PMID:37~~",),
        ('PMID:38"',),
        ("DOI:10.1002/(SICI)1097-0258(19980430)17:8<857::AID>3.0",),
    ]
    messages = [f.message for f in lint_document(document).findings]
    assert 'found "PMID:37~~", which is not a valid reference id' in messages[0]


def test_block_boundaries_in_citation_text_separate_words() -> None:
    document = parse_document(
        "<cite>PMID:39<br>and other work, <q>x</q></cite>"
        "<cite>PMID:40<br/>and more, <q>y</q></cite>"
    )

    assert [quote.sources for quote in document.quotes] == [("PMID:39",), ("PMID:40",)]


def test_end_tag_inside_code_is_kept_as_written() -> None:
    document = parse_document(
        "\n".join(
            [
                '<pre><code>assert "</P >" in page</code></pre>',
                '<figure><pre><code>s = "</figure>"</code></pre>'
                "<blockquote>kept</blockquote>"
                "<figcaption><cite>PMID:41</cite></figcaption></figure>",
            ]
        )
    )

    # Dropping it would execute assert "" in page, which always passes.
    assert document.diagnostics == []
    assert [
        event.code for event in document.events if isinstance(event, CodeBlock)
    ] == [
        'assert "</P >" in page',
        's = "</figure>"',
    ]
    # It never closes markup outside the code.
    assert [(quote.text, quote.source) for quote in document.quotes] == [
        ("kept", "PMID:41")
    ]


def test_self_closing_tags_inside_code_are_parser_diagnostics() -> None:
    document = parse_document(
        '<code>x = 1 <code use="other"/> <span class="result" data-code="x"/></code>'
    )

    # Like any other tag inside <code>, they add no event and block
    # verification, so a code use or result there is never silently dropped.
    assert [type(event).__name__ for event in document.events] == ["CodeBlock"]
    assert len(document.diagnostics) == 2
    assert all("nested HTML tag inside <code>" in d for d in document.diagnostics)


def test_rejected_id_next_to_a_valid_one_is_an_error() -> None:
    document = parse_document("<cite>~~PMID:37~~ and PMID:38, <q>x</q></cite>")

    quote = document.quotes[0]
    assert quote.sources == ("PMID:38",)
    # Ambiguous like two valid ids: the claim is not attributed to PMID:38.
    assert quote.source is None
    [finding] = lint_document(document).findings
    assert (finding.level, finding.code) == ("error", "rejected-reference-id")
    assert '"PMID:37~~"' in finding.message


def test_realistic_id_in_code_in_a_citation_is_an_executable_cell() -> None:
    document = parse_document("<cite><code>Reactome:R-HSA-1</code>, <q>x</q></cite>")

    # The id is still the source, but it is also a Python cell. Whether running
    # it fails depends on the id and the Python version (here it is a valid
    # annotation), which is why lint flags it rather than relying on verify.
    assert document.quotes[0].source == "Reactome:R-HSA-1"
    assert [
        event.code for event in document.events if isinstance(event, CodeBlock)
    ] == ["Reactome:R-HSA-1"]
    assert [f.code for f in lint_document(document).findings] == [
        "executable-markup-in-quote"
    ]


def test_rejected_id_is_named_even_when_the_quote_has_another_problem() -> None:
    document = parse_document(
        "\n".join(
            [
                "<cite>~~PMID:37~~, <q></q></cite>",
                "<cite>~~PMID:38~~, <q>x</q>",
            ]
        )
    )

    findings = lint_document(document).findings
    assert [f.code for f in findings] == [
        "empty-quote",
        "rejected-reference-id",
        "unclosed-citation",
        "rejected-reference-id",
    ]


def test_repeated_reference_id_counts_once() -> None:
    document = parse_document("<cite>PMID:1 and PMID:1, <q>x</q></cite>")

    assert document.quotes[0].sources == ("PMID:1",)
    assert lint_document(document).findings == []


def test_comments_and_declarations_inside_code_are_kept_exactly() -> None:
    for markup in ("<!-- x -->", "</ p>", "<!DOCTYPE x>", "<?pi x?>", "<!x>"):
        document = parse_document(f'<pre><code>assert "{markup}" in page</code></pre>')

        assert document.diagnostics == [], markup
        assert [
            event.code for event in document.events if isinstance(event, CodeBlock)
        ] == [f'assert "{markup}" in page'], markup


def test_every_end_tag_spelling_inside_code_is_kept_exactly() -> None:
    document = parse_document(
        "\n".join(
            [
                "<pre><code>a = '</>'</code></pre>",
                "<pre><code>b = '</p a=\">\">'</code></pre>",
            ]
        )
    )

    assert document.diagnostics == []
    assert [
        event.code for event in document.events if isinstance(event, CodeBlock)
    ] == ["a = '</>'", "b = '</p a=\">\">'"]


def test_ignore_marker_inside_code_does_not_hide_code_text() -> None:
    document = parse_document(
        '<pre><code>assert "<b data-provedown-ignore="true">x</b>" in page</code></pre>'
    )

    assert len(document.diagnostics) == 1
    assert "nested HTML tag inside <code>" in document.diagnostics[0]
    assert [
        event.code for event in document.events if isinstance(event, CodeBlock)
    ] == ['assert "x</b>" in page']


def test_comments_outside_code_are_still_ignored() -> None:
    document = parse_document("<!-- a note --> <cite>PMID:42, <q>x</q></cite>")

    assert document.diagnostics == []
    assert document.quotes[0].source == "PMID:42"


def test_ignored_region_inside_a_quote_keeps_its_visible_text() -> None:
    document = parse_document(
        "\n".join(
            [
                '<cite>PMID:43, <q>the gene is <span data-provedown-ignore="true">'
                "not </span>required</q></cite>",
                '<cite>PMID:44, <q>a<p class="provedown-ignore">x</p>b</q></cite>',
                '<cite>PMID:45 <span class="provedown-ignore">PMID:46</span>, '
                "<q>y</q></cite>",
            ]
        )
    )

    # The marker keeps markup out of the executable contract; it never hides
    # visible text from a quote or citation.
    assert [quote.text for quote in document.quotes] == [
        "the gene is not required",
        "a x b",
        "y",
    ]
    assert document.quotes[2].sources == ("PMID:45", "PMID:46")
    assert [f.code for f in lint_document(document).findings] == [
        "quote-citation-with-several-sources"
    ]


def test_nested_cite_text_stays_in_the_enclosing_citation() -> None:
    document = parse_document(
        "<cite>PMID:1 (reviewed in <cite>PMID:2</cite>), <q>x</q></cite>"
    )

    assert document.quotes[0].sources == ("PMID:1", "PMID:2")
    assert document.quotes[0].source is None
    assert [f.code for f in lint_document(document).findings] == [
        "quote-citation-with-several-sources"
    ]
    glued = parse_document("<cite>see <cite>PMID:2</cite>and PMID:1, <q>x</q></cite>")
    assert glued.quotes[0].sources == ("PMID:2", "PMID:1")


def test_unclosed_ignored_region_is_a_parser_diagnostic() -> None:
    document = parse_document(
        '<span class="provedown-ignore"><br class="a"></span>\n'
        "<cite>PMID:47, <q>a claim that would otherwise vanish</q></cite>"
    )

    # The <br> deepens the region and never closes, so everything after it is
    # skipped; that must block verification rather than pass with no quotes.
    assert document.quotes == []
    assert any("unclosed ignored region" in d for d in document.diagnostics)


def test_every_break_spelling_in_an_ignored_region_separates_quoted_words() -> None:
    for markup, leaks in (
        ('<span class="provedown-ignore">not<br/>yet</span>', False),
        ('<span class="provedown-ignore">not<br>yet</span>', True),
        ('not<br class="provedown-ignore"/>yet', False),
        ('not<br class="provedown-ignore">yet', True),
    ):
        document = parse_document(
            f"<cite>PMID:1, <q>the gene is {markup} required</q></cite>"
            "<cite>PMID:2, <q>a later claim</q></cite>"
        )

        # Same text, closed, and the later quotation still parsed.
        assert [
            (quote.text, quote.unclosed, quote.citation_unclosed)
            for quote in document.quotes
        ] == [
            ("the gene is not yet required", False, False),
            ("a later claim", False, False),
        ], markup
        quote_lints = [
            f.code
            for f in lint_document(document).findings
            if f.code != "parser-diagnostic"
        ]
        assert quote_lints == [], markup
        # A non-self-closing <br> counts as an open element, so it leaves the
        # region open until the quote's end tag, which is reported.
        unclosed = [d for d in document.diagnostics if "unclosed ignored region" in d]
        assert len(unclosed) == int(leaks), markup


def test_unclosed_ignored_region_message_names_the_likely_cause() -> None:
    for source in (
        '<span class="provedown-ignore"><br class="a"></span>',
        '<div class="provedown-ignore">\nDraft notes.',
    ):
        [diagnostic] = parse_document(source).diagnostics

        assert "unclosed ignored region" in diagnostic
        assert "most likely a void element such as <br>" in diagnostic
        assert "or a missing end tag" in diagnostic


def test_quote_inside_an_ignored_region_inside_a_quote_does_not_close_it() -> None:
    document = parse_document(
        '<cite>PMID:3, <q>a <span class="provedown-ignore"><br><q>x</q></span> b</q>'
        "</cite>"
    )

    assert [(quote.text, quote.unclosed) for quote in document.quotes] == [
        ("a x b", False)
    ]
    # The <br> leaked the region, so the quote's own end tag closed it, and the
    # leak is reported: the document is not verified.
    [diagnostic] = document.diagnostics
    assert "unclosed ignored region" in diagnostic


def test_ignored_region_leaked_by_a_void_element_in_a_citation_is_reported() -> None:
    inline = parse_document(
        '<cite>PMID:1 <span class="provedown-ignore">(draft<br>note)</span>, '
        "<q>a claim</q></cite>"
    )
    figure = parse_document(
        "<figure><blockquote>A</blockquote><figcaption><cite>PMID:2"
        '<br class="provedown-ignore"> (preprint)</cite></figcaption></figure>'
    )

    # The region the <br> left open ends at the citation's own end tag and is
    # reported, so the dropped inline claim is not silent and the figure's
    # well-formed citation is not called unclosed.
    for document in (inline, figure):
        assert any("unclosed ignored region" in d for d in document.diagnostics)
    assert inline.quotes == []
    assert [(q.text, q.source, q.citation_unclosed) for q in figure.quotes] == [
        ("A", "PMID:2", False)
    ]


def test_ignored_region_left_open_inside_a_quote_is_reported() -> None:
    document = parse_document(
        '<cite>PMID:1, <q>a <span class="provedown-ignore">x<b>y</q> rest</cite>'
    )

    # The quote still closes at its own end tag, but the region never did.
    assert [(q.text, q.unclosed) for q in document.quotes] == [("a xy", False)]
    assert any("unclosed ignored region" in d for d in document.diagnostics)


def test_ignored_region_left_open_inside_a_citation_is_reported() -> None:
    document = parse_document(
        '<cite>PMID:1 <span class="provedown-ignore">(draft<b>note)</span>, '
        "<q>a claim</q></cite> after"
    )

    assert any("unclosed ignored region" in d for d in document.diagnostics)


def test_ignore_marked_element_of_the_owners_kind_does_not_end_the_owner() -> None:
    for source, expected in (
        (
            '<cite>PMID:1, <q>a <q class="provedown-ignore">x</q> b</q></cite>',
            ("a x b", "PMID:1"),
        ),
        (
            "<figure><blockquote>A</blockquote>"
            '<figure class="provedown-ignore"><span>decoration</span></figure>'
            "<figcaption><cite>PMID:1</cite></figcaption></figure>",
            ("A", "PMID:1"),
        ),
        (
            '<cite>PMID:1 <cite class="provedown-ignore">draft</cite>, '
            "<q>the claim</q></cite>",
            ("the claim", "PMID:1"),
        ),
    ):
        document = parse_document(source)

        assert [
            (quote.text, quote.source, quote.unclosed, quote.citation_unclosed)
            for quote in document.quotes
        ] == [(*expected, False, False)], source
        assert document.diagnostics == [], source
        assert lint_document(document).findings == [], source


def test_void_element_in_an_ignore_marked_figure_inside_a_figure_fails_closed() -> None:
    document = parse_document(
        "<figure><blockquote>A</blockquote>"
        '<figure class="provedown-ignore"><img src="x"></figure>'
        "<figcaption><cite>PMID:1</cite></figcaption></figure>"
    )

    # The <img> leaks the region, so the caption is skipped; the leak is
    # reported, so the uncited quote is never verified as if nothing happened.
    [diagnostic] = document.diagnostics
    assert "unclosed ignored region" in diagnostic


def test_unclosed_ignore_marked_container_inside_its_own_kind_is_reported() -> None:
    for source, outer, kind in (
        (
            '<cite>PMID:1 <cite class="provedown-ignore">draft, <q>a claim</q></cite>',
            "cite",
            "cite",
        ),
        (
            '<figure><figure class="provedown-ignore"><blockquote>A</blockquote>'
            "</figure>",
            "figure",
            "figure",
        ),
    ):
        document = parse_document(source)

        assert document.quotes == [], source
        [diagnostic] = document.diagnostics
        assert (
            f"unclosed <{outer}> holding no quotation; most likely an "
            f"ignore-marked <{kind}> inside it has no end tag"
        ) in diagnostic
        assert not verify_document(document).ok


def test_plain_missing_end_tag_after_a_closed_ignored_own_kind_is_lint_only() -> None:
    for source in (
        '<cite>PMID:1 <cite class="provedown-ignore">draft</cite>, <q>the claim</q>'
        "\n<pre><code>total = 42</code></pre>",
        '<figure><blockquote>A</blockquote><figure class="provedown-ignore">'
        "<figcaption><cite>PMID:1</cite></figcaption></figure>"
        "\n<pre><code>total = 42</code></pre>",
    ):
        document = parse_document(source)

        # A quotation carries the unclosed-citation lint, so the code still runs.
        assert document.diagnostics == [], source
        assert "unclosed-citation" in {
            finding.code for finding in lint_document(document).findings
        }, source
        assert verify_document(document).ok, source


def test_figcaption_leak_with_the_caption_end_tag_missing_is_reported() -> None:
    document = parse_document(
        "<figure><blockquote>A</blockquote><figcaption>"
        '<span class="provedown-ignore">draft<br>note</span>'
        "<pre><code>total = 42</code></pre><cite>PMID:1</cite></figure>"
        '<p><span class="result" data-code="total">42</span></p>'
    )

    [diagnostic] = document.diagnostics
    assert "unclosed ignored region" in diagnostic
    assert not verify_document(document).ok


def test_void_element_leak_in_a_figcaption_is_reported_for_any_count() -> None:
    for breaks in ("<br>", "<br><br>"):
        document = parse_document(
            "<figure><blockquote>A</blockquote><figcaption>"
            f'<span class="provedown-ignore">draft{breaks}note</span>'
            "<cite>PMID:1</cite></figcaption></figure>"
            "<cite>PMID:2, <q>later</q></cite>"
        )

        [diagnostic] = document.diagnostics
        assert "unclosed ignored region" in diagnostic, breaks
        # The figure still ends at its own end tag, so later quotes parse.
        assert [quote.text for quote in document.quotes] == ["A", "later"], breaks


def test_unmatched_figure_in_a_caption_region_keeps_the_rescue() -> None:
    document = parse_document(
        "<figure><blockquote>A</blockquote><figcaption>"
        '<span class="provedown-ignore">see <figure>draft</span>'
        "<cite>PMID:1</cite></figcaption></figure>"
    )

    # The stray <figure> no longer cancels the </figcaption> that ends the leak.
    [diagnostic] = document.diagnostics
    assert "unclosed ignored region" in diagnostic
    assert not verify_document(document).ok


def test_closed_ignored_cite_in_an_unclosed_cite_without_quotes_still_runs_code() -> (
    None
):
    document = parse_document(
        '<cite>Darwin, <cite class="provedown-ignore">draft note</cite>\n\n'
        "<pre><code>total = 42</code></pre>\n"
        '<p>The total is <span class="result" data-code="total">42</span>.</p>'
    )

    assert document.diagnostics == []
    assert verify_document(document).ok
