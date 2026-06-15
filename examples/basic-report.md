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
