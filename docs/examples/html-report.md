# Pure HTML Report

A Provedown document written as plain HTML, useful when a pipeline already emits HTML or when Markdown is not part of the authoring workflow.

The tabs show the same Provedown document in two forms. The raw view shows the literal Provedown contract; the rendered HTML is generated from that source with `pandoc`.

=== "Raw .html"

    ````html
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Inventory Provedown Report</title>
      </head>
      <body>
        <h1>Inventory Check</h1>
        <p>
          This report is authored as plain HTML. Provedown reads the same
          executable code and result assertion contract it reads from Markdown.
        </p>

        <pre><code>
    from statistics import mean

    counts = [12, 18, 15]
    mean_count = mean(counts)
        </code></pre>

        <p>
          The average count is
          <span class="result" data-code="f'{mean_count:.1f}'">15.0<span class="method"></span></span>.
        </p>

        <p>
          The maximum count is
          <span class="result" data-code="max(counts)">18<span class="method"></span></span>.
        </p>
      </body>
    </html>
    ````

=== "Rendered HTML"

    <div class="pd-rendered-provedown" data-provedown-ignore="true">
    <h1 id="inventory-check">Inventory Check</h1><p>This report is authored as plain HTML. Provedown reads the same executable code and result assertion contract it reads from Markdown.</p><pre><code>from statistics import mean

    counts = [12, 18, 15]
    mean_count = mean(counts)
        </code></pre><p>The average count is <span class="result" data-code="f&#39;{mean_count:.1f}&#39;">15.0<span class="method"></span></span>.</p><p>The maximum count is <span class="result" data-code="max(counts)">18<span class="method"></span></span>.</p>
    </div>

Verify this example with:

```bash
provedown verify examples/html-report.html
```
