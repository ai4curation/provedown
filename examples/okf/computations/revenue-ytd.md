---
type: Attested Computation
title: Revenue for a fiscal year
description: Sanctioned SQL that produces the recognized-revenue figure for a given fiscal year, per Acme's FY2026 Revenue Recognition Policy.
tags: [finance, revenue, attested]
runtime: duckdb
parameters:
  - { name: year, type: integer, required: true }
executor:
  resource: ../skills/run-on-duckdb.md
  receipt: [job_id, executed_sql, result]
attester:
  resource: ../attesters/sql_equality.py
generated: { by: reference_agent/example, at: 2026-06-30T14:00:00Z }
verified:
  - { by: human:jsmith@acme, at: 2026-07-01T09:00:00Z }
status: stable
stale_after: 2026-12-31T00:00:00Z
sources:
  - id: revenue-policy
    resource: ../policies/revenue-recognition.md
    title: Revenue Recognition Policy (FY2026)
    author: human:jsmith@acme
    last_modified: 2026-06-15T00:00:00Z
  - id: orders-table
    resource: ../tables/orders.md
    title: Customer Orders
    author: team:data-platform
    last_modified: 2026-07-01T00:00:00Z
provedown:
  okf:
    bindings:
      fy2025: { year: 2025 }
      fy2026: { year: 2026 }
---

# Computation

```sql
SELECT printf('%.2f', SUM(o.net_amount)) AS revenue_usd
FROM read_csv_auto('../data/orders.csv') AS o
WHERE o.order_status = 'delivered'
  AND date_diff('day', o.order_ts::DATE, CURRENT_DATE) >= 30
  AND EXTRACT(YEAR FROM o.order_ts) = @year
```

This computation implements the four rules of the FY2026 Revenue Recognition
Policy: [^revenue-policy]

1. **Recognition trigger:** `order_status = 'delivered'` and the 30-day return
   window has closed.
2. **Recognized amount:** `net_amount`, excluding shipping and tax.
3. **Currency:** the sample dataset is USD-only, so the daily-rate join is
   omitted here.
4. **Fiscal year:** the calendar year of `order_ts`.

# Worked examples

Against `data/orders.csv`, the sanctioned computation returns
<span class="result" data-code="#fy2025">225.50<span class="method"></span></span>
for FY2025 and
<span class="result" data-code="#fy2026">513.40<span class="method"></span></span>
for FY2026.

Each figure runs the computation above with only the declared `year` parameter
substituted. The computation itself is never edited, so these are the values the
sanctioned query returns — not a second implementation that happens to agree
with it today.

# What the attester checks

`attesters/sql_equality.py` receives the receipt returned by
`skills/run-on-duckdb.md` and verifies two things:

1. **Provenance:** `receipt.executed_sql`, canonicalized, equals the SQL above
   canonicalized the same way. Any rewrite — a swapped table, an added filter, a
   dropped predicate — fails the check.
2. **Fidelity:** the value the caller is about to display equals
   `receipt.result[0]`.

A run whose SQL does not match is unattested, and the consumer must refuse to
display the value. Attestation asks whether the sanctioned query is what ran;
the worked examples above ask whether the numbers a reader sees still reproduce.
Neither answers the other's question.

# Freshness

`stale_after: 2026-12-31T00:00:00Z` mirrors the policy's annual review cycle.
That date is a calendar hint, not a measurement: `provedown verify --okf` is
what establishes that this document's figures are still correct today.

[^revenue-policy]: Revenue Recognition Policy (FY2026)
