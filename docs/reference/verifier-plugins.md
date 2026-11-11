# Verifier Plugins

Verifier plugins let Provedown check more than Python scalar results. A verifier
receives a parsed `Document` and returns `Finding` objects.

## Protocol

A verifier has a stable id and a `verify()` method:

```python
from collections.abc import Iterable

from provedown import Document, Finding, Status, VerificationContext


class MyVerifier:
    verifier_id = "my-verifier"

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        for event in document.events:
            yield Finding(
                verifier_id=self.verifier_id,
                status=Status.PASS,
                location=event.location,
                message=f"checked {type(event).__name__}",
            )
```

## Findings

Each finding has:

`verifier_id`
: The verifier that produced the finding, as a `str`. Provedown does not check it against
  the verifier that yielded the finding, so a composite verifier may report
  under sub-ids; treat it as the plugin's claim, not as proof of which code
  ran.

`status`
: A `Status`: `Status.PASS`, `Status.FAIL`, `Status.SKIP` or `Status.ERROR`.
  The plain strings `"pass"`, `"fail"`, `"skip"` and `"error"` are accepted and
  converted; any other value raises `ValueError`.

`location`
: A `SourceLocation` for the relevant document item, such as an event's or
  quote's `location`. Anything else raises `TypeError`.

`message`
: Human-readable explanation, as a `str`.

`expected`
: Optional authored value or expectation, as a `str` or `None`.

`actual`
: Optional computed value, as a `str` or `None`. Convert numbers and other
  values with `str()`, as the built-in verifiers do.

`evidence`
: Optional structured metadata: a mapping that strict JSON can represent,
  because it appears in `--format json` output. Convert values such as `Path`
  to strings, and avoid `NaN` and infinite floats. Omit it when there is none:
  `None`, like any other value that is not such a mapping, raises `TypeError`.
  The finding keeps its own copy.

## Status Semantics

Use `pass` when the verifier checked the item and it matched.

Use `fail` when the verifier checked the item and found a mismatch.

Use `skip` when the verifier intentionally did not check the item.

Use `error` when the verifier could not complete the check.

Return an `error` finding rather than raising, and yield only `Finding`
objects. If a verifier raises anyway, including from building a `Finding`
with a bad `status` or `location`, the registry reports it as an `error`
finding attributed to that verifier's id. Its `evidence["traceback"]` holds
the traceback, chained causes included, with each frame and message cut to a
bounded length. If the verifier yields something that is not a `Finding`, the
error finding names it, shortened, under `evidence["yielded"]`, and the rest
of that verifier's output is ignored. Findings the verifier yielded before
the problem, and the other verifiers' findings, are kept.

Only `fail` and `error` make a report not ok.

## Context

`VerificationContext` currently provides:

`cwd`
: Optional working directory for verifier execution.

`comparators`
: Comparator registry used by scalar result verifiers.

`sandbox`
: Optional execution adapter requested by the caller. A verifier must either
  implement the named mode or return an error; it must not silently run code
  outside the requested sandbox.

Verifiers may ignore context fields that do not apply.

## Registration

Create a registry and register verifier instances:

```python
from provedown import VerifierRegistry

registry = VerifierRegistry()
registry.register(MyVerifier())
```

Then pass the registry to `verify_document()`. Requesting a verifier id that
is not registered, through `verify_document()`, `registry.verify()` or
`registry.get()`, raises `UnknownVerifierError`, a `KeyError` subclass whose
message lists the registered ids. An empty list of ids raises `ValueError`,
so that running nothing never looks like a passing report; pass `None` to run
every verifier. A repeated id runs its verifier once. Call
`registry.check_ids(ids)` to validate ids up front. `registry.register()`
raises `TypeError` for an object without a string `verifier_id` and a
`verify()` method.

Do not call `registry.verify()` directly for parsed or untrusted document input.
That low-level dispatch method does not inspect `Document.diagnostics` before
invoking plugins; `verify_document()` enforces the fail-closed parser-diagnostic
gate.

The default registry currently includes:

- `python-results` for `python` and `py` code;
- `sql-results` for `sql`, `duckdb`, and `duckdb-sql` code;
- every verifier that an installed package publishes as a plugin (see below).

## Publishing A Plugin

A package publishes verifiers under the `provedown.verifiers` entry-point
group. Each entry point names a verifier class, or any callable that takes no
arguments and returns a verifier:

```toml
# pyproject.toml of the plugin package
[project.entry-points."provedown.verifiers"]
quotes = "my_package.provedown_plugin:QuoteVerifier"
```

Once that package is installed alongside Provedown, `default_registry()` loads
the verifier, `provedown list-verifiers` lists it, and `provedown verify` runs
it with the built-in verifiers or alone with `--verifier <id>`.

The id that `--verifier` and `list-verifiers` use is the verifier's
`verifier_id`, not the entry point name. In the example above the entry point
is called `quotes`, but `--verifier` takes whatever `QuoteVerifier.verifier_id`
is. The entry point name only sets the load order and appears in error
messages.

Entry points load in name order. A plugin may not reuse the `verifier_id` of a
built-in verifier or of a plugin loaded before it. A plugin that cannot be
imported or constructed, that does not return an object with a string
`verifier_id` and a `verify()` method, or that reuses an id, raises
`PluginLoadError` naming the entry point and the package that provides it.
`default_registry()`, and `verify_document()` and `verify_file()` when called
without a registry, raise it to library callers. The CLI prints the message
and exits with status 2. Run `provedown verify --no-plugins` or
`provedown list-verifiers --no-plugins` to use only the built-in verifiers
while a broken plugin is installed. In Python, call
`default_registry(plugins=False)`, and use `load_plugin_verifiers()` to see
what is installed.

A plugin runs in the Provedown process, so install only plugins you trust. The
sandbox rule in [Context](#context) applies to plugins as it does to the
built-in verifiers. The only exemption is narrow: a verifier that executes
nothing (no document code, no subprocesses, no network access) has nothing to
sandbox and may leave `context.sandbox` unread. A verifier that fetches
sources over the network or runs any process must honour the requested
sandbox or return an `error` finding.
