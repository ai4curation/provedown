# Verify Lean Claims

The built-in `lean-results` verifier checks scalar claims backed by Lean 4
definitions. Use it when a report's numbers come from Lean code and you want
the prose re-checked against it.

## Prerequisites

Install a Lean 4 toolchain so that `lean` is on your `PATH`. The
[official installer](https://lean-lang.org/install/) sets up `elan`, which
provides `lean` and `lake`.

Provedown does not bundle Lean. If no toolchain is found, Lean claims are
reported as errors rather than silently skipped, so a document whose evidence
cannot be checked never reports as `ok`.

## Mark cells and claims as Lean

Set `data-language="lean"` on both the evidence and the claim:

````markdown
<pre><code data-language="lean">
def cohortSizes : List Nat := [128, 96, 188]

def total (xs : List Nat) : Nat := xs.foldl (· + ·) 0
</code></pre>

The study pooled
<span class="result" data-language="lean" data-code="total cohortSizes">412<span
class="method"></span></span> samples.
````

To make Lean the default for a whole document, set it in frontmatter:

```yaml
---
provedown:
  default_language: lean
---
```

The verifier accepts `lean` and `lean4` as language names.

## How execution works

Lean has no long-lived REPL, so Provedown emulates notebook semantics by
re-elaborating the accumulated source prefix at each execution point. Document
order is still execution order, and forward references via `name` / `#name`
work exactly as they do for Python and SQL.

Two consequences are worth knowing:

- **Cost is quadratic in the number of cells.** That is cheap at document
  scale, but a report with many cells and a heavy `import Mathlib` will be
  slow. Each invocation is capped at 300 seconds.
- **`import` lines are hoisted.** Lean only accepts imports at the top of a
  file, so Provedown lifts any top-level `import` line out of its cell and
  emits it first. Write imports wherever they read best.

## Value rendering

Claims are evaluated by appending a generated `main` entry point and running
`lean --run`, which gives `toString` semantics. A Lean `String` therefore
renders the way it reads in prose:

| Expression | Authored value |
| --- | --- |
| `String.append "hi " "there"` | `hi there` |
| `(2 : Nat) + 2` | `4` |
| `[1, 2, 3].length` | `3` |

Values with no `ToString` instance — a `deriving Repr` structure, for example —
fall back to `repr` automatically.

Because a generated `main` is appended, a Lean cell that declares its own
`main` is reported as an error. Rename it.

## Exact arithmetic

Lean's `Nat` and `Int` are exact, so prefer integer claims over floats. Rather
than asserting a rounded percentage, state the figure in basis points:

````markdown
<span
  class="result"
  data-language="lean"
  data-code="largest cohortSizes * 10000 / total cohortSizes"
>4563<span class="method"></span></span> basis points.
````

Where a float is genuinely wanted, use `data-compare="tol"` with a `tol`
attribute, as with any other language.

## Lake projects

If the document's directory contains a `lakefile.lean` or `lakefile.toml`,
Provedown runs `lake env lean` instead of bare `lean` so that project and
Mathlib imports resolve. Otherwise it runs `lean` directly.

## `sorry` is reported as a failure

A cell that elaborates with `declaration uses 'sorry'` is reported as `fail`.
A `sorry` means the Lean text does not actually establish what it appears to,
so treating it as evidence would defeat the point of verifying the document.

## Proof claims

Scalar evaluation is the less interesting half. Python and SQL already compute
values, and they do it against real data, which Lean cannot easily read. What
Lean offers that neither can is a claim about *every* input rather than about
the rows in front of you.

A `lean-proof` claim names a theorem, and the authored text is the theorem's
statement:

````markdown
<span
  class="result"
  data-language="lean-proof"
  data-code="keepAbove_never_invents"
>∀ (t : Nat) (xs : List Nat), (keepAbove t xs).length ≤ xs.length</span>
````

Three independent things are checked:

1. **The declaration exists.** A renamed or deleted theorem fails the report.
2. **It rests on no unproved assumptions.** `#print axioms` is consulted, and
   anything beyond Lean's standard `propext`, `Classical.choice`, and
   `Quot.sound` is reported. Declare deliberate extras with
   `data-axioms="myAxiom"`.
3. **Its statement matches the document.** The pretty-printed statement is
   compared with the authored text, ignoring line wrapping.

The language names are `lean-proof` and `lean-theorem`.

### Why all three

The checks catch genuinely different failures, and none subsumes another.

A `sorry` anywhere in a proof's *dependencies* makes the claim vacuous, even
when the theorem's own text is clean and Lean emits no warning on it:

```lean
theorem helper (xs : List Nat) : P xs := by sorry
theorem looks_clean (xs : List Nat) : P xs := helper xs   -- no warning here
```

`looks_clean` has no `sorry` in its text, yet `#print axioms` reports
`sorryAx`. Grepping for `sorry` misses this; the axiom audit does not. Here the
statement is correct, so only check 2 fires.

Conversely, a proof can be entirely honest and still not support the prose,
because the theorem was weakened until it went through — an extra hypothesis, a
loosened bound. Then checks 1 and 2 pass and only check 3 fires.

### What this still does not check

Whether the theorem's statement means what the surrounding *prose* claims it
means. That is why the statement is printed in the document rather than hidden
behind a name: the machine checks statement against proof, and the reader
checks statement against prose. A theorem can typecheck, use no `sorry`, match
the displayed statement, and still be irrelevant to the sentence above it. That
last gap is not mechanically closable.
