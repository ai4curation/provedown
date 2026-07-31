# Why Not Marimo?

[marimo](https://marimo.io/) is one of the closest pieces of prior art to
Provedown. It is a reactive Python notebook stored as a Python file, with strong
answers for many problems that make traditional notebooks difficult to review,
rerun, and deploy.

Provedown does not reject marimo's premise. It rejects a different default: that
the notebook should be the primary artifact.

## The Short Version

Use marimo when the primary thing you want is a reliable computational notebook
or an interactive Python app.

Use Provedown when the primary thing you want is a readable document whose claims
can be independently checked.

marimo keeps computation honest. Provedown keeps prose claims honest.

## Different Trust Contracts

marimo's central guarantee is state consistency. It statically analyzes cells,
builds a dependency graph, and reruns cells affected by changes. That eliminates
a common notebook failure mode: a visible output that no longer matches the code
currently on the page.

Provedown's central guarantee is claim falsification. The authored value in prose
is the thing being checked:

```html
The cohort has <span class="result" data-code="len(df)">412</span> samples.
```

The verifier reruns the supporting code and asks whether the document's authored
claim is still true. The value is not merely regenerated at render time. It is a
human-readable claim with attached executable evidence.

That distinction matters for agent-written reports. If an agent fabricates or
miscopies a number, a notebook can still look plausible. Provedown treats the
printed number as an assertion and gives a dumb, non-LLM verifier a narrow job:
prove that exact assertion wrong or pass it.

## Why Markdown Is The Source

marimo notebooks are Git-friendly because they are stored as Python files. That
is a major improvement over JSON notebooks.

Provedown goes further in a different direction: the source is normal Markdown
with a small HTML contract. The document should remain useful in ordinary
Markdown renderers, code review tools, static sites, and plain text editors. The
computation is annotation attached to the prose, not the container that owns the
prose.

That makes the default reader experience different:

- In marimo, the reader is still looking at a notebook or an app derived from a
  notebook.
- In Provedown, the reader is looking at a document. The notebook-like behavior
  exists only to verify claims.

## Why Not Reactive Execution?

marimo's reactive dependency graph is the right answer for interactive
exploration. If a cell changes, dependent cells should update automatically.

For Provedown, the default execution model is intentionally simpler:

1. Code blocks execute in document order.
2. State accumulates linearly.
3. A result span is checked against the live state at its position in the
   document.

This is less powerful than a DAG, but it is easier to audit. A reviewer can read
the document from top to bottom and understand what state exists at each claim.
When prose order must differ from execution order, Provedown should make that
escape hatch explicit rather than implicit.

Reactive execution also changes the authoring model. It encourages a document to
be organized around dependencies. Provedown is organized around the reader's
path through the argument.

## Why Not Generated Inline Values?

Tools such as notebooks, Quarto, knitr, and marimo can display values produced by
code. That is useful, but it usually makes the displayed value a render product.

Provedown makes the displayed value authored source.

That inversion is the core anti-hallucination move. A verifier can disagree with
the document because the document contains a claim independent of the recomputed
value. If the rendered value is always generated fresh, there is no separate
authored claim to falsify.

## Where Marimo Could Help

marimo is still useful prior art for Provedown. Several ideas are worth
borrowing:

- Inline dependency metadata with
  [PEP 723](https://peps.python.org/pep-0723/) for single-file reproducibility.
- Sandboxed execution with `uv` for verifier isolation.
- Dependency inspection tools that show which code supports which claims.
- [App or WASM export ideas](export-paths.md) for richer interactive
  presentations.
- Strong linting around mutation, hidden state, and nondeterministic execution.

The likely workflow is not "Provedown instead of marimo" in every context. A
good workflow may be:

1. Explore interactively in marimo.
2. Extract the final argument into Provedown.
3. Commit the Markdown report and verify it in CI.

## Decision

Provedown should not become a marimo wrapper, and it should not adopt marimo's
reactive notebook model as its default execution semantics.

The project should stay markdown-native, document-first, and verifier-neutral.
marimo remains an important comparison point and a source of implementation
ideas, but Provedown's differentiator is the falsifiable prose claim.

## Sources

- [marimo documentation](https://docs.marimo.io/)
- [marimo reactivity guide](https://docs.marimo.io/guides/reactivity/)
- [marimo app guide](https://docs.marimo.io/guides/apps/)
- [marimo package reproducibility guide](https://docs.marimo.io/guides/package_management/inlining_dependencies/)
- [Provedown Verifiable Literate Weave design spec](../ideas/verifiable-weave-spec.md)
