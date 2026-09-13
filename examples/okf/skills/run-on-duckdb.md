---
type: Skill
title: Run an Attested Computation on DuckDB
description: Executor instructions for running a sanctioned computation and returning a receipt.
tags: [executor, duckdb]
---

# Instructions

1. Read the computation from the concept document's `# Computation` section.
   Do not edit it.
2. Substitute values for the declared `parameters` only.
3. Execute the result against the bundle's DuckDB connection.
4. Return a receipt with `job_id`, `executed_sql` (the statement as executed,
   after substitution), and `result` (the returned rows).

The caller passes the receipt to the computation's `attester` before displaying
any value.

# Relationship to Provedown

Provedown does not implement this executor, and does not read `executor` or
`attester`: both keys are preserved verbatim and ignored. Attestation covers the
runtime path — was the sanctioned SQL what ran against the sanctioned warehouse.
Provedown covers the document — do the figures a reader sees still reproduce.
