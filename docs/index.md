# Provedown

<div class="pd-hero" markdown>

Markdown-native verifiable literate documents. Agents or people create
markdown/HTML/text reports, attach small executable
evidence to the claims that matter, and let a deterministic verifier check
the numbers.

[Start the tutorial](tutorials/first-verified-report.md){ .md-button .md-button--primary }
[Read the markup contract](reference/markup.md){ .md-button }

</div>

## What It Does

Provedown keeps the human-readable document as the source of truth. Values in
prose are authored claims, not generated render output, and verifier plugins can
recompute those claims from embedded evidence.

<!-- pd-homepage-example:start -->
<!-- Generated from examples/homepage-orders.md by scripts/render_example_tabs.py. -->
<div class="pd-proof-pair" data-provedown-ignore="true" markdown>

<div class="pd-proof-panel pd-proof-reader">

<p class="pd-proof-label">Styled reader view</p>

<pre><code>
orders = [
    {"status": "paid", "amount": 120},
    {"status": "refunded", "amount": 45},
    {"status": "paid", "amount": 75},
]
paid = [order for order in orders if order["status"] == "paid"]
total = sum(order["amount"] for order in paid)
</code></pre><p>The report includes <span class="result" data-code="len(paid)">2<span class="method"></span></span> paid orders totaling <span class="result" data-code="f&#39;${total}&#39;">$195<span class="method"></span></span>.</p>

</div>

<div class="pd-proof-panel pd-proof-source" markdown>

<p class="pd-proof-label">Provedown source</p>

````markdown
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

</div>

</div>
<!-- pd-homepage-example:end -->

The styled reader view is a documentation preview, not the default output of
every Markdown viewer. Pandoc renders the same source shown alongside it, then
this site's CSS hides the `<pre>` block and accents the result spans. GitHub and
other viewers that do not load that CSS show the code and render the claims as
ordinary prose.

In the source, `<code>` marks executable evidence and `<pre>` preserves its
multiline layout for readers. Reader-first reports can make that block
expandable or hide it from rendered output; the
[rendering guide](how-to-guides/customize-evidence-rendering.md) shows each
option alongside its source.

If the data or filtering logic changes, `provedown verify` catches stale prose
before it ships.

## Find Your Path

<div class="grid cards" markdown>

- **Learn the loop**

    Create a first report, run the verifier, and see how mismatches are
    reported.

    [First verified report](tutorials/first-verified-report.md)

- **Use real inputs**

    Import standard-library modules, read local CSV files, and verify prose
    claims against computed summaries.

    [Python modules and data files](how-to-guides/use-python-modules-and-data-files.md)

- **Inspect and lint**

    Understand which code supports which claims, then catch fragile document
    structure before verification.

    [Inspect dependencies](how-to-guides/inspect-claim-dependencies.md)

- **Check the contract**

    Review the recognized HTML elements, attributes, comparison policies, and
    CLI behavior.

    [Markup contract](reference/markup.md)

- **Understand hallucination checks**

    See how Provedown turns important prose claims into values that deterministic
    tools can challenge.

    [Hallucination detection](explanations/hallucination-detection.md)

</div>

## Documentation Map

This documentation follows the Diataxis structure:

- **Tutorials** teach new workflows step by step.
- **How-to guides** solve focused operational tasks.
- **Reference** describes stable APIs, commands, and file formats.
- **Explanations** discuss design choices and tradeoffs.

The project is still early, so examples and reference pages describe what exists
today while design notes track where the format is heading.
