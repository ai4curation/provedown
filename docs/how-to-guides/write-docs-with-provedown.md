# Write Docs With Provedown

It is reasonable to dogfood Provedown in its own documentation, but there are
two different jobs that should not be confused:

1. Teaching the syntax.
2. Verifying claims made by the documentation itself.

Use different patterns for each job.

## Show Syntax In Fenced Blocks

When a documentation page is teaching Provedown markup, put examples in fenced
code blocks:

````markdown
```markdown
The answer is <span class="result" data-code="answer">42<span class="method"></span></span>.
```
````

This keeps MkDocs, Markdown renderers, and the Provedown parser from treating
the teaching example as a live assertion in the docs page.

## Keep Verified Examples As Separate Documents

For executable examples, create standalone documents under `docs/examples/`.
Those files can be both visible in the docs site and checked with:

```bash
uv run provedown verify docs/examples/basic-report.md
```

This repository uses [Basic Verified Report](../examples/basic-report.md) as the
first example of that pattern.

## Use Real Assertions Sparingly In Explanations

A page can contain real Provedown assertions if the page itself is meant to be
verified. That is useful for claims like "this command returns three findings"
or "this example has two passing assertions."

Do not start there for every page. A self-verifying documentation page has extra
escaping pressure because it may need to show literal Provedown markup while also
containing live Provedown markup. Fenced code blocks are usually clearer for
teaching pages.

## Recommended Policy

For now:

- Tutorials and reference pages should use fenced examples by default.
- `docs/examples/` may contain real Provedown documents.
- CI should eventually verify the real examples.
- Fully self-verifying docs pages should be introduced only when the renderer
  and escaping conventions are stable.
