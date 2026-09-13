---
type: Log
title: Acme Retail bundle history
---

# Bundle history

## 2026-07-01

- **Verified** the bundle for OKF v0.2 conformance. `human:kliu@acme` reviewed
  every `verified` and `sources` entry.

## 2026-06-30

- **Re-generated** `metrics/revenue.md` and `computations/revenue-ytd.md` after
  Finance published the FY2026 revenue recognition policy. Set `stale_after` on
  both revenue concepts to `2026-12-31T00:00:00Z`.
- **Added** worked examples to `computations/revenue-ytd.md` and consumer notes
  to `tables/orders.md`, both carrying figures, both verified with Provedown.

## 2026-04-15

- **Deprecated** the pre-FY2026 revenue definition. Moved to
  `metrics/revenue-legacy.md` with `status: deprecated`.

## 2026-02-10

- **Bootstrapped** by `reference_agent/example`. Initial trust tier:
  machine-confirmed across the board, with finance-critical concepts flagged for
  human review.
