# Provedown

Provedown is a markdown-native framework for verifiable literate documents.
Markdown is the primary authoring surface, but pure HTML documents can use the
same contract. The source document stays human-readable, while embedded
assertions can be checked by independent verifier plugins.

The first built-in verifier executes Python cells and checks scalar prose
results:

```html
<code>
x = 410 + 2
</code>

The cohort has <span class="result" data-code="x">412<span class="method"></span></span> samples.
```

Run verification with:

```bash
provedown verify report.md
```

Use `provedown verify report.html` for the same contract in an HTML file.

## Documentation

The documentation is organized with the Diataxis structure under `docs/`.

For repository development, build it with:

```bash
just docs-build
```

Preview it locally with:

```bash
just docs-serve
```

The public model is intentionally verifier-neutral. Python execution is one
plugin; future plugins can validate references with LinkML tooling or prove
properties about code with systems such as clauz3.

## Extension model

Verifier plugins receive a parsed `Document` IR and return a `Report` made of
portable findings:

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

The IR keeps code language, unknown attributes, source locations, authored
values, and named code references intact. That leaves room for non-Python
executors, LinkML-backed reference validation, and static proof tools without
changing the core parser or report format.
