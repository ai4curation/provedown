# SQL CSV Sales Summary

A Provedown document that uses DuckDB SQL to query a local CSV file and verify summary claims in prose.

The tabs show the same Provedown document in two forms. The raw view shows the literal Provedown contract; the rendered HTML is generated from that source with `pandoc`.

=== "Raw .md"

    ````markdown
    # SQL CSV Sales Summary

    This Provedown document verifies CSV summary claims with DuckDB SQL.

    <pre><code data-language="sql">
    create view orders as
    select *
    from read_csv_auto('data/orders.csv');
    </code></pre>

    The CSV contains <span class="result" data-language="sql" data-code="select count(*) from orders">6<span class="method"></span></span> orders.

    There are <span class="result" data-language="sql" data-code="select count(*) from orders where status = 'paid'">4<span class="method"></span></span> paid orders.

    Paid orders total <span class="result" data-language="sql" data-code="select printf('$%.2f', sum(amount)) from orders where status = 'paid'">$461.00<span class="method"></span></span>.

    The paid regions are <span class="result" data-language="sql" data-compare="set" data-code="select distinct region from orders where status = 'paid'">North,South,West<span class="method"></span></span>.

    <pre><code name="sql_topline" data-language="sql">
    select count(*)::varchar || ' paid orders totaling ' || printf('$%.2f', sum(amount))
    from orders
    where status = 'paid'
    </code></pre>

    The SQL topline is <span class="result" data-language="sql" data-code="#sql_topline">4 paid orders totaling $461.00<span class="method"></span></span>.
    ````

=== "Rendered HTML"

    <div class="pd-rendered-provedown" data-provedown-ignore="true">
    <h1 id="sql-csv-sales-summary">SQL CSV Sales Summary</h1><p>This Provedown document verifies CSV summary claims with DuckDB SQL.</p><pre><code data-language="sql">
    create view orders as
    select *
    from read_csv_auto('data/orders.csv');
    </code></pre><p>The CSV contains <span class="result" data-language="sql" data-code="select count(*) from orders">6<span class="method"></span></span> orders.</p><p>There are <span class="result" data-language="sql" data-code="select count(*) from orders where status = &#39;paid&#39;">4<span class="method"></span></span> paid orders.</p><p>Paid orders total <span class="result" data-language="sql" data-code="select printf(&#39;$%.2f&#39;, sum(amount)) from orders where status = &#39;paid&#39;">$461.00<span class="method"></span></span>.</p><p>The paid regions are <span class="result" data-language="sql" data-compare="set" data-code="select distinct region from orders where status = &#39;paid&#39;">North,South,West<span class="method"></span></span>.</p><pre><code name="sql_topline" data-language="sql">
    select count(*)::varchar || ' paid orders totaling ' || printf('$%.2f', sum(amount))
    from orders
    where status = 'paid'
    </code></pre><p>The SQL topline is <span class="result" data-language="sql" data-code="#sql_topline">4 paid orders totaling $461.00<span class="method"></span></span>.</p>
    </div>

Verify this example with:

```bash
provedown verify examples/sql-sales-summary.md
```
