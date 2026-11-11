# Lint A Document

Use `provedown lint` to catch fragile document structure without executing code.
Linting is static: it parses the document, inspects code/result relationships,
and looks for patterns that may make verification misleading or hard to audit.

## Run Lints

```bash
provedown lint report.md
```

The command prints one summary per file:

```text
report.md: ok
  errors=0, warnings=1
  [warning] unused-named-code report.md:3:6: named code block is never referenced by a code use or result assertion target='load'
```

Warnings do not make the command fail. Errors do.

## Use JSON Output

```bash
provedown lint --format json report.md
```

JSON output is intended for CI, editor integrations, and scripts.

## Current Lints

`unresolved-code-use`
: A `<code use="..."/>` references a missing named code block. This is an
  error.

`unresolved-result-reference`
: A result assertion such as `data-code="#name"` references a missing named code
  block. This is an error.

`unused-named-code`
: A named code block is never referenced by a use site or result assertion. This
  is a warning.

`unjustified-none-compare`
: A result uses `data-compare="none"` without `data-reason` or
  `data-justification`. This is a warning.

`excessive-none-compare`
: A document has more than three unverified result assertions. This is a
  warning.

`fragile-python`
: Python code appears to use randomness, wall-clock time, environment variables,
  or network calls during verification. This is a warning.

`distant-global-mutation`
: A code block mutates a global object (for example `list.append` or
  `data[key] = ...`) that was first defined in an earlier block many lines away.
  Because Python cells share one namespace, this is hidden state that makes the
  later block depend on and change something far from where it reads. This is a
  warning.

`python-syntax-error`
: A Python code block or inline expression cannot be parsed. This is an error.

`uncited-quote`
: A `<q>` or `<blockquote>` is not inside a citation, so no verifier can check
  it against a source. This is a warning. See
  [Quotations](../reference/markup.md#quotations).

`quote-citation-without-source`
: A quote is inside a `<cite>` whose text names no valid reference id such as
  `PMID:123`. The message names any id-shaped token that was rejected, such as
  `PMID:1~~`. This is an error.

`quote-citation-with-several-sources`
: The citation around a quote names more than one reference id: a `<cite>`
  with several ids, or a `<figcaption>` with several `<cite>` elements. A quote
  must cite exactly one source. This is an error.

`empty-quote`
: A `<q>` or `<blockquote>` inside a citation has no text. This is an error.

`unclosed-quote`
: A `<q>` or `<blockquote>` has no end tag, so its text runs to the end of the
  document and quotations after it are not parsed. This is an error.

`unclosed-citation`
: The `<cite>` or `<figure>` around a properly closed quote has no end tag, so
  the citation may name the wrong source. This is an error.

`executable-markup-in-quote`
: A quote or its citation text contains a `<code>` element or result span.
  `provedown verify` still executes it; mark up code quoted from a source with
  `<samp>` and keep reference ids out of `<code>`. This is a warning.

## Justify Explicitly Unverified Claims

When a claim is intentionally outside the verifier's scope, mark it with
`data-compare="none"` and explain why:

````markdown
The service status is <span class="result" data-code="status()" data-compare="none" data-reason="external service changes between runs">available<span class="method"></span></span>.
````

The linter does not judge whether the reason is good. It makes the escape hatch
visible and reviewable.

## Lint Before Verify

Linting does not replace verification:

```bash
provedown lint report.md
provedown verify report.md
```

Use linting to catch fragile structure. Use verification to recompute authored
claims and compare the results.
