# Inspect Claim Dependencies

Use `provedown inspect` when you want to understand the static relationships
between code blocks, code uses, and result assertions without executing the
document.

Inspection is useful before verification when you want to answer questions such
as:

- Which named code blocks are referenced by prose claims?
- Which code blocks execute inline, and which are deferred to a use site or
  result assertion?
- Does a result point at a missing named expression?
- Are any named blocks never referenced?

## Inspect A Document

Run:

```bash
uv run provedown inspect docs/examples/data-file-report.md
```

Text output starts with a summary and then lists document events in document
order:

```text
docs/examples/data-file-report.md: ok
  events=10, errors=0, warnings=0
  [1] code docs/examples/data-file-report.md:9:6 execution='inline'
  [2] result docs/examples/data-file-report.md:28:19 compare='exact' authored='6' execution='eval'
```

The exact line and column numbers may change as the document changes.

## Use JSON Output

Use JSON when an editor, CI job, or script needs structured inspection data:

```bash
uv run provedown inspect --format json docs/examples/data-file-report.md
```

Each event includes its kind, source location, language, and any relevant
reference information. Result assertions include the authored value and
comparison policy.

## Interpret Issues

Inspection can report errors and warnings.

Errors mean the document has a broken static relationship, such as a code use or
result assertion pointing at a missing named block. The command exits with
status `1` when any inspection error is present.

Warnings identify suspicious but technically executable structure. For example,
a named code block that is never referenced is reported as
`unused-named-code`.

Inspection does not execute Python, read data files, or check authored values.
Use `provedown verify` for that.
