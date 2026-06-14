# Provedown In Provedown?

Using Provedown to document Provedown is not crazy. It is the right kind of
dogfooding. But it should be introduced carefully because documentation pages
often need to show literal Provedown markup, and literal examples can conflict
with live assertions.

## The Tension

A documentation page can contain two different kinds of Provedown-looking text:

- examples that teach the syntax;
- real assertions that the page itself wants to verify.

Those should not accidentally become the same thing. A tutorial that shows a bad
example should not fail the documentation build unless it was meant to be a live
claim.

## Practical Rule

Use fenced code blocks for teaching examples.

Use real Provedown markup only when the page itself is meant to be verified.

That keeps the reader experience clear and avoids an escaping maze where a page
has to explain result spans while also hiding some result spans from the parser.

## A Good First Step

The first dogfooding layer should be verified example documents under
`docs/examples/`. They are easy to understand:

- MkDocs can render them as ordinary pages.
- `provedown verify docs/examples/basic-report.md` can check them.
- CI can later verify the whole examples directory.

This gives the project real self-use without forcing every tutorial and
reference page to become a Provedown input.

## A Later Step

Once rendering conventions stabilize, selected docs pages can become
self-verifying. Good candidates are pages that make factual claims about command
output, parser behavior, or verifier counts.

The standard should be high: if self-verifying docs make the source harder to
read, they are working against Provedown's document-first premise.
