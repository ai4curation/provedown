# Markup Contract

Provedown looks for a small HTML contract in Markdown or HTML documents.

The parser currently recognizes `<code>` elements, `<code use="..."/>` elements,
`<span class="result">` elements, and quotations: `<q>` inside `<cite>`, and
`<blockquote>` inside `<figure>`.

## Rendering In Markdown

`<code>` is the executable Provedown contract. For a multiline cell intended
to render as a visible code block, use `<pre><code>`:

````markdown
<pre><code>
x = 40 + 2
</code></pre>
````

The `<pre>` element is a presentation wrapper, not a Provedown event. Without
it, browsers treat `<code>` as an inline element and may collapse the block's
line breaks and whitespace. Provedown can parse a bare `<code>` element, but
`<pre><code>` is the renderer-safe authoring form for multiline cells.

To hide supporting code by default without a custom renderer, use native HTML
disclosure:

````markdown
<details>
<summary>Show supporting calculation</summary>

<pre><code>
x = 40 + 2
</code></pre>

</details>

The answer is <span class="result" data-code="x">42<span class="method"></span></span>.
````

The `<details>` and `<summary>` elements affect presentation only. Provedown
still executes the nested `<code>` element. GitHub and ordinary browser-based
MkDocs output can present this as a collapsed section; no Provedown-specific CSS
or JavaScript is required.

Rendering remains viewer-dependent. Without custom CSS, result spans look like
ordinary prose. A platform that sanitizes raw HTML or `data-*` attributes may
also remove part of the rendered contract. Verification operates on the
original source file, not a rendered or sanitized DOM. Markdown fenced code
blocks are literal examples and are not executable Provedown cells.

## Source Formats

Markdown documents can mix prose with raw Provedown HTML:

````markdown
The answer is <span class="result" data-code="x">42<span class="method"></span></span>.
````

HTML documents use the same contract directly:

```html
<pre><code name="calc">
x = 40 + 2
</code></pre>
<p>
  The answer is
  <span class="result" data-code="x">42<span class="method"></span></span>.
</p>
```

Markdown fenced code blocks and YAML frontmatter are ignored when scanning for
Provedown HTML. HTML regions with `data-provedown-ignore="true"` or the
`provedown-ignore` class are also ignored.

In source HTML, every `<code>` element is treated as Provedown code, including
one inside a [quotation](#quotations). Put non-executable code samples inside
an ignored region when they should only be shown to readers, and mark up code
quoted from a source with `<samp>`.

## Code Blocks

Use `<code>` for executable cells, normally inside `<pre>` for rendering:

````markdown
<pre><code>
x = 40 + 2
</code></pre>
````

Attributes:

`name`
: Optional block name.

`data-language`, `language`, `lang`
: Optional language marker. Defaults to the document's `provedown.default_language`
  frontmatter setting, or `python` when unset.

Built-in verifier language names are `python`/`py` and
`sql`/`duckdb`/`duckdb-sql`.

Unknown attributes are preserved in the parsed IR.

The parser strips leading and trailing newlines from the code text.

## Named Code

Name a block with `name`:

````markdown
<pre><code name="load">
x = 40 + 2
</code></pre>
````

Named blocks can be referenced by result assertions or executed at use sites.

A duplicate name produces a parser diagnostic. The parsed IR retains the later
definition for static inspection, but the high-level verification entry points
do not invoke a verifier until the duplicate is fixed.

## Code Uses

Use a named block at a specific execution point:

````markdown
<code use="load"/>
````

The `use` attribute names the block to execute. Empty uses emit diagnostics.

## Result Assertions

Use `<span class="result">` for authored scalar claims:

````markdown
The answer is <span class="result" data-code="x">42<span class="method"></span></span>.
````

Attributes:

`class="result"`
: Marks the span as a Provedown assertion.

`data-code`
: Required Python expression to evaluate, or `#name` to reference a named code
  block. A missing or empty value produces a parser error and blocks high-level
  verification.

`data-compare`
: Optional comparison policy. Defaults to `exact`.

`data-language`, `language`, `lang`
: Optional language marker. Defaults to the document's `provedown.default_language`
  frontmatter setting, or `python` when unset.

Built-in verifier language names are `python`/`py` and
`sql`/`duckdb`/`duckdb-sql`.

`tol`, `data-tol`
: Numeric tolerance. If present without `data-compare`, the comparison policy is
  `tol`.

`seed`, `data-seed`
: Random seed. If present without `data-compare`, the comparison policy is
  `seed`.

Unknown attributes are preserved in the parsed IR.

The parser strips surrounding whitespace from the authored value.

## Method Slot

Result spans may contain an empty method slot:

````markdown
<span class="method"></span>
````

The parser ignores text inside the method slot when collecting the authored
value. Future renderers can use this slot for method markers or disclosure UI.

## Quotations

A quotation that claims to reproduce its source verbatim is a `<q>` nested in a
`<cite>` that names the source:

````markdown
IL-34 signals through CSF1R <cite>PMID:18467591, <q>IL-34 binds the CSF-1 receptor</q></cite>.
````

The `<cite>` scopes the claim. Its own text, outside its `<q>` elements, must
name exactly one reference id: a `prefix:local` token such as `PMID:18467591`,
`DOI:10.1016/...`, `Reactome:R-HSA-75899` or `file:genes/x.txt`. Commas and
semicolons separate an id from the text around it; trailing sentence
punctuation, unbalanced closing brackets, and Markdown backtick, `*` and `_`
markers around an id (`` `PMID:1` ``, `**PMID:1**`, `_PMID:1_`) are dropped. A
token holding any other character an id cannot contain, such as `~~PMID:1~~`,
is rejected, and `provedown lint` reports it as an error, even when a valid id
is also present; the quote then has no single `source`. Any `prefix:local`
shaped token in citation text is held to these rules, so keep prose such as
`Chapter:3–5` out of the citation. The prefix is not checked against a list:
any `prefix:local` token counts as a reference id, so a verifier should reject
prefixes it does not know. A bare link such as `https://...` or `mailto:...`
is not a reference id; write a URL source as `url:https://...`. Do not wrap an
id in an HTML `<code>` element, which would be executed; Markdown backticks are
fine.
Each `<q>` in the citation is a separate claim against that source, and the id
may be link text, from an HTML `<a>` or a Markdown `[PMID:18467591](https://...)`
link:

````markdown
<cite><a href="https://pubmed.ncbi.nlm.nih.gov/18467591/">PMID:18467591</a>, <q>first excerpt</q> and <q>second excerpt</q></cite>
````

A `<blockquote>` cannot go inside `<cite>`, which holds only inline content.
Use a `<figure>` and put the citation in its `<figcaption>`:

````markdown
<figure>
<blockquote>
At the endoplasmic reticulum (ER) membrane, phosphatidic acid ...
</blockquote>
<figcaption><cite>Reactome:R-HSA-1483203</cite></figcaption>
</figure>
````

All of the information is visible text: browsers italicize the citation and
add quotation marks around `<q>`, and a renderer that drops the tags still shows
the reference and the quoted words. Do not type quotation marks inside `<q>`.
Text without `<q>` makes no verbatim claim, so cite a paraphrase without
quotation marks.

The quoted text is collected with HTML entities decoded and whitespace,
including line wraps, collapsed to single spaces. Markup inside a quote, such as
a nested `<q>`, is part of the quoted text, and paragraph or `<br>` boundaries
separate words, in quotes and in citation text. Inside a `<code>` element, a
start or self-closing tag is a parser diagnostic that blocks verification, as
anywhere else. An end tag, comment, declaration or processing instruction is
kept in the code exactly as written, so it never closes markup outside the code;
the verifier then runs it as part of the code, where it must be valid. An ignore
marker has no effect inside `<code>`. An ignored region inside a quote or
citation keeps its visible text there: the marker keeps markup out of the
executable contract, not words out of a quotation. Even a `</cite>` or
`</figure>` end tag inside an open quote is treated as quoted text, so a stray
end tag never cuts a quote short. Markdown inside a quote is not rendered first,
so avoid Markdown emphasis there.

Quotation markup never changes what is executable. A `<code>` element or a
result span runs wherever it appears, including inside a quote or citation, and
its text is also part of that quote or citation. That is a trap: a result
span's authored value becomes part of the verbatim quote, so correcting the
value to fix a failed check rewrites the quotation. `provedown lint` warns about
executable markup inside a quote or its citation; to quote code from a source,
use `<samp>`, which Provedown never executes, or, for a whole block, a
`<code>` carrying the ignore marker, whose text still joins the quote:

````markdown
<cite>PMID:1, <q>the patch adds <samp>retry=3</samp> to the client</q></cite>
````

A quote whose end tag is missing runs to the end of the document, so no
quotation after it is parsed; it is marked `unclosed`. A properly closed quote
in a `<cite>` or `<figure>` that has no end tag keeps its text, but is marked
`citation_unclosed`, because the citation text may run on and name the wrong
source. `provedown lint` reports both. Unclosed quote markup is not a parser
diagnostic, so it never stops a document's Python or SQL claims from being
verified.

Quotations are parsed into `Document.quotes` as `QuoteClaim` objects, not into
`Document.events`, because a quotation claim is not itself executable (any
`<code>` or result span inside it is still an event). Provedown itself does not
fetch sources: a verifier plugin that can, such as one built on
linkml-reference-validator, checks each claim's `text` against its `source`.
`provedown lint` reports quotes that such a verifier could not check; see
[Lint A Document](../how-to-guides/lint-a-document.md#current-lints).

## Diagnostics

The `provedown verify` CLI and the high-level `verify_file()` and
`verify_document()` APIs convert every current parser diagnostic into an
`error` finding. If any parser finding has `error` status, they append a `skip`
finding and return without constructing the default registry or invoking a
verifier. A document for which parsing reports an error therefore cannot execute
Python, SQL, dependency setup, or other verifier side effects through these
entry points. Static `inspect` and `lint` analysis remain available for
diagnosing the document.

`VerifierRegistry.verify()` is a lower-level plugin dispatch API: it does not
inspect `Document.diagnostics` before invoking registered verifiers. Use
`verify_document()` or `verify_file()` for parsed or untrusted document input.

Markup diagnostics include:

- nested HTML tags inside `<code>`;
- duplicate code block names;
- empty code uses;
- unclosed `<code>` blocks;
- unclosed result spans;
- result spans missing `data-code`;
- an unclosed ignored region: one still open at the end of the document, or
  still open when the quote, `<cite>` or `<figure>` it began in ends. A void
  element such as `<br>` inside a region, or carrying the ignore marker, counts
  as an open element, so the region can stay open even though its own end tag
  is there. What it swallowed was skipped, so the whole document is not
  verified. Documents that verified before this diagnostic existed may now
  report it.
- a `<cite>` or `<figure>` still open at the end of the document, holding no
  quotation, after an element of the same kind inside an ignored region took
  its end tag while that region skipped a quotation, citation, code block or
  result span. The inner element most likely has no end tag, so what the region
  skipped was lost, and no quotation is left to carry a lint. An unclosed
  `<cite>` or `<figure>` that holds a quotation is reported by lint instead, as
  `unclosed-citation`, and does not block verification; so is one whose
  ignored region skipped only text;
- a `<figure>` that ends while its `<figcaption>` is still open, after a
  `<figcaption>` inside an ignored region took the caption's end tag while that
  region skipped such markup.
- a `<cite>` or `<figure>` that closes after an ignored region inside it took
  an element's end tag of the container's kind, skipped such markup, and ended
  on another element's end tag: the region's own end tag was taken earlier, and
  a later stray end tag closed the container. It is reported even when another
  quotation in it survived, since no lint carries the ones that were lost. A
  container that never closes is reported by the bullets above instead.

A void element inside an ignored region also extends the region past its own
end tag. If the region began inside a quote, a `<cite>`, a `<figure>` or a
`<figcaption>`, that element's own end tag still closes it and ends the region,
and the region is reported as unclosed, so verification stops instead of
silently skipping what the region swallowed. Elsewhere, when later end tags
close the region again before the end of the document, claims and quotations
in that stretch are skipped without a diagnostic. Keep void elements out of
hand-written ignored regions; the diagram tooling already counts them
correctly, the core parser does not yet.

See [Frontmatter](frontmatter.md) for document-level metadata and defaults.
