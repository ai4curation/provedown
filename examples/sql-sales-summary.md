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
