---
type: BigQuery Table
title: Customer Orders
description: One row per customer order.
resource: https://example.invalid/acme/sales/orders
tags: [sales, orders, revenue]
generated: { by: reference_agent/example, at: 2026-06-30T14:00:00Z }
verified:
  - { by: human:kliu@acme, at: 2026-07-01T16:00:00Z }
status: stable
stale_after: 2026-12-31
sources:
  - id: warehouse-schema
    resource: https://example.invalid/wiki/warehouse/schemas/sales
    title: Acme Retail warehouse schema
    author: team:data-platform
    usage_count: 1240
    last_modified: 2026-06-15
provedown:
  default_language: duckdb
---

# Schema

| Column | Type | Description |
|--------|------|-------------|
| `order_id` | STRING | Globally unique order id. |
| `order_ts` | TIMESTAMP | Order placement time; drives fiscal-year assignment. |
| `order_status` | STRING | Revenue is recognized at `delivered`. |
| `net_amount` | NUMERIC | Net of discounts. |

# Examples

<pre><code name="orders">
CREATE OR REPLACE VIEW orders AS
SELECT * FROM read_csv_auto('../data/orders.csv');
</code></pre>

<code use="orders"/>

The table holds
<span class="result" data-code="SELECT COUNT(*) FROM orders">7<span class="method"></span></span>
orders, of which
<span class="result" data-code="SELECT COUNT(*) FROM orders WHERE order_status = 'delivered'">5<span class="method"></span></span>
are delivered, spanning
<span class="result" data-code="SELECT COUNT(DISTINCT EXTRACT(YEAR FROM order_ts)) FROM orders">2<span class="method"></span></span>
fiscal years.

This document is an ordinary OKF concept document, not an Attested Computation.
It needs no shim: Provedown already ignores OKF frontmatter when it looks for
executable markup, and leaves every OKF key untouched.
