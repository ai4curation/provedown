# Use Python Modules And Data Files

Use this pattern when a report needs ordinary Python imports, local input files,
and several prose claims derived from the same setup code.

## Put Data Next To The Document

For a document at `reports/sales.md`, keep small example data nearby:

```text
reports/
  sales.md
  data/
    orders.csv
```

When you run `provedown verify reports/sales.md`, the Python verifier executes
with `reports/` as the working directory. Relative paths in code blocks are
therefore resolved relative to the document, not relative to the shell command's
current directory.

## Import Standard-Library Modules Normally

Write ordinary Python in a `<code>` block:

````markdown
<pre><code>
from collections import Counter
from csv import DictReader
from decimal import Decimal
from pathlib import Path

data_path = Path("data/orders.csv")
with data_path.open(encoding="utf-8", newline="") as stream:
    rows = list(DictReader(stream))

paid_rows = [row for row in rows if row["status"] == "paid"]
paid_total = sum(Decimal(row["amount"]) for row in paid_rows)
orders_by_region = Counter(row["region"] for row in rows)
</code></pre>
````

The `<pre><code>` wrapper renders nicely in MkDocs and still gives Provedown a
`<code>` element to execute.

## Assert The Values In Prose

Attach short expressions directly to result spans:

````markdown
The file contains <span class="result" data-code="len(rows)">6<span class="method"></span></span> orders.

Paid orders total <span class="result" data-code="paid_total">461.00<span class="method"></span></span>.

The North region has <span class="result" data-code="orders_by_region['North']">2<span class="method"></span></span> orders.
````

The authored values, such as `6`, `461.00`, and `2`, are the claims being
verified. The code is the evidence used to falsify or pass those claims.

## Use Named Expressions For Longer Claims

When the expression is too long for an attribute, put it in a named code block
and reference it with `data-code="#name"`:

````markdown
<pre><code name="topline">f"{len(paid_rows)} paid orders totaling ${paid_total}"</code></pre>

The compact topline is <span class="result" data-code="#topline">4 paid orders totaling $461.00<span class="method"></span></span>.
````

Named code referenced by a result assertion must be an expression because the
Python verifier evaluates it with `eval()`.

## Compare Unordered Values As Sets

Use `data-compare="set"` when order should not matter:

````markdown
Paid orders appear in the regions <span class="result" data-code="paid_regions" data-compare="set">North,South,West<span class="method"></span></span>.
````

The authored value can be comma-separated text. The computed value can be a
Python set, list, tuple, dict, or string representation of a collection.

## Verify The Example

The docs include a complete version of this pattern:

```bash
uv run provedown verify docs/examples/data-file-report.md
```

That example uses only Python's standard library and the checked-in CSV file at
`docs/examples/data/orders.csv`.
