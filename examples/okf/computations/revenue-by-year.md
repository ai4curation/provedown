---
type: Attested Computation
title: Revenue for a fiscal year
description: Net revenue across delivered orders in one fiscal year.
resource: https://example.invalid/acme/sales/orders
tags: [sales, revenue]
runtime: duckdb
parameters:
  - { name: year, type: integer, required: true }
generated: { by: reference_agent/example, at: 2026-06-30T14:00:00Z }
verified:
  - { by: human:jsmith@acme, at: 2026-07-01T09:00:00Z }
status: stable
stale_after: 2026-12-31
sources:
  - id: revenue-policy
    resource: ../policies/revenue-recognition.md
    title: Revenue Recognition Policy (FY2026)
    author: human:jsmith@acme
    last_modified: 2026-06-15
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

Each claim runs the computation above with only the declared `year` parameter
substituted. The computation itself is never edited, so the value a reader sees
is the value the sanctioned query returns.
