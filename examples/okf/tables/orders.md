---
type: BigQuery Table
title: Customer Orders
description: One row per customer order across web, mobile, and marketplace channels. The grain is the order, not the line item.
resource: https://example.invalid/acme/sales/orders
tags: [sales, orders, revenue]
generated: { by: reference_agent/example, at: 2026-06-30T14:00:00Z }
verified:
  - { by: human:kliu@acme, at: 2026-07-01T16:00:00Z }
status: stable
stale_after: 2026-12-31T00:00:00Z
sources:
  - id: warehouse-schema
    resource: https://example.invalid/wiki/warehouse/schemas/sales
    title: Acme Retail warehouse schema — sales dataset
    author: team:data-platform
    usage_count: 1240
    last_modified: 2026-06-15T00:00:00Z
  - id: revenue-policy
    resource: ../policies/revenue-recognition.md
    title: Revenue Recognition Policy (FY2026)
    author: human:jsmith@acme
    last_modified: 2026-06-15T00:00:00Z
provedown:
  default_language: duckdb
---

# Schema

| Column | Type | Description |
|---|---|---|
| `order_id` | STRING | Globally unique order id. [^warehouse-schema] |
| `customer_id` | STRING | FK into `customers`. [^warehouse-schema] |
| `order_ts` | TIMESTAMP | Order placement time. Drives fiscal-year assignment. [^revenue-policy] |
| `order_status` | STRING | Revenue is recognized only at `delivered`, once the 30-day return window closes. [^revenue-policy] |
| `gross_amount` | NUMERIC | Pre-discount subtotal. Excludes tax and shipping. [^warehouse-schema] |
| `discount_amount` | NUMERIC | Promo codes, loyalty credits, price adjustments. [^warehouse-schema] |
| `net_amount` | NUMERIC | `gross_amount - discount_amount`. The recognized amount. [^revenue-policy] |
| `currency` | STRING | ISO 4217 code. Non-USD converts on the `order_ts` date. [^revenue-policy] |
| `channel` | STRING | Order origin: `web`, `mobile`, `marketplace`. |

# Notes for consumers

<pre><code name="orders">
CREATE OR REPLACE VIEW orders AS
SELECT * FROM read_csv_auto('../data/orders.csv');
</code></pre>

<code use="orders"/>

The grain assumption trips up new analysts: `SUM(net_amount) GROUP BY order_id`
is a no-op, because the table holds
<span class="result" data-code="SELECT COUNT(*) FROM orders">10<span class="method"></span></span>
rows for
<span class="result" data-code="SELECT COUNT(DISTINCT order_id) FROM orders">10<span class="method"></span></span>
distinct orders. Of those,
<span class="result" data-code="SELECT COUNT(*) FROM orders WHERE order_status = 'delivered'">7<span class="method"></span></span>
are delivered, spread across
<span class="result" data-code="SELECT COUNT(DISTINCT channel) FROM orders">3<span class="method"></span></span>
channels and
<span class="result" data-code="SELECT COUNT(DISTINCT EXTRACT(YEAR FROM order_ts)) FROM orders">2<span class="method"></span></span>
fiscal years.

These are facts about the table rather than about the revenue policy, so they
survive a policy change. Verify them with plain `provedown verify`: this is an
ordinary OKF concept document, and it needs no shim.

[^warehouse-schema]: Acme Retail warehouse schema — sales dataset
[^revenue-policy]: Revenue Recognition Policy (FY2026)
