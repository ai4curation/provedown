set dotenv-load := true

default:
    just --list

test:
    uv run pytest

typecheck:
    uv run mypy

lint:
    uv run ruff check

check: lint typecheck test

docs-build:
    uv run mkdocs build --strict

docs-serve port="8000":
    uv run mkdocs serve -a 127.0.0.1:{{port}}

examples := "docs/examples/basic-report.md docs/examples/data-file-report.md"

verify-examples:
    uv run provedown verify {{examples}}

inspect-examples:
    uv run provedown inspect {{examples}}

lint-examples:
    uv run provedown lint {{examples}}

check-examples: lint-examples inspect-examples verify-examples

all: check check-examples docs-build
