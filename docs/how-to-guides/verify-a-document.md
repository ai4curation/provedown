# Verify A Document

Use `provedown verify` to check one or more Provedown Markdown or HTML files.

## Verify One File

```bash
provedown verify report.md
```

Text output summarizes each file and prints one line per finding:

```text
report.md: ok
  pass=1, fail=0, skip=0, error=0
  [pass] python-results report.md:5:16: value matches exactly expected='42' actual='42'
```

The command exits with `0` when every report is ok. A report is ok when it has no
`fail` or `error` findings. `skip` findings are allowed.

## Verify Multiple Files

```bash
provedown verify report.md appendix.md
```

Each path is parsed and verified independently.

## Verify HTML

HTML documents use the same Provedown contract:

```html
<pre><code>
x = 40 + 2
</code></pre>

<p>
  The answer is
  <span class="result" data-code="x">42<span class="method"></span></span>.
</p>
```

Verify the file the same way:

```bash
provedown verify report.html
```

## Relative Data Files

When verifying a file from disk, verifiers run with the document's directory as
the working directory. This lets reports read nearby data files with relative
paths:

````markdown
<pre><code>
from pathlib import Path

value = Path("data/value.txt").read_text(encoding="utf-8").strip()
</code></pre>

The value is <span class="result" data-code="value">42<span class="method"></span></span>.
````

If the document is `reports/summary.md`, the path above resolves to
`reports/data/value.txt`.

## Use JSON Output

```bash
provedown verify --format json report.md
```

JSON output is intended for CI, editor integrations, and scripts. It includes an
overall `ok` field, per-file summaries, and structured findings.

## Select A Verifier

List verifier ids:

```bash
provedown list-verifiers
```

The built-in verifiers are currently:

```text
python-results
sql-results
```

Run only that verifier explicitly:

```bash
provedown verify --verifier python-results report.md
```

Run only the SQL verifier explicitly:

```bash
provedown verify --verifier sql-results report.md
```

The option may be passed more than once when additional verifier plugins exist.

## Verify Python In A Fresh Environment

Use the uv sandbox prototype when you want Python verification to run without
inheriting packages from the caller's environment:

```bash
provedown verify --sandbox uv report.md
```

The sandbox reads Python requirements from document frontmatter. See
[Verify Python With uv](verify-python-with-uv.md) for setup and boundaries.

## Interpret Statuses

`pass` means the authored claim matched the recomputed value.

`fail` means the verifier ran successfully and found a mismatch.

`skip` means a check was intentionally not run. It can describe an intentionally
unchecked claim, such as `data-compare="none"`, or a document-level verification
skip after parser errors block all verifier execution.

`error` means verification could not complete for that item. Examples include a
parser diagnostic, a Python exception, an unknown result code reference, or an
unknown comparison policy.
