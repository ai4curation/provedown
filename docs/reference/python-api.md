# Python API Reference

The public API is exported from `provedown`.

## Parse Documents

Parse Markdown or HTML text:

```python
from provedown import parse_document

document = parse_document("""
<code>x = 40 + 2</code>
The answer is <span class="result" data-code="x">42</span>.
""")
```

Parse a file:

```python
from pathlib import Path
from provedown import parse_file

document = parse_file(Path("report.md"))
```

The parsed `Document` contains:

`source`
: Original source text.

`path`
: Optional source path.

`events`
: Ordered `CodeBlock`, `CodeUse`, and `ResultAssertion` events.

`named_code`
: Mapping of code block names to `CodeBlock` objects.

`frontmatter`
: Parsed YAML frontmatter from Markdown documents. User-defined fields are
  preserved but not validated by Provedown.

`provedown`
: Normalized Provedown-specific frontmatter settings, including `aliases`,
  `environments`, `last_validated`, `default_language`, and `pyproject`.

`diagnostics`
: Parser diagnostics.

## Verify Documents

Verify parsed text:

```python
from provedown import parse_document, verify_document

document = parse_document("""
<code>x = 40 + 2</code>
The answer is <span class="result" data-code="x">42</span>.
""")

report = verify_document(document)
assert report.ok
```

Verify a file:

```python
from pathlib import Path
from provedown import verify_file

report = verify_file(Path("report.md"))
```

`verify_file()` runs with the document directory as the working directory.
Pass `sandbox="uv"` and select `python-results` to use the uv sandbox adapter.

## Inspect Reports

```python
from provedown import Status

summary = report.summary()
failures = report.count(Status.FAIL)
payload = report.to_dict()
```

A report is ok when it contains no `fail` or `error` findings.

## Register A Custom Verifier

```python
from collections.abc import Iterable

from provedown import (
    Document,
    Finding,
    SourceLocation,
    Status,
    VerificationContext,
    VerifierRegistry,
    verify_document,
)


class AlwaysPassVerifier:
    verifier_id = "always-pass"

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        del context
        yield Finding(
            verifier_id=self.verifier_id,
            status=Status.PASS,
            location=SourceLocation(path=document.path, line=1, column=1),
            message="custom verifier ran",
        )


registry = VerifierRegistry()
registry.register(AlwaysPassVerifier())

report = verify_document(
    Document(source="", path=None, events=[], named_code={}),
    registry=registry,
)
```

Verifier plugins receive the parsed document IR and return portable findings.
