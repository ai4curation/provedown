from pathlib import Path

from provedown import QuoteClaim, SourceLocation, lint_document, parse_document


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


def test_unclosed_quote_is_a_parser_diagnostic() -> None:
    document = parse_document("<cite>PMID:12, <q>never closed</cite>")

    assert len(document.diagnostics) == 1
    assert "unclosed <q>" in document.diagnostics[0]
    assert [quote.text for quote in document.quotes] == ["never closed"]


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
