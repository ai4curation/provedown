# First Verified Report

This tutorial creates a tiny Provedown document and verifies that a prose claim
matches the code attached to it.

## Prerequisites

Install Provedown, then use the `provedown` command in your shell.

## Create A Report

Create a file named `report.md`:

````markdown
# Example Report

<code>
samples = ["alpha", "beta", "gamma"]
sample_count = len(samples)
</code>

The cohort has <span class="result" data-code="sample_count">3<span class="method"></span></span> samples.
````

The document is ordinary Markdown plus two Provedown contracts:

- `<code>` contains Python that will run during verification.
- `<span class="result">` contains an authored prose value and the expression
  that should reproduce it.

## Verify It

Run:

```bash
provedown verify report.md
```

Expected text output:

```text
report.md: ok
  pass=1, fail=0, skip=0, error=0
  [pass] python-results report.md:7:16: value matches exactly expected='3' actual='3'
```

The exact line and column can differ if your file has different spacing.

## See A Failure

Change the authored value from `3` to `4`:

````markdown
The cohort has <span class="result" data-code="sample_count">4<span class="method"></span></span> samples.
````

Run verification again:

```bash
provedown verify report.md
```

The command exits with status `1` and reports a failed assertion:

```text
report.md: failed
  pass=0, fail=1, skip=0, error=0
  [fail] python-results report.md:7:16: value differs expected='4' actual='3'
```

The verifier does not rewrite the document. It tells you that the document's
claim is false under the current code and environment.

## What You Have

You now have a readable Markdown report whose scalar claim can be checked by a
non-LLM verifier. That is the core Provedown loop:

1. Write prose for people.
2. Attach minimal executable evidence.
3. Recompute and compare the authored claim.
