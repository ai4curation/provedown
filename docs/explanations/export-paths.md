# Export Paths

Provedown should add richer presentation without changing its trust model: the
Markdown or HTML document is the source, authored values remain falsifiable,
and every exported artifact is derived.

## Recommendation

Build a verified static HTML export first. Defer browser execution and hosted
apps until the static artifact contract is stable.

| Target | Executes document code | Infrastructure | Best use | Priority |
| --- | --- | --- | --- | --- |
| Verified static HTML | During export only | None for readers | Reports, review, archives | First |
| Browser/WASM HTML | In each reader's browser | Static hosting | Interactive demonstrations | Later |
| Hosted app | On a server | Runtime, isolation, operations | Native dependencies, large data, secrets | Last |

This order follows Provedown's document-first purpose. Static HTML improves the
reader experience without introducing a second execution environment or making
interactivity part of the source contract.

## Static HTML Contract

The first exporter should have a command shaped like:

```bash
provedown export html report.md -o report.html
```

Export should parse and verify the input before rendering. By default, a
`fail` or `error` finding should prevent creation of an artifact that appears
verified. An explicit `--allow-unverified` option may produce an artifact, but
the failed or incomplete status must be prominent in the output.

The generated HTML should contain:

- the readable rendered document;
- disclosure controls for supporting code and comparison policies;
- per-claim status and the overall verification summary;
- the Provedown version and verifier ids;
- a SHA-256 fingerprint of the exact source bytes that were verified;
- the structured verification report in an embedded JSON data block;
- an optional copy of, or link to, the canonical source.

The source fingerprint is essential. A verification report without a binding
to exact source bytes can be accidentally paired with a newer document and
display stale trust signals.

The static artifact should execute no document code and require no backend.
Method disclosure can use native HTML such as `details` and `summary`, with
small embedded CSS. JavaScript is optional presentation enhancement, not part
of verification.

[Pandoc can produce standalone HTML](https://pandoc.org/MANUAL.html#option--standalone)
and already renders the repository's documentation examples. It is a practical
first renderer, but the artifact contract should not expose Pandoc-specific
structures. That leaves room for another renderer later.

## Keep Generated Output Derived

Export must never rewrite authored result values or become the only retained
artifact. In particular:

- rerunning verification updates status, not prose values;
- interactive controls reveal evidence but do not replace the claim;
- an exported file does not become verification input when the source is
  available;
- CI should rebuild exports from source rather than accept hand-edited HTML.

A generated claim identifier may be added to the HTML for UI wiring. It should
be derived from the parsed event index and source location, not added to the
authored document merely to serve the exporter.

## Browser Execution Architecture

WASM export should build on the same parsed document IR and portable finding
schema as static export. The exporter can serialize the event stream and assets
once, then verifier-specific browser adapters can execute supported events in a
Web Worker.

Each adapter must declare:

- the verifier id and supported language names;
- runtime and package compatibility checks;
- supported data and network access modes;
- resource limits and cancellation behavior;
- the version information included in findings.

An unsupported verifier is an export error or a conspicuous unverified status.
It must never be silently omitted.

### Python

The Python adapter would use Pyodide. Pure-Python wheels can generally be
installed in Pyodide, while compiled packages require a Pyodide build or a
compatible wheel. The current
[Pyodide package list](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)
is broad, but it is not equivalent to a native Python environment.

The adapter should evaluate the document's Python environment metadata before
export and reject incompatible dependencies. It should also make browser
limits visible: no native subprocess model, different filesystem and network
behavior, finite browser memory, and no assumption that local credentials or
files exist.

[marimo's WASM documentation](https://docs.marimo.io/guides/wasm/) is useful
prior art for package checks, bundled data, platform markers, and browser
limitations. Provedown should borrow those operational lessons without
adopting a notebook or reactive execution model.

### SQL

The SQL adapter should use DuckDB-Wasm directly rather than route SQL through
the Python runtime. DuckDB-Wasm can query browser-accessible CSV, JSON, Parquet,
Arrow, and database files, but its
[documented native/WASM differences](https://github.com/duckdb/duckdb-wasm)
include networking, extension loading, filesystem access, and threading.

The adapter therefore needs its own compatibility declaration and versioned
findings. Native DuckDB verification and browser DuckDB-Wasm verification are
related results, not automatically interchangeable ones.

### Other Verifiers

Verifier plugins should opt into browser export through an explicit adapter or
manifest entry. Core Provedown should not attempt to translate arbitrary
plugin code to WASM. Static export can still present findings produced before
export even when no browser adapter exists.

## Data And Security

Browser execution changes data handling. An exporter must require an explicit
asset manifest rather than copying every file reachable from the document.
Remote data needs stable URLs and suitable CORS policy. Sensitive local files
and credentials must not be bundled.

Running in WASM reduces direct host access but does not make arbitrary code
benign. Exported code can consume resources, issue allowed network requests,
and expose bundled data. Browser execution should use workers, timeouts,
cancel controls, size limits, and a clear warning before rerunning untrusted
documents.

## When A Hosted App Is Justified

A server-backed app is appropriate when verification requires native packages,
large or private data, controlled credentials, long-running computation, or
central policy enforcement. It also carries the largest operational and
security burden.

The server should consume the canonical source and emit the same portable
finding schema. It should not introduce a private app state that can disagree
with the checked-in document.

## Implementation Sequence

1. Add static HTML export with source fingerprinting, embedded findings, code
   disclosure, and failure gating.
2. Add golden tests proving that displayed claims and embedded findings map to
   the exact source.
3. Define the browser adapter manifest and serialized IR version.
4. Prototype one Python/Pyodide adapter on a dependency-free document.
5. Prototype one DuckDB-Wasm adapter on a bundled CSV document.
6. Add hosted execution only in response to concrete workflows that cannot use
   static or browser execution.

The first implementation PR should cover steps 1 and 2 only.

## Prior Art

- [marimo export formats](https://docs.marimo.io/guides/exporting/)
- [marimo WebAssembly notebooks](https://docs.marimo.io/guides/wasm/)
- [Pyodide package support](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)
- [DuckDB-Wasm](https://github.com/duckdb/duckdb-wasm)
- [Pandoc standalone HTML](https://pandoc.org/MANUAL.html#option--standalone)
