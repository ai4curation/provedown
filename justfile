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

docs-build: docs-render-examples
    uv run mkdocs build --strict

docs-render-examples:
    uv run python scripts/render_example_tabs.py

docs-serve port="8000": docs-render-examples
    uv run mkdocs serve -a 127.0.0.1:{{port}}

examples := "examples/homepage-orders.md examples/basic-report.md examples/data-file-report.md examples/sql-sales-summary.md examples/html-report.html"
okf_examples := "examples/okf/index.md examples/okf/log.md examples/okf/tables/orders.md examples/okf/metrics/revenue.md examples/okf/metrics/revenue-legacy.md examples/okf/policies/revenue-recognition.md examples/okf/skills/run-on-duckdb.md"
okf_computations := "examples/okf/computations/revenue-ytd.md"

verify-examples:
    uv run provedown verify {{examples}} {{okf_examples}}
    uv run provedown verify --okf {{okf_computations}}

inspect-examples:
    uv run provedown inspect {{examples}} {{okf_examples}}
    uv run provedown inspect --okf {{okf_computations}}

lint-examples:
    uv run provedown lint {{examples}} {{okf_examples}}
    uv run provedown lint --okf {{okf_computations}}

check-examples: lint-examples inspect-examples verify-examples

all: check check-examples docs-build
