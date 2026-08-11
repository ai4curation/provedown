# Basic Verified Report

A compact Provedown document with inline Python, scalar result assertions, set comparison, tolerance comparison, and a named expression.

The tabs show the same Provedown document in two forms. The raw view shows the literal Provedown contract; the rendered HTML is generated from that source with `pandoc`.

=== "Raw .md"

    ````markdown
    # Basic Verified Report

    This Provedown document checks a small in-memory cohort.

    <pre><code>
    samples = ["alpha", "beta", "gamma"]
    passed = [name for name in samples if "a" in name]
    rate = len(passed) / len(samples)
    </code></pre>

    The cohort has <span class="result" data-code="len(samples)">3<span class="method"></span></span> samples.

    The passing labels are <span class="result" data-code="passed" data-compare="set">alpha,beta,gamma<span class="method"></span></span>.

    The pass rate is <span class="result" data-code="rate" tol="1e-6">1.0<span class="method"></span></span>.

    <pre><code name="summary">f"{len(passed)}/{len(samples)}"</code></pre>

    The compact summary is <span class="result" data-code="#summary">3/3<span class="method"></span></span>.
    ````

=== "Rendered HTML"

    <div class="pd-rendered-provedown" data-provedown-ignore="true">
    <h1 id="basic-verified-report">Basic Verified Report</h1><p>This Provedown document checks a small in-memory cohort.</p><pre><code>
    samples = ["alpha", "beta", "gamma"]
    passed = [name for name in samples if "a" in name]
    rate = len(passed) / len(samples)
    </code></pre><p>The cohort has <span class="result" data-code="len(samples)">3<span class="method"></span></span> samples.</p><p>The passing labels are <span class="result" data-code="passed" data-compare="set">alpha,beta,gamma<span class="method"></span></span>.</p><p>The pass rate is <span class="result" data-code="rate" data-tol="1e-6">1.0<span class="method"></span></span>.</p><pre><code name="summary">f"{len(passed)}/{len(samples)}"</code></pre><p>The compact summary is <span class="result" data-code="#summary">3/3<span class="method"></span></span>.</p>
    </div>

Verify this example with:

```bash
provedown verify examples/basic-report.md
```
