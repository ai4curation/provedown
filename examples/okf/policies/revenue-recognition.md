---
type: Policy
title: Revenue Recognition Policy (FY2026)
description: When Acme Retail recognizes revenue on a customer order.
tags: [finance, revenue, policy]
author: human:jsmith@acme
status: stable
stale_after: 2026-12-31T00:00:00Z
---

# Rules

1. **Recognition trigger.** Revenue is recognized when `order_status = 'delivered'`
   and the 30-day return window has closed.
2. **Recognized amount.** `net_amount`, which is `gross_amount - discount_amount`.
   Shipping and tax are pass-through liabilities and are excluded.
3. **Currency.** Non-USD orders convert at the `order_ts` daily reference rate.
4. **Fiscal year.** The calendar year of `order_ts`.

# Review cycle

Finance re-issues this policy each January. Concepts that cite it carry
`stale_after: 2026-12-31T00:00:00Z` so consumers re-verify against the new
policy before serving.
