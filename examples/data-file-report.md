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
