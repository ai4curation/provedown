# Verifiable Literate Weave — Design Spec

**Status:** draft v0.1
**One line:** A markdown-native document format where human-readable prose is the primary artifact, computed values are authored inline, and a cheap post-hoc pass re-executes the embedded code to verify those values — catching agent hallucination in the same session it was produced.

---

## 1. Motivation

Agentic tools that produce reports (BERIL, openscientist-style outputs) are readable but can hallucinate. Tools that produce notebooks are checkable (re-runnable) but optimize for the wrong reader: the notebook becomes the primary artifact and the prose an afterthought, so user-unfriendly Python leaks into the deliverable.

This format inverts that. It returns to the original literate-programming claim — the document is written *for humans*, in the order a human wants to read it — while keeping the notebook's one genuinely valuable property: the values can be mechanically re-derived and checked.

The target threat is specific and *hot*: **the agent wrote this document in this session; did it fabricate a number; can I trust it right now.** This is deliberately not the cold reproducibility problem (re-run a year later on another machine). Long-term reproducibility is a welcome side effect, not the goal. Scoping to hot verification removes the hardest parts of the reproducibility literature — environment reconstruction and fuzzy type-aware comparison — because the data, interpreter, and dependencies are the same ones that produced the value seconds ago.

### What this is, precisely

A notebook with the cells left inline but hidden by default, the narrative promoted to primary, and the printed values *pinned and asserted* rather than merely displayed. Reading is the default mode; verification is a separate, optional, non-LLM pass. There is no source/derived split — the document with its inline values **is** the source of truth. The agent may write a value by running code, by hand, or by copying; verification re-derives it and flags any disagreement.

---

## 2. Core model

1. **The document is the source.** An inline value such as `412` is the real, primary, human-readable artifact. The attached code is *annotation justifying the value*, not the value's generator-of-record.
2. **Notebook execution semantics.** Code blocks form an ordered cell sequence sharing one kernel; state accumulates linearly. A value assertion is checked against live state *at its position in that sequence*.
3. **Verification is falsification, not generation.** A separate dumb (non-LLM) pass re-executes the code and asserts equality with the authored value. A mismatch is the trust signal.
4. **Document order = execution order**, by default. A forward-reference mechanism is the only escape hatch when narrative order must diverge from execution order.
5. **Hot equality, not fuzzy similarity.** Because verification runs in the same environment, the default comparison is exact equality. Tolerance/normalization policies exist only for genuinely non-deterministic values, and declaring one is a visible, auditable, lint-able choice.

### Two failure modes, one signal

A mismatch means either (a) the agent hallucinated/miscopied the value, or (b) the document is stale. Both mean "the document no longer tells the truth," which is exactly the signal wanted. They need not be distinguished for the trust use case.

---

## 3. Markup

### 3.1 The result assertion (the unit that matters)

The agent's entire contract is: a value, the code that derives it, and (optionally) a comparison policy. Nothing else.

```html
The cohort has <span class="result" data-code="len(df)">412<span class="method"></span></span> samples.
```

- **`class="result"`** carries the contract. The verifier keys off this.
- **`data-code`** — the expression whose result must equal the span's authored text. Short code inline; long code by reference (§3.3).
- **`data-compare`** *(optional, default `exact`)* — comparison policy (§4).
- **`412`** — the authored value. Primary, human-readable, asserted.
- **`<span class="method"></span>`** — an **empty presentation slot**. The agent never fills it. A preprocessor injects the citation mark / disclosure affordance (§5). Keeping it empty means the agent maintains no numbering and no footnote table — the hallucination-resistant contract stays as small as possible.

`<span>` (not a custom `<method>` element) is chosen so every markdown renderer and HTML sanitizer passes it through unchanged.

### 3.2 Code cells

By default, code lives in `<code>` blocks woven through the document. Cell order is document order; the document *is* the notebook, linearized.

```html
<code name="load">
df = pd.read_parquet("cohort.parquet")
</code>
```

- A `<code>` block executes in document order against the shared kernel.
- An optional **`name`** makes the block referenceable (needed only for forward references).
- Whether a `<code>` block is visible by default is a presentation choice (§5) — the verifier runs it regardless.

### 3.3 Inline vs. referenced code

- **Inline** (`data-code="len(df)"`) — for short single expressions that fit readably in an attribute.
- **Referenced** (`data-code="#cohort-size"`) — for anything longer. The expression lives in a named `<code>` block; the result span points at it. This is the original `<exec code="#script123">` idea as the overflow path.

```html
The cohort has <span class="result" data-code="#cohort-size">412<span class="method"></span></span> samples.

<!-- in methods, or woven nearby -->
<code name="cohort-size">len(df)</code>
```

**Threshold rule of thumb:** if the expression is a single side-effect-free expression under ~40 chars, inline it; otherwise name it and reference it.

### 3.4 Forward references (the only ordering escape hatch)

Default: document order = execution order, zero ceremony. When prose order must diverge from execution order, name a block and use it elsewhere — the literate-programming `@<...@>` move.

```html
<code name="load">df = pd.read_parquet("cohort.parquet")</code>
...prose that needs df to already exist...
<code use="load"/>
```

**Ordering contract:** the **use site is the execution site**. The definition is parked text; execution order is the order of *use* sites (and of inline `<code>` blocks, which are their own use site). This preserves a single linear execution sequence, so a `result` span always asserts against well-defined state.

---

## 4. Comparison policies

In hot verification the default is exact string/value equality, because re-running against identical state is deterministic. Policies exist only for the cases where exact equality is legitimately wrong, and **declaring one is auditable** — an agent marking something `none` that is actually deterministic is making a visible choice you can lint for (the way you lint for swallowed exceptions).

| `data-compare` | Meaning | When |
|---|---|---|
| `exact` *(default)* | byte/value equality | almost everything in-session |
| `numeric` | parse as number, compare equal | `412` vs `412.0` |
| `tol="1e-6"` | numeric within tolerance | floats |
| `set` | order-insensitive collection equality | sets, dict keys, unordered rows |
| `seed="42"` | RNG pinned before exec, then exact | stochastic-but-pinnable |
| `none` | not verified; explicitly out of scope | wall-clock, external API, true nondeterminism |

`none` does not undermine the checksum *as long as it is declared and countable*. The escape hatches are visible in the document; a lint can flag "too many `none`."

---

## 5. Rendering & progressive disclosure

The design target is that **default rendering in standard markdown tools is already friendly**, with richer disclosure available via light CSS, and full interactivity in a bespoke renderer. Superlight preprocessing produces whichever view is wanted; all views are a pure function of the authored source.

Because the format already assumes a preprocessing step, it does **not** rely on markdown footnote (`[^1]`) syntax — it weaves freely in HTML. The empty `method` slot is filled mechanically:

- **Citation mark.** Injected as a small superscript marker. Marks attach to the *claim* (after the noun), not jammed against the digits — `412 samples¹`, never `412¹`, which reads as an exponent. A bracketed/spaced mark (`[1]`) is unambiguous against numeric values.
- **Disclosure.** Code is hidden by default and revealed on demand. With light CSS this is a click-to-expand (`<label>`/checkbox, no JS); the degraded no-CSS case still shows the value plus a small mark.
- **Methods placement.** Code may be woven inline (for code-literate readers) or pooled in a methods section at the end (clean weave). Both are generated from the same `data-code` references; this is purely a layout choice and does not affect execution order except via forward references.

**Numbering, mark placement, footnote/methods pooling, and CSS injection are all mechanical** — owned by the preprocessor, never authored. The agent emits only value + code + (optional) policy.

---

## 6. The verifier

A small, non-LLM, post-hoc consumer of the document. *Where* it runs is incidental — a Claude Code stop-hook, a GitHub Action, or a manual CLI invocation — because the document is the contract and the trigger is just deployment. It is cheap and easy by design.

**Algorithm:**

1. Parse the document; collect `<code>` blocks and `result` spans in document order.
2. Resolve forward references into a single linear cell sequence (use sites are execution sites).
3. Start one fresh kernel. Execute cells in sequence.
4. At each `result` span's execution point, evaluate its `data-code` against current live state and compare to the authored value under the span's `data-compare` policy.
5. Emit a per-span pass/fail report. Optionally annotate the document in place.

**Note on "hot" vs the kernel:** a stop-hook or CI job runs in a *fresh* process — the agent's live kernel is gone. So even hot verification re-establishes state by running the cells from the top. The difference from cold reproducibility is that this happens on the same machine, same files, same dependencies, seconds later — so it is cheap, but it is **not** stateless: cells must run in order so that a `result` span sees the state it was authored against. This is the one piece of "setup" that survives, and it is exactly the notebook execution model, nothing more.

**Failure surface (deployment choice):**

- *Fatal* — hook blocks the turn / CI fails the build. Use when no unverified values may ship.
- *Advisory* — annotate the document with pass/fail marks and let a human judge. Use when `none` escape hatches are legitimate and human review is expected.

---

## 7. Relationship to prior work

The substrate and the pieces are old; the synthesis is not.

- **Literate programming** (Knuth, 1984) — document written for humans, machine-extraction secondary. This format restores that priority; BERIL-style notebook-first output had inverted it.
- **Live values in prose** (knitr / Quarto inline code, ~2012) — narrative pulls computed values from execution. But these *generate the value fresh at render time*; there is no authored value for a pass to disagree with, so nothing catches a fabricated number. This format makes the value primary and authored, and verification a falsification pass.
- **Reproducibility checking** (Jupyter-from-PMC studies; SRI similarity index) — "recompute and diff against the printed value" at scale, plus type-aware comparison tolerances. Same mechanism, but framed as *cold* reproducibility (rerun later, environment drift is the core problem) and as a continuous similarity score. This format borrows the comparison taxonomy but scopes to *hot*, in-session, exact-equality verification, where their hardest problem — environment reconstruction, which their data shows is what actually kills automated reruns — largely vanishes.
- **Agent tool-receipt verification** (2025–26) — cross-check LLM claims against signed records of what tools actually returned; re-fetch to catch fabricated URLs. Structurally the same anti-hallucination move (verify-by-recompute, give actionable trust signals rather than binary verified/unverified) applied to tool calls rather than to a readable document.
- **Prior art to clear:** a USPTO patent on "determining validity of multipart branching literate programs" (per-module output validation with declared inter-module dependencies). Coming from a formal-validation angle, not a readable-document one — worth reading for scope before publishing.

**One-line positioning:** prior work verifies notebooks *after* publication; this makes the publishable artifact self-verifying *by construction* — the weave is born verifiable rather than checked after the fact.

---

## 8. Open questions / decisions deferred

- **LinkML schema for the contract.** The `result` / `code` units (value, code-or-ref, compare policy, name/use) are the shared contract among agent, renderer, and verifier. A schema is what makes "stuff leaking through" enforceable by a build step rather than by prompting. Deferred until the markup stabilizes.
- **Result types beyond scalars.** Scalars round-trip trivially inline. Tables, dataframes, and figures need a discipline (referenced artifact + hash) if they are ever to be asserted. v1 scope is scalar-in-prose; richer result types are future work.
- **Verification status in the document.** Whether the citation mark reflects verified state (green check / red x) or the document stays verification-state-free and status lives only in the verifier's output. Folding status into the mark bakes a "verified-at" notion into the doc; keeping it out keeps the doc a pure source. Leaning state-free for v1.
- **`none` budget / linting.** Define a lint that flags an excess of `data-compare="none"` so escape hatches stay countable.
