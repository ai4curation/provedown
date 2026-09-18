---
type: Metric
title: Revenue (legacy, pre-FY2026)
description: The revenue definition in force before the FY2026 policy. Kept for historical reproducibility.
tags: [finance, revenue, deprecated]
generated: { by: reference_agent/example, at: 2026-02-10T11:00:00Z }
verified:
  - { by: human:jsmith@acme, at: 2026-02-11T09:00:00Z }
status: deprecated
---

# Definition

Revenue was the sum of `net_amount` over orders at `order_status = 'delivered'`,
with no return-window wait.

# Why it was replaced

The FY2026 policy added the 30-day return window, so figures produced under this
definition are not comparable with current ones.

`status: deprecated` keeps this document out of new work while preserving it for
reproducing historical reports. Provedown does not treat `status` specially: a
deprecated document's claims are verified like any other, which is what makes a
historical figure reproducible rather than merely archived.
