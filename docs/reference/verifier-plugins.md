# Verifier Plugins

Verifier plugins let Provedown check more than Python scalar results. A verifier
receives a parsed `Document` and returns `Finding` objects.

## Protocol

A verifier has a stable id and a `verify()` method:

```python
from collections.abc import Iterable

from provedown import Document, Finding, VerificationContext


class MyVerifier:
    verifier_id = "my-verifier"

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        ...
```

## Findings

Each finding has:

`verifier_id`
: The verifier that produced the finding.

`status`
: One of `pass`, `fail`, `skip`, or `error`.

`location`
: Source location for the relevant document item.

`message`
: Human-readable explanation.

`expected`
: Optional authored value or expectation.

`actual`
: Optional computed value.

`evidence`
: Optional structured metadata.

## Status Semantics

Use `pass` when the verifier checked the item and it matched.

Use `fail` when the verifier checked the item and found a mismatch.

Use `skip` when the verifier intentionally did not check the item.

Use `error` when the verifier could not complete the check.

Only `fail` and `error` make a report not ok.

## Context

`VerificationContext` currently provides:

`cwd`
: Optional working directory for verifier execution.

`comparators`
: Comparator registry used by scalar result verifiers.

Verifiers may ignore context fields that do not apply.

## Registration

Create a registry and register verifier instances:

```python
from provedown import VerifierRegistry

registry = VerifierRegistry()
registry.register(MyVerifier())
```

Then pass the registry to `verify_document()`.

The default registry currently includes:

- `python-results` for `python` and `py` code;
- `sql-results` for `sql`, `duckdb`, and `duckdb-sql` code.
