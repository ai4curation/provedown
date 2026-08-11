# Customize Evidence Rendering

Choose how executable evidence appears to readers without changing what
Provedown verifies. Verification always reads the original source document;
these patterns only change its rendered presentation.

## Keep Evidence Visible

Use `pre` around `code` as the portable default. It preserves line breaks and
whitespace in HTML-based Markdown viewers and keeps the evidence immediately
available to readers.

=== "Raw .md"

    ````markdown
    <pre><code>
    samples = ["alpha", "beta", "gamma"]
    sample_count = len(samples)
    </code></pre>

    The cohort has <span class="result" data-code="sample_count">3<span class="method"></span></span> samples.
    ````

=== "Rendered HTML"

    <div class="pd-rendered-provedown" data-provedown-ignore="true">

    <pre><code>
    samples = ["alpha", "beta", "gamma"]
    sample_count = len(samples)
    </code></pre>

    <p>The cohort has <span class="result" data-code="sample_count">3<span class="method"></span></span> samples.</p>

    </div>

## Make Evidence Expandable

Wrap the executable block in native HTML `details` and `summary` elements when
readers should be able to reveal it on demand. This does not require custom CSS
or JavaScript in viewers that support raw HTML.

=== "Raw .md"

    ````markdown
    <details>
    <summary>Show supporting calculation</summary>

    <pre><code>
    samples = ["alpha", "beta", "gamma"]
    sample_count = len(samples)
    </code></pre>

    </details>

    The cohort has <span class="result" data-code="sample_count">3<span class="method"></span></span> samples.
    ````

=== "Rendered HTML"

    <div class="pd-rendered-provedown" data-provedown-ignore="true">

    <details>
    <summary>Show supporting calculation</summary>

    <pre><code>
    samples = ["alpha", "beta", "gamma"]
    sample_count = len(samples)
    </code></pre>

    </details>

    <p>The cohort has <span class="result" data-code="sample_count">3<span class="method"></span></span> samples.</p>

    </div>

Add the `open` attribute to `details` when the evidence should initially be
visible.

## Render Claims Without Code

For a claim-only reader view, give the evidence block a class and hide that
class in the renderer's stylesheet. The code remains in the source for
verification even though the stylesheet hides it from the reader view.

=== "Raw .md"

    ````markdown
    <pre class="hide-evidence"><code>
    samples = ["alpha", "beta", "gamma"]
    sample_count = len(samples)
    </code></pre>

    The cohort has <span class="result" data-code="sample_count">3<span class="method"></span></span> samples.
    ````

=== "Rendered HTML"

    <div class="pd-rendered-provedown" data-provedown-ignore="true">

    <pre class="hide-evidence"><code>
    samples = ["alpha", "beta", "gamma"]
    sample_count = len(samples)
    </code></pre>

    <p>The cohort has <span class="result" data-code="sample_count">3<span class="method"></span></span> samples.</p>

    </div>

=== "CSS"

    ```css
    .hide-evidence {
      display: none;
    }
    ```

This option requires control of the rendered page's CSS. GitHub and other
viewers that do not load that stylesheet will still show the evidence block.
Do not remove the block from the source document: Provedown needs it to
recompute the claim.

See the [markup contract](../reference/markup.md#rendering-in-markdown) for the
recognized elements and the [export paths](../explanations/export-paths.md) for
the distinction between source documents and reader-facing HTML.
