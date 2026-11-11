# CLI Reference

The command-line entry point is `provedown`.

## `provedown verify`

Verify one or more documents.

```bash
provedown verify [--verifier VERIFIER_ID] [--no-plugins] [--format text|json]
  [--sandbox uv] [--okf] PATH [PATH ...]
```

Parser diagnostics become `error` findings. If a document has any parser error,
the command adds a `skip` finding, does not invoke verifiers for that document,
and exits with status `1`. Installed [verifier
plugins](verifier-plugins.md#publishing-a-plugin) are loaded once per run,
before any document is verified; a plugin that cannot be loaded stops the run
with status `2`.

Arguments:

`PATH`
: Markdown or HTML document to parse and verify. Multiple paths are allowed.

Options:

`--verifier VERIFIER_ID`
: Run only the named verifier. May be passed more than once. An id that is not
  registered stops the run with status `2` and lists the available ids.

`--no-plugins`
: Use only the built-in verifiers, without loading installed verifier plugins.

`--format text`
: Print human-readable output. This is the default.

`--format json`
: Print structured JSON output.

`--sandbox uv`
: Run the built-in Python verifier in a fresh uv environment. This prototype
  supports only sandboxed `python-results`; documents containing SQL claims
  return an unsupported-sandbox error. The mode uses document environment
  metadata and does not provide network or filesystem security isolation.

`--okf`
: Treat each document as [Open Knowledge Format](../how-to-guides/verify-an-okf-bundle.md)
  and lift an `Attested Computation`'s fenced computation into an executable
  named code block. Without this flag the fenced computation stays a literal
  example, as fenced code does everywhere else.

Exit codes:

`0`
: Every report is ok. Reports with only `pass` and `skip` findings are ok.

`1`
: At least one report has a `fail` or `error` finding.

`2`
: Argument parsing failed, a `--verifier` id is not registered, `--sandbox` was
  combined with an unsupported verifier, or an installed verifier plugin could
  not be loaded.

## `provedown list-verifiers`

List verifier ids registered in the default registry, including installed
verifier plugins. Pass `--no-plugins` to list only the built-in verifiers.
It exits with status `2` if an installed verifier plugin cannot be loaded.

```bash
provedown list-verifiers [--no-plugins]
```

Current output:

```text
python-results
sql-results
```

## `provedown inspect`

Inspect code and result relationships without executing document code.

```bash
provedown inspect [--format text|json] [--okf] PATH [PATH ...]
```

Arguments:

`PATH`
: Markdown or HTML document to parse and inspect. Multiple paths are allowed.

Options:

`--format text`
: Print human-readable inspection output. This is the default.

`--format json`
: Print structured JSON output.

`--okf`
: Lift an OKF `Attested Computation` before inspecting, so claims that
  reference the lifted block resolve. Useful for seeing what `--okf` verify
  would execute.

Exit codes:

`0`
: No inspection errors were found. Warnings are allowed.

`1`
: At least one inspection error was found, such as an unresolved code use or
  result reference.

`2`
: Argument parsing failed.

## `provedown lint`

Lint Provedown documents without executing document code.

```bash
provedown lint [--format text|json] [--okf] PATH [PATH ...]
```

Arguments:

`PATH`
: Markdown or HTML document to parse and lint. Multiple paths are allowed.

Options:

`--format text`
: Print human-readable lint output. This is the default.

`--format json`
: Print structured JSON output.

`--okf`
: Lift an OKF `Attested Computation` before linting, so claims that reference
  the lifted block are not reported as unresolved.

Exit codes:

`0`
: No lint errors were found. Warnings are allowed.

`1`
: At least one lint error was found.

`2`
: Argument parsing failed.

## Verify Text Output

Text output has one file summary followed by finding lines:

```text
report.md: ok
  pass=1, fail=0, skip=0, error=0
  [pass] python-results report.md:5:16: value matches exactly expected='42' actual='42'
```

## Verify JSON Output Shape

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

## Python Execution Directory

When `provedown verify` reads a document from disk, the built-in Python verifier
executes code with that document's parent directory as the working directory.
Relative paths therefore resolve next to the document being verified.

For example, code in `reports/summary.md` can read `reports/data/input.csv` as
`Path("data/input.csv")`.
