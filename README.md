# Provedown

Provedown makes claims in Markdown and HTML reports independently verifiable.
Attach small Python or DuckDB SQL calculations to important values, then run a
deterministic verifier to catch stale or incorrect prose.

[Documentation](https://ai4curation.io/provedown/) |
[First verified report](https://ai4curation.io/provedown/tutorials/first-verified-report/) |
[Markup reference](https://ai4curation.io/provedown/reference/markup/)

## Install

Provedown requires Python 3.10 or later and is available from PyPI:

```bash
pip install provedown
```

## Quick Start

Create `report.md`:

````markdown
# Order Summary

<pre><code>
orders = [
    {"status": "paid", "amount": 120},
    {"status": "refunded", "amount": 45},
    {"status": "paid", "amount": 75},
]
paid = [order for order in orders if order["status"] == "paid"]
total = sum(order["amount"] for order in paid)
</code></pre>

The report includes <span class="result" data-code="len(paid)">2<span class="method"></span></span> paid orders totaling <span class="result" data-code="f'${total}'">$195<span class="method"></span></span>.
````

Verify it:

```bash
provedown verify report.md
```

Provedown reruns the calculation and checks both authored values:

```text
report.md: ok
  pass=2, fail=0, skip=0, error=0
```

The HTML elements have separate jobs:

- `code` contains executable evidence. The surrounding `pre` preserves its
  multiline layout for readers.
- `span.result` contains an authored value and the expression that must
  reproduce it.

Provedown reports mismatches but does not rewrite the document. The Markdown or
HTML file remains the source of truth.

## Capabilities

- Execute embedded Python or DuckDB SQL.
- Query local CSV files from SQL or Python reports.
- Check exact values, numeric tolerances, and set equality.
- Reuse named calculations across multiple claims.
- Inspect dependencies between evidence and claims.
- Render evidence as visible, expandable, or claim-only HTML.

## Learn More

- [Use SQL and CSV files](https://ai4curation.io/provedown/how-to-guides/use-sql-and-csv-files/)
- [Customize evidence rendering](https://ai4curation.io/provedown/how-to-guides/customize-evidence-rendering/)
- [CLI reference](https://ai4curation.io/provedown/reference/cli/)
- [Python API](https://ai4curation.io/provedown/reference/python-api/)
