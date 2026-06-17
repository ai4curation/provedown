from pathlib import Path

from provedown import Status, parse_document, verify_document, verify_file


def test_sql_verifier_passes_inline_scalar_results() -> None:
    document = parse_document(
        """
<code data-language="sql">
create table orders(status varchar, amount integer);
insert into orders values ('paid', 120), ('refunded', 45), ('paid', 75);
</code>

The report includes
<span
  class="result"
  data-language="sql"
  data-code="select count(*) from orders where status = 'paid'"
>2<span class="method"></span></span>
paid orders totaling
<span
  class="result"
  data-language="sql"
  data-code="select '$' || sum(amount)::varchar from orders where status = 'paid'"
>$195<span class="method"></span></span>.
""".strip()
    )

    report = verify_document(document)

    assert report.ok
    assert report.summary() == {"pass": 2, "fail": 0, "skip": 0, "error": 0}
    assert {finding.verifier_id for finding in report.findings} == {"sql-results"}


def test_sql_verifier_reports_mismatch() -> None:
    document = parse_document(
        """
<code data-language="sql">
create table values_table(value integer);
insert into values_table values (42);
</code>
Answer:
<span
  class="result"
  data-language="sql"
  data-code="select value from values_table"
>41<span class="method"></span></span>
""".strip()
    )

    report = verify_document(document)

    assert not report.ok
    assert report.count(Status.FAIL) == 1
    assert report.findings[0].expected == "41"
    assert report.findings[0].actual == "42"


def test_named_sql_query_used_by_result() -> None:
    document = parse_document(
        """
<code data-language="sql">
create table orders(status varchar, amount integer);
insert into orders values ('paid', 120), ('refunded', 45), ('paid', 75);
</code>

<code name="paid_count" data-language="sql">
select count(*) from orders where status = 'paid'
</code>

Paid order count:
<span
  class="result"
  data-language="sql"
  data-code="#paid_count"
>2<span class="method"></span></span>
""".strip()
    )

    report = verify_document(document)

    assert report.ok
    assert report.count(Status.PASS) == 1


def test_sql_verifier_can_compare_multirow_single_column_as_set() -> None:
    document = parse_document(
        """
<code data-language="sql">
create table orders(region varchar, status varchar);
insert into orders values
  ('North', 'paid'),
  ('South', 'paid'),
  ('West', 'paid'),
  ('North', 'refunded');
</code>

Paid regions:
<span
  class="result"
  data-language="sql"
  data-compare="set"
  data-code="select region from orders where status = 'paid'"
>North,South,West<span class="method"></span></span>
""".strip()
    )

    report = verify_document(document)

    assert report.ok
    assert report.count(Status.PASS) == 1


def test_sql_verifier_reads_csv_relative_to_document(tmp_path: Path) -> None:
    (tmp_path / "orders.csv").write_text(
        "order_id,status,amount\n"
        "A001,paid,120.50\n"
        "A002,refunded,40.00\n"
        "A003,paid,75.00\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "report.md"
    report_path.write_text(
        """
<code data-language="sql">
create view orders as
select * from read_csv_auto('orders.csv');
</code>

Paid order count:
<span
  class="result"
  data-language="sql"
  data-code="select count(*) from orders where status = 'paid'"
>2<span class="method"></span></span>
""".strip(),
        encoding="utf-8",
    )

    report = verify_file(report_path)

    assert report.ok
