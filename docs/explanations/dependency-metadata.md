# Dependency Metadata

Provedown documents declare runtime requirements in YAML frontmatter. The
metadata is document-scoped, verifier-neutral at the core, and inert until a
user explicitly selects an execution mode that consumes it.

## Decision

Use a mapping under `provedown.environments`, keyed by a language or verifier
family:

```yaml
---
provedown:
  environments:
    python:
      requires-python: ">=3.11"
      dependencies:
        - pandas>=2
        - pyarrow>=15
    sql:
      extensions:
        - spatial
---
```

Provedown core checks that `environments` and each named environment are
mappings, and that environment names and metadata keys are strings. It
otherwise preserves their content for verifier plugins. This lets the Python
verifier use Python packaging metadata without imposing Python package
semantics on SQL or future verifier families.

## Python Semantics

The `python` environment borrows the two runtime fields standardized by PEP
723:

`dependencies`
: A list of PEP 508 dependency strings.

`requires-python`
: A Python version specifier.

The field names and values match PEP 723, but the surrounding syntax is YAML
rather than a literal `# /// script` comment block. PEP 723 defines metadata
inside a standalone Python script. A Provedown source is a Markdown document
that may contain several languages, so copying the Python comment container
would make the document contract Python-specific.

## Project Environments

The existing `provedown.pyproject` field remains available when a document
belongs to a Python project:

```yaml
---
provedown:
  pyproject: ../pyproject.toml
  environments:
    python:
      dependencies:
        - matplotlib>=3.9
---
```

An execution adapter may use the project as the base environment and layer the
inline dependencies on top. Paths resolve from the document directory.

## Scope And Ownership

Environment metadata applies to the whole document. Code-block-specific
environments would make linear execution depend on mid-document environment
switches and are deliberately out of scope.

Parsing metadata never creates an environment or installs a package. The core
parser owns only the portable mapping. A verifier adapter owns validation,
environment construction, and execution. Installing declared dependencies is
therefore an explicit execution action, with the same trust implications as
running the document code itself.

Lock data and offline dependency policies can be added later without changing
the document-level ownership boundary.
