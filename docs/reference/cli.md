# CLI Reference

The command-line entry point is `provedown`.

From this repository, run commands through `uv`:

```bash
uv run provedown ...
```

## `provedown verify`

Verify one or more documents.

```bash
provedown verify [--verifier VERIFIER_ID] [--format text|json] PATH [PATH ...]
```

Arguments:

`PATH`
: Markdown document to parse and verify. Multiple paths are allowed.

Options:

`--verifier VERIFIER_ID`
: Run only the named verifier. May be passed more than once.

`--format text`
: Print human-readable output. This is the default.

`--format json`
: Print structured JSON output.

Exit codes:

`0`
: Every report is ok. Reports with only `pass` and `skip` findings are ok.

`1`
: At least one report has a `fail` or `error` finding.

`2`
: Argument parsing failed.

## `provedown list-verifiers`

List verifier ids registered in the default registry.

```bash
provedown list-verifiers
```

Current output:

```text
python-results
```

## Text Output

Text output has one file summary followed by finding lines:

```text
report.md: ok
  pass=1, fail=0, skip=0, error=0
  [pass] python-results report.md:5:16: value matches exactly expected='42' actual='42'
```

## JSON Output Shape

JSON output has an overall `ok` field and one report object per path:

```json
{
  "ok": true,
  "reports": [
    {
      "path": "report.md",
      "ok": true,
      "summary": {
        "pass": 1,
        "fail": 0,
        "skip": 0,
        "error": 0
      },
      "findings": []
    }
  ]
}
```

Findings include `verifier_id`, `status`, `location`, `message`, `expected`,
`actual`, and `evidence`.
