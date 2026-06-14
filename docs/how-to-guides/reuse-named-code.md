# Reuse Named Code

Use named code when an expression is too long for a `data-code` attribute or
when prose order should differ from execution order.

## Name A Result Expression

For longer expressions, put the expression in a named `<code>` block and point a
result span at it with `data-code="#name"`:

````markdown
<code>
samples = ["alpha", "beta", "gamma"]
</code>

The summary is <span class="result" data-code="#summary">3 samples<span class="method"></span></span>.

<code name="summary">f"{len(samples)} samples"</code>
````

Named code used by a result assertion must be a Python expression, because the
Python verifier evaluates it with `eval()`.

The named block is evaluated at the result site. Its position in the document is
where the expression is defined, not where it executes.

## Execute A Named Cell At A Use Site

Use `<code use="name"/>` when the named block contains statements that should
execute somewhere else in the document:

````markdown
<code name="load-data">
samples = ["alpha", "beta", "gamma"]
sample_count = len(samples)
</code>

<code use="load-data"/>

The cohort has <span class="result" data-code="sample_count">3<span class="method"></span></span> samples.
````

The use site is the execution site. This keeps execution linear while allowing
definitions to be parked away from the prose that needs them.

## Avoid Ambiguous Reuse

Prefer one named block per concept. A duplicate `name` is accepted, but the later
definition wins and the parser emits a diagnostic. In practice, duplicate names
should be treated as authoring mistakes.

## Choose Inline Or Named Code

Use inline `data-code` when the expression is short and readable:

````markdown
<span class="result" data-code="len(samples)">3</span>
````

Use named result expressions when the expression is long but side-effect-free.

Use named cells with `<code use="..."/>` when the code is a setup step or has
statements that need to run before later claims.
