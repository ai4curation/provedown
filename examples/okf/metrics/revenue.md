---
type: Metric
title: Revenue
description: Recognized revenue for a period, per Acme's FY2026 revenue-recognition policy. Backed by an Attested Computation.
tags: [finance, revenue, headline-metric]
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
---

# Definition

Revenue for a fiscal year is the sum of `net_amount` over orders that reached
`order_status = 'delivered'`, completed the 30-day return window, and fall in the
fiscal year by `order_ts`. [^revenue-policy]

The sanctioned computation is
[`computations/revenue-ytd.md`](../computations/revenue-ytd.md). Consumers must
run and attest that computation rather than composing their own `SUM`.

# Reporting cuts

- **By fiscal year:** the sanctioned computation takes `year` as its sole parameter.
- **By channel:** an approved narration, not a new metric. Join the receipt's
  rows to `orders.channel` client-side. Do not rewrite the sanctioned SQL.

# Trust and freshness

- **Verified:** Finance sign-off on 2026-07-01, against the FY2026 policy.
- **Stale after 2026-12-31:** Finance re-issues the policy each January.

This document states no figure of its own, by design: the numbers live with the
computation that produces them, where Provedown can check them without a second
implementation of the policy. A metric document that quoted a headline number
here would need its own copy of the SQL, which is exactly what OKF's attestation
rules forbid.

[^revenue-policy]: Revenue Recognition Policy (FY2026)
