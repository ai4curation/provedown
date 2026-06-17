# CSV Sales Summary

A more realistic Provedown document that imports Python standard-library modules, reads a local CSV file, and verifies summary claims in prose.

The tabs show the same Provedown document in two forms. The rendered view is generated from the raw source with `pandoc`; the raw view shows the literal Provedown contract.

=== "Rendered"

    <div class="pd-rendered-provedown" data-provedown-ignore="true">
    <h1 id="csv-sales-summary">CSV Sales Summary</h1><p>This Provedown document imports Python standard-library modules, reads a data file next to the report, computes summary values, and asserts those values in the prose.</p><p>The source data is <a href="data/orders.csv"><code>data/orders.csv</code></a>.</p><pre><code>
    from collections import Counter
    from csv import DictReader
    from decimal import Decimal
    from pathlib import Path

    data_path = Path("data/orders.csv")
    with data_path.open(encoding="utf-8", newline="") as stream:
        rows = list(DictReader(stream))

    paid_rows = [row for row in rows if row["status"] == "paid"]
    paid_total = sum(Decimal(row["amount"]) for row in paid_rows)
    paid_average = paid_total / len(paid_rows)
    orders_by_region = Counter(row["region"] for row in rows)
    paid_regions = sorted({row["region"] for row in paid_rows})
    largest_order = max(rows, key=lambda row: Decimal(row["amount"]))
    </code></pre><p>The file contains <span class="result" data-code="len(rows)">6<span class="method"></span></span> orders.</p><p>Of those, <span class="result" data-code="len(paid_rows)">4<span class="method"></span></span> are paid orders.</p><p>Paid orders total <span class="result" data-code="paid_total">461.00<span class="method"></span></span>.</p><p>The average paid order is <span class="result" data-code="paid_average">115.25<span class="method"></span></span>.</p><p>The North region has <span class="result" data-code="orders_by_region[&#39;North&#39;]">2<span class="method"></span></span> orders.</p><p>Paid orders appear in the regions <span class="result" data-code="paid_regions" data-compare="set">North,South,West<span class="method"></span></span>.</p><p>The largest order id is <span class="result" data-code="largest_order[&#39;order_id&#39;]">A004<span class="method"></span></span>.</p><pre><code name="topline">f"{len(paid_rows)} paid orders totaling ${paid_total}"</code></pre><p>The compact topline is <span class="result" data-code="#topline">4 paid orders totaling $461.00<span class="method"></span></span>.</p>
    </div>

=== "Raw .md"

    ````markdown
    # CSV Sales Summary

    This Provedown document imports Python standard-library modules, reads a data
    file next to the report, computes summary values, and asserts those values in
    the prose.

    The source data is [`data/orders.csv`](data/orders.csv).

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
    paid_average = paid_total / len(paid_rows)
    orders_by_region = Counter(row["region"] for row in rows)
    paid_regions = sorted({row["region"] for row in paid_rows})
    largest_order = max(rows, key=lambda row: Decimal(row["amount"]))
    </code></pre>

    The file contains <span class="result" data-code="len(rows)">6<span class="method"></span></span> orders.

    Of those, <span class="result" data-code="len(paid_rows)">4<span class="method"></span></span> are paid orders.

    Paid orders total <span class="result" data-code="paid_total">461.00<span class="method"></span></span>.

    The average paid order is <span class="result" data-code="paid_average">115.25<span class="method"></span></span>.

    The North region has <span class="result" data-code="orders_by_region['North']">2<span class="method"></span></span> orders.

    Paid orders appear in the regions <span class="result" data-code="paid_regions" data-compare="set">North,South,West<span class="method"></span></span>.

    The largest order id is <span class="result" data-code="largest_order['order_id']">A004<span class="method"></span></span>.

    <pre><code name="topline">f"{len(paid_rows)} paid orders totaling ${paid_total}"</code></pre>

    The compact topline is <span class="result" data-code="#topline">4 paid orders totaling $461.00<span class="method"></span></span>.
    ````

Verify this example with:

```bash
provedown verify examples/data-file-report.md
```
