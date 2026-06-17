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
