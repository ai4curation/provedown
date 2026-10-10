# Acme Retail

A small OKF bundle, mirroring the layout of the reference `acme_retail` bundle,
with claims that Provedown can verify.

* [tables](tables/orders.md) - the table the bundle grounds against.
* [metrics](metrics/revenue.md) - business definitions of Acme's headline numbers.
* [computations](computations/revenue-ytd.md) - sanctioned SQL as Attested Computations.
* [policies](policies/revenue-recognition.md) - source-of-truth Finance policy documents.
* [skills](skills/run-on-duckdb.md) - executor instructions for running computations.
* [attesters](attesters/sql_equality.py) - deterministic verification of computation receipts.

`data/orders.csv` stands in for the warehouse table so the bundle runs anywhere.
A real bundle would point at BigQuery and carry per-directory `index.md` files
for navigation; those are generated, so they are omitted here.

Verify it:

```bash
provedown verify examples/okf/tables/orders.md
provedown verify --okf examples/okf/computations/revenue-ytd.md
```
