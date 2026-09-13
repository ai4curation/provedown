# OKF Bundle: Revenue at Acme Retail

A walkthrough of `examples/okf/`, a small [Open Knowledge Format][okf] bundle
that mirrors the layout of OKF's reference `acme_retail` bundle. It exists to
answer one question: what does Provedown catch that OKF v0.2's trust signals do
not?

For the mechanics of the `--okf` flag, see
[Verify an OKF Bundle](../how-to-guides/verify-an-okf-bundle.md). This page is
the scenario.

## The Bundle

```text
examples/okf/
├── index.md                        # navigation
├── log.md                          # bundle history
├── data/orders.csv                 # stands in for the warehouse table
├── policies/revenue-recognition.md # source of truth for the definition
├── tables/orders.md                # BigQuery Table concept, with claims
├── metrics/revenue.md              # Metric concept, delegates to the computation
├── metrics/revenue-legacy.md       # the same metric, status: deprecated
├── computations/revenue-ytd.md     # Attested Computation, with claims
├── skills/run-on-duckdb.md         # executor instructions
└── attesters/sql_equality.py       # deterministic receipt check
```

`data/orders.csv` replaces BigQuery so the bundle runs anywhere; everything else
follows OKF's conventions, including footnote citations tied to `sources` ids and
the `executor`/`attester` contract on the computation.

Today the bundle is green:

```bash
$ provedown verify examples/okf/tables/orders.md
examples/okf/tables/orders.md: ok
  pass=5, fail=0, skip=0, error=0

$ provedown verify --okf examples/okf/computations/revenue-ytd.md
examples/okf/computations/revenue-ytd.md: ok
  pass=2, fail=0, skip=0, error=0
```

## The Scenario

It is January 2027. Finance issues an addendum: marketplace orders are
net-settled and recognized on marketplace payout, so they leave the
recognized-revenue figure.

An agent does everything right. It edits the sanctioned SQL in
`computations/revenue-ytd.md` to add one predicate:

```sql
WHERE o.order_status = 'delivered'
  AND o.channel <> 'marketplace'
  AND date_diff('day', o.order_ts::DATE, CURRENT_DATE) >= 30
  AND EXTRACT(YEAR FROM o.order_ts) = @year
```

It re-runs the executor, the attester confirms the receipt matches the new
sanctioned SQL, a human signs off, and the freshness window moves to the next
review cycle:

```yaml
verified:
  - { by: human:jsmith@acme, at: 2027-01-04T09:00:00Z }
status: stable
stale_after: 2027-12-31T00:00:00Z
```

## Every Signal Says Yes

Read the trust signals back after the change:

```python
>>> okf = parse_okf_file(Path("examples/okf/computations/revenue-ytd.md"))
>>> okf.metadata.status
'stable'
>>> okf.metadata.trust_tier()
'human-reviewed'
>>> okf.metadata.is_stale(date(2027, 2, 1))
False
```

The highest trust tier OKF defines. Current lifecycle state. Inside its freshness
window. Attested on every call. A consumer filtering for the most trustworthy
concepts in the bundle would pick this document first.

And its body is wrong. The `# Worked examples` section still reads:

> Against `data/orders.csv`, the sanctioned computation returns **225.50** for
> FY2025 and **513.40** for FY2026.

Those were the right numbers for the old policy. Nothing in OKF re-checks them,
because nothing in OKF knows they are derived from the computation directly
above them.

## What Provedown Catches

```bash
$ provedown verify --okf examples/okf/computations/revenue-ytd.md
examples/okf/computations/revenue-ytd.md: failed
  pass=0, fail=2, skip=0, error=0
  [fail] sql-results examples/okf/computations/revenue-ytd.md:61:1: value differs expected='225.50' actual='195.50'
  [fail] sql-results examples/okf/computations/revenue-ytd.md:63:1: value differs expected='513.40' actual='425.00'
$ echo $?
1
```

Both figures, with the old value, the new value, and the line to fix. The fix is
to update the prose and re-run; Provedown never rewrites the document, so the
correction stays an authoring decision.

## Why Each Mechanism Misses It

| Mechanism | What it established | Why the stale figure survived it |
| --- | --- | --- |
| `verified` | A human reviewed the document on 2027-01-04 | Reviewers approve definitions; nobody recomputed two figures in a prose paragraph |
| Attestation | The executed SQL was the sanctioned SQL | The receipt is about the *query*, not about the document's narrative |
| `stale_after` | The document is inside its review window | A calendar date cannot know a number changed in January |
| `status` | The document is current, not deprecated | Lifecycle state says nothing about arithmetic |
| Provedown | The figures reproduce from the computation | — |

These are complements, not competitors. Attestation is the only one that can
tell you the sanctioned query ran against the sanctioned warehouse; Provedown
cannot, and does not try. Provedown is the only one that re-derives the numbers a
reader actually sees.

## What Survives a Policy Change

Not every claim is policy-dependent. `tables/orders.md` states facts about the
table itself — row count, distinct orders, delivered orders, channels, fiscal
years — and those stay green through the addendum:

```bash
$ provedown verify examples/okf/tables/orders.md
examples/okf/tables/orders.md: ok
  pass=5, fail=0, skip=0, error=0
```

It is an ordinary OKF concept document, so it needs no `--okf`: Provedown already
parses OKF frontmatter, ignores it when scanning for markup, and leaves every key
untouched.

`metrics/revenue-legacy.md` shows the other end of the lifecycle. Provedown does
not treat `status: deprecated` specially, so a deprecated document's claims are
verified like any other — which is what makes a historical figure reproducible
rather than merely archived.

## Where the Boundary Falls

`metrics/revenue.md` states no figure of its own, and that is deliberate. A
metric document that quoted a headline number would need its own copy of the SQL
to verify it, which is exactly what OKF's attestation rules forbid: consumers
"MUST run and attest that computation rather than composing their own SUM."

Provedown verifies within a document. It has no cross-document references, so a
claim in `metrics/revenue.md` cannot execute the computation that lives in
`computations/revenue-ytd.md`. Keeping figures next to the computation that
produces them is the arrangement that works today, and it is also the one OKF's
own rules point at.

One more thing to know for bundle-wide runs: a document with no claims verifies
vacuously.

```bash
$ provedown verify examples/okf/metrics/revenue.md
examples/okf/metrics/revenue.md: ok
  pass=0, fail=0, skip=0, error=0
```

`ok` here means "nothing to check", not "checked and correct". Read the `pass`
count, not just the exit code, when you point Provedown at a whole bundle.

## In CI

Verify the claim-bearing documents on every change to the bundle:

```bash
provedown verify examples/okf/tables/orders.md
provedown verify --okf examples/okf/computations/revenue-ytd.md
```

Both exit non-zero on drift, so a policy change that lands without updating the
prose fails the build — in January, when the SQL changes, rather than in a
quarterly review.

[okf]: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf
