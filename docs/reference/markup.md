# Markup Contract

Provedown looks for a small HTML contract in Markdown or HTML documents.

The parser currently recognizes `<code>` elements, `<code use="..."/>` elements,
and `<span class="result">` elements.

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

In source HTML, every `<code>` element is treated as Provedown code. Put
non-executable code samples inside an ignored region when they should only be
shown to readers.

## Code Blocks

Use `<code>` for executable cells:

````markdown
<code>
x = 40 + 2
</code>
````

Attributes:

`name`
: Optional block name.

`data-language`, `language`, `lang`
: Optional language marker. Defaults to the document's `provedown.default_language`
  frontmatter setting, or `python` when unset.

Unknown attributes are preserved in the parsed IR.

The parser strips leading and trailing newlines from the code text.

## Named Code

Name a block with `name`:

````markdown
<code name="load">
x = 40 + 2
</code>
````

Named blocks can be referenced by result assertions or executed at use sites.

Duplicate names are accepted, but the later definition wins and the parser emits
a diagnostic.

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
: Python expression to evaluate, or `#name` to reference a named code block.

`data-compare`
: Optional comparison policy. Defaults to `exact`.

`data-language`, `language`, `lang`
: Optional language marker. Defaults to the document's `provedown.default_language`
  frontmatter setting, or `python` when unset.

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

## Diagnostics

Parser diagnostics are converted into `error` findings by `provedown verify`.

Current diagnostics include:

- nested HTML tags inside `<code>`;
- duplicate code block names;
- empty code uses;
- unclosed `<code>` blocks;
- unclosed result spans;
- result spans missing `data-code`.

See [Frontmatter](frontmatter.md) for document-level metadata and defaults.
