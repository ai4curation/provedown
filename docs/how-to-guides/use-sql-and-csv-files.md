# Use SQL And CSV Files

Use `data-language="sql"` to verify prose claims with DuckDB SQL. DuckDB can
query nearby CSV files directly with `read_csv_auto()`.

## Create A SQL Setup Cell

Create a view over a CSV file:

````markdown
<pre><code data-language="sql">
create view orders as
select *
from read_csv_auto('data/orders.csv');
</code></pre>
````

When the document is verified from disk, relative paths resolve from the
document's directory.

## Write SQL Result Assertions

Put a SQL query in `data-code`:

````markdown
The CSV contains <span class="result" data-language="sql" data-code="select count(*) from orders">6<span class="method"></span></span> orders.
````

The SQL verifier expects result queries to return a value:

- one row and one column becomes a scalar;
- multiple rows and one column become a list, useful with `data-compare="set"`;
- multiple columns become tuples.

## Query A CSV Directly

You can also query the CSV directly from the result span:

````markdown
Paid orders total <span class="result" data-language="sql" data-code="select printf('$%.2f', sum(amount)) from read_csv_auto('data/orders.csv') where status = 'paid'">$461.00<span class="method"></span></span>.
````

For a complete example, see [SQL CSV Sales Summary](../examples/sql-sales-summary.md).
