# Verify Python With uv

Use the uv sandbox prototype to verify Python claims in a fresh dependency
environment instead of the environment that launched Provedown.

## Declare Python Requirements

Add a `python` environment to the document frontmatter:

```yaml
---
provedown:
  environments:
    python:
      requires-python: ">=3.11"
      dependencies:
        - pandas>=2
        - pyarrow>=15
---
```

Dependency entries use PEP 508 requirement syntax. `requires-python` uses a
Python version specifier.

If the document belongs to an existing project, point at its `pyproject.toml`:

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

The project supplies the base environment and inline dependencies are layered
on top. The path resolves from the document directory.

## Run Sandboxed Verification

Run:

```bash
provedown verify --sandbox uv report.md
```

Sandbox mode currently supports only the built-in `python-results` verifier.
Requesting another verifier, or verifying a document that contains SQL claims,
produces an error. Provedown never silently runs a verifier outside the
requested environment.

The worker preserves normal Provedown execution order and the document-relative
working directory. Result comparison and report formatting remain in the
parent Provedown process. The complete uv setup and worker invocation has a
five-minute timeout so dependency resolution or document code cannot hang the
verifier indefinitely.

## Understand The Boundary

This mode provides a fresh Python environment and dependency isolation. It is
not a security sandbox:

- document code can read and write files available to the current user;
- document code inherits environment variables and credentials;
- dependency resolution and document code may access the network;
- native packages and subprocesses retain normal operating-system access.

Review an untrusted document and its dependency declarations before running it.
Use a container or operating-system sandbox when hostile-code isolation is
required.

If uv cannot create the environment, Provedown reports an environment setup
error separately from code exceptions and authored-value mismatches.
