# Verify A Document

Use `provedown verify` to check one or more Provedown Markdown files.

## Verify One File

```bash
uv run provedown verify report.md
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
uv run provedown verify report.md appendix.md
```

Each path is parsed and verified independently.

## Use JSON Output

```bash
uv run provedown verify --format json report.md
```

JSON output is intended for CI, editor integrations, and scripts. It includes an
overall `ok` field, per-file summaries, and structured findings.

## Select A Verifier

List verifier ids:

```bash
uv run provedown list-verifiers
```

The built-in verifier is currently:

```text
python-results
```

Run only that verifier explicitly:

```bash
uv run provedown verify --verifier python-results report.md
```

The option may be passed more than once when additional verifier plugins exist.

## Interpret Statuses

`pass` means the authored claim matched the recomputed value.

`fail` means the verifier ran successfully and found a mismatch.

`skip` means the verifier deliberately did not check the claim. For example, the
Python verifier skips result spans marked with `data-compare="none"`.

`error` means verification could not complete for that item. Examples include a
Python exception, an unknown result code reference, or an unknown comparison
policy.
