# Frontmatter

Markdown documents may start with YAML frontmatter. Provedown parses it, exposes
it on the Python API, and ignores it when looking for executable code and result
assertions.

```yaml
---
title: Sales summary
owner: analytics
tags:
  - weekly
  - revenue
provedown:
  aliases:
    data: data
    cache: ../cache
  environments:
    python:
      requires-python: ">=3.11"
      dependencies:
        - pandas>=2
        - pyarrow>=15
  last_validated: "2026-06-15"
  default_language: python
  pyproject: pyproject.toml
---
```

## User Metadata

The top-level YAML schema belongs to the project that owns the document.
Provedown does not validate `title`, `owner`, `tags`, or other user-defined
fields. Unknown fields are preserved in `Document.frontmatter`.

A first line whose trimmed contents are `---` is always treated as a frontmatter
opener and must have a closing `---` or `...` delimiter. Use `***` or `___` for
a thematic break at the start of a Markdown document. Without a closing
delimiter, the parser masks the rest of the document so HTML in the malformed
frontmatter cannot become executable Provedown markup, and reports an
unterminated-block diagnostic.

Any frontmatter parser diagnostic—for example, invalid YAML, a non-mapping
`environments` value, or an unterminated block—becomes an `error` finding in
the high-level verification entry points. They report that verification was
skipped and do not invoke a verifier. Static `inspect` and `lint` analysis
remain available and report the diagnostic. For an unterminated block, the
source through EOF is masked, so static reports contain no events from that
region; with a closing delimiter, the document body remains available for
static analysis.

## `provedown` Block

The optional `provedown` mapping is reserved for Provedown-aware tooling.

`aliases`
: Optional mapping of short names to data folders or other local paths. The
  parser stores these aliases for verifiers and integrations.

`environments`
: Optional mapping of language or verifier-family names to environment
  metadata. Environment names and metadata keys must be strings. Provedown core
  preserves each nested mapping without interpreting plugin-specific fields.
  The built-in Python environment uses
  `dependencies` and `requires-python` with the same value semantics as PEP
  723. See [Dependency Metadata](../explanations/dependency-metadata.md).

`last_validated`
: Optional date or string recording when the document was last validated. YAML
  dates are normalized to strings in `Document.provedown.last_validated`.

`default_language`
: Optional default language for `<code>`, `<code use="..."/>`, and result
  spans that do not set `data-language`, `language`, or `lang`. Defaults to
  `python`.

`pyproject`
: Optional path to the Python project's `pyproject.toml`, relative to the
  document. A Python environment may combine this project with extra inline
  dependencies from `environments.python.dependencies`.

`pyproject_toml`
: Accepted as a synonym for `pyproject`.

`okf`
: Optional mapping read by the
  [OKF integration](../how-to-guides/verify-an-okf-bundle.md). Provedown core
  preserves it without interpreting it.

The built-in parser also accepts `data_aliases` as a synonym for `aliases`.
Element-level language attributes still override `default_language`.

## `provedown.okf` Block

The OKF integration reads these keys when a document is verified with `--okf`.
They are ignored otherwise.

`bindings`
: Optional mapping of binding name to declared parameter values. Each binding
  becomes a named code block holding the computation with its `@parameter`
  placeholders replaced.

`runtime_language`
: Optional verifier language to use instead of the one implied by the OKF
  `runtime` key. Set this when a computation declares a runtime Provedown
  cannot run but is portable enough to check with another.

`computation_name`
: Optional name for the lifted computation block. Defaults to `computation`.
