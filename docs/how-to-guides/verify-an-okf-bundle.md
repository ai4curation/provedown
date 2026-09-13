# Verify an OKF Bundle

[Open Knowledge Format][okf] (OKF) describes structured knowledge — table
definitions, metrics, runbooks, computations — as Markdown with YAML
frontmatter. OKF v0.2 added trust signals so consumers can decide how much to
believe a document that an agent wrote.

Provedown answers a question those signals leave open. `verified` records that
somebody blessed the document, and `stale_after` records a date by which it
might have drifted; neither checks that the numbers in the document's prose
still reproduce. Provedown does, deterministically.

## OKF documents Are Already Provedown documents

Provedown parses YAML frontmatter, ignores it when it scans for executable
markup, preserves unknown keys on `Document.frontmatter`, and never rewrites the
file. An OKF concept document with Provedown claims in its body needs no
special handling:

````markdown
---
type: BigQuery Table
title: Customer Orders
generated: { by: reference_agent/example, at: 2026-06-30T14:00:00Z }
verified:
  - { by: human:kliu@acme, at: 2026-07-01T16:00:00Z }
status: stable
stale_after: 2026-12-31
provedown:
  default_language: duckdb
---

# Examples

<pre><code name="orders">
CREATE OR REPLACE VIEW orders AS
SELECT * FROM read_csv_auto('../data/orders.csv');
</code></pre>

<code use="orders"/>

The table holds
<span class="result" data-code="SELECT COUNT(*) FROM orders">7<span class="method"></span></span>
orders.
````

```bash
provedown verify tables/orders.md
```

`provedown` is a legal OKF extension key, and OKF's own keys mean nothing to
Provedown, so the two vocabularies do not collide.

## Attested Computations Need The Shim

One OKF convention does not line up. An `Attested Computation` carries its
computation as a Markdown fenced code block under a `# Computation` heading, or
in a separate file named by the `computation` key. Provedown treats fenced code
as a literal example and [never executes it](../reference/markup.md), so a
bundle authored the ordinary OKF way gets no coverage at all.

Pass `--okf` to close that gap:

```bash
provedown verify --okf computations/revenue-by-year.md
```

The shim parses the document normally, then *lifts* the OKF computation into a
named code block that the ordinary verifiers can execute. Nothing on disk
changes, and fenced code keeps its usual meaning for every other document.

The lifted block is a definition named `computation`, so reference it by name:

````markdown
---
type: Attested Computation
runtime: duckdb
---

# Computation

```sql
SELECT printf('%.2f', SUM(net_amount))
FROM read_csv_auto('../data/orders.csv')
WHERE order_status = 'delivered'
```

Delivered revenue is
<span class="result" data-code="#computation">500.50<span class="method"></span></span>.
````

`runtime` also sets the document's default language, so claims do not have to
repeat it. An explicit `provedown.default_language`, or a `data-language`
attribute on one element, still wins.

## Bind Declared Parameters

OKF computations take typed parameters, and the producer "MAY only supply values
for the declared parameters; it MUST NOT author or edit the computation."
Declare each set of values as a binding, and the shim generates one named block
per binding with the `@parameter` placeholders replaced by literals:

````markdown
---
type: Attested Computation
runtime: duckdb
parameters:
  - { name: year, type: integer, required: true }
provedown:
  okf:
    bindings:
      fy2025: { year: 2025 }
      fy2026: { year: 2026 }
---

# Computation

```sql
SELECT printf('%.2f', SUM(net_amount))
FROM read_csv_auto('../data/orders.csv')
WHERE order_status = 'delivered'
  AND EXTRACT(YEAR FROM order_ts) = @year
```

# Examples

Revenue was
<span class="result" data-code="#fy2025">225.50<span class="method"></span></span>
in FY2025 and
<span class="result" data-code="#fy2026">275.00<span class="method"></span></span>
in FY2026.
````

Bindings are checked against the declared `parameters`, and the checks are
blocking:

- a binding that supplies a parameter the document does not declare is an error;
- a binding that omits a required parameter, or one the computation references,
  is an error;
- a value that does not match its declared type is an error.

Literals are rendered for the target language: quoted and escaped for SQL,
`repr` for Python. Only declared parameter names are substituted, so an `@` in a
string literal is never mistaken for a placeholder.

## Runtimes Provedown Cannot Run

`runtime` names an execution context — `bigquery`, `postgres`, `dbt`, `python`,
`duckdb`. The built-in verifiers cover `python` and DuckDB SQL. A computation
declaring any other runtime is **reported, not guessed at**:

```text
revenue.md:1:1: okf: no built-in verifier runs the 'bigquery' runtime; set
provedown.okf.runtime_language to check the computation with another language,
or register a verifier plugin for it
```

Failing here is deliberate. Running BigQuery SQL through DuckDB could pass or
fail for reasons that have nothing to do with the claim, and a document that
silently checks nothing is worse than one that says so.

Two ways forward. If the computation is portable enough to check locally, say so
explicitly:

```yaml
provedown:
  okf:
    runtime_language: duckdb
```

Otherwise write a [verifier plugin](../reference/verifier-plugins.md) for the
real runtime. The shim hands it an ordinary `Document`, so a plugin needs to
know nothing about OKF.

## Attestation And Verification Are Different Jobs

OKF attestation asks whether the sanctioned computation is what actually ran,
using an executor receipt and a deterministic attester. Provedown asks whether
the values a reader sees still reproduce. Neither subsumes the other:

| Signal | Scope | Answers |
| --- | --- | --- |
| `verified` | document, stored | Did somebody bless this document? |
| Attestation | per call, runtime | Was the sanctioned computation what ran? |
| `stale_after` | document, calendar | Is it probably still true? |
| Provedown | per claim, deterministic | Do the numbers still reproduce? |

Use them together. A document can be human-`verified`, `status: stable`, and
inside its `stale_after` window while its prose reports last quarter's number.

## Read The Trust Signals

The Python API exposes OKF metadata alongside the parsed document, including the
trust tier OKF derives from its `verified` actors:

```python
from pathlib import Path

from provedown.integrations.okf import parse_okf_file, verify_okf_file

okf = parse_okf_file(Path("computations/revenue-by-year.md"))

okf.metadata.trust_tier()   # 'unverified' | 'machine-confirmed' | 'human-reviewed'
okf.metadata.is_stale()     # compares stale_after against today
okf.metadata.sources        # provenance entries, preserved verbatim
okf.computation             # the lifted CodeBlock, or None
okf.bindings                # one CodeBlock per declared binding

report = verify_okf_file(Path("computations/revenue-by-year.md"))
```

`okf.document` is an ordinary `Document`, so it also works with
`inspect_document()` and `lint_document()`. `provedown inspect --okf` shows what
the shim lifted and which claims resolve to it.

Provedown does not write results back into OKF frontmatter. A `verify` run is
evidence a bundle's own tooling can turn into a `verified` entry, but appending
one is that tooling's decision, not Provedown's.

## A Worked Bundle

`examples/okf/` holds a small bundle mirroring the layout of OKF's reference
`acme_retail` bundle, covering both cases:

```bash
provedown verify examples/okf/tables/orders.md
provedown verify --okf examples/okf/computations/revenue-ytd.md
```

[OKF Bundle: Revenue at Acme Retail](../examples/okf-acme-retail.md) walks
through it with a policy change that leaves every OKF trust signal green and the
document's figures wrong.

[okf]: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf
