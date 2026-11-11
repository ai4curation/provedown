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

`quotes`
: Ordered `QuoteClaim` objects for the document's
  [quotations](markup.md#quotations). They are not executable, so they are not
  in `events`.

Each `QuoteClaim` has:

`text`
: The quoted text, with entities decoded and whitespace collapsed.

`location`
: Location of the `<q>` or `<blockquote>` start tag.

`element`
: `"q"` or `"blockquote"`.

`citation`
: The citation's own text, without its quotes, or `None` when the quote is not
  inside a citation.

`citation_location`
: Location of the `<cite>` start tag, or `None`.

`sources`
: Reference ids named in the citation text, in order.

`source`
: The single reference id when `sources` has exactly one, else `None`. A quote
  verifier checks `text` against this source.

`unclosed`
: True when the quote, or the citation or figure around it, has no end tag.
  Its `text` may then run to the end of the document.

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

`verify_document()` and `verify_file()` fail closed when the parsed document has
an error diagnostic: their report contains every parser error plus a `skip`
finding, and they do not construct the default registry or invoke a verifier.
`VerifierRegistry.verify()` is a lower-level dispatch API that does not inspect
`Document.diagnostics` before invoking registered verifiers.

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
