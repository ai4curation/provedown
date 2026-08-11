"""Render tabbed documentation pages for Provedown examples."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE_SOURCE = ROOT / "examples/homepage-orders.md"
HOMEPAGE_TARGET = ROOT / "docs/index.md"
HOMEPAGE_START = "<!-- pd-homepage-example:start -->"
HOMEPAGE_END = "<!-- pd-homepage-example:end -->"


@dataclass(frozen=True)
class ExamplePage:
    title: str
    source: Path
    target: Path
    description: str
    pandoc_from: str = "markdown-smart"
    raw_language: str = "markdown"


EXAMPLES = [
    ExamplePage(
        title="Basic Verified Report",
        source=ROOT / "examples/basic-report.md",
        target=ROOT / "docs/examples/basic-report.md",
        description=(
            "A compact Provedown document with inline Python, scalar result "
            "assertions, set comparison, tolerance comparison, and a named "
            "expression."
        ),
    ),
    ExamplePage(
        title="CSV Sales Summary",
        source=ROOT / "examples/data-file-report.md",
        target=ROOT / "docs/examples/data-file-report.md",
        description=(
            "A more realistic Provedown document that imports Python "
            "standard-library modules, reads a local CSV file, and verifies "
            "summary claims in prose."
        ),
    ),
    ExamplePage(
        title="SQL CSV Sales Summary",
        source=ROOT / "examples/sql-sales-summary.md",
        target=ROOT / "docs/examples/sql-sales-summary.md",
        description=(
            "A Provedown document that uses DuckDB SQL to query a local CSV "
            "file and verify summary claims in prose."
        ),
    ),
    ExamplePage(
        title="Pure HTML Report",
        source=ROOT / "examples/html-report.html",
        target=ROOT / "docs/examples/html-report.md",
        description=(
            "A Provedown document written as plain HTML, useful when a "
            "pipeline already emits HTML or when Markdown is not part of the "
            "authoring workflow."
        ),
        pandoc_from="html",
        raw_language="html",
    ),
]


def main() -> int:
    if shutil.which("pandoc") is None:
        raise SystemExit("pandoc is required to render tabbed example pages")

    for example in EXAMPLES:
        source = example.source.read_text(encoding="utf-8")
        rendered = _pandoc_html(example)
        example.target.write_text(
            _render_page(example, source=source, rendered=rendered),
            encoding="utf-8",
        )
    _render_homepage_example()
    return 0


def _pandoc_html(example: ExamplePage) -> str:
    completed = subprocess.run(
        [
            "pandoc",
            "--from",
            example.pandoc_from,
            "--to",
            "html",
            "--wrap=none",
            str(example.source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _render_page(example: ExamplePage, *, source: str, rendered: str) -> str:
    return (
        f"# {example.title}\n\n"
        f"{example.description}\n\n"
        "The tabs show the same Provedown document in two forms. The raw view "
        "shows the literal Provedown contract; the rendered HTML is generated "
        "from that source with `pandoc`.\n\n"
        f'=== "Raw {example.source.suffix}"\n\n'
        f"    ````{example.raw_language}\n"
        f"{_indent(source.rstrip())}\n"
        "    ````\n\n"
        '=== "Rendered HTML"\n\n'
        "    <div class=\"pd-rendered-provedown\" data-provedown-ignore=\"true\">\n"
        f"{_indent(rendered)}\n"
        "    </div>\n\n"
        "Verify this example with:\n\n"
        "```bash\n"
        f"provedown verify {example.source.relative_to(ROOT)}\n"
        "```\n"
    )


def _render_homepage_example() -> None:
    source = HOMEPAGE_SOURCE.read_text(encoding="utf-8")
    rendered = _pandoc_html(
        ExamplePage(
            title="Homepage Orders",
            source=HOMEPAGE_SOURCE,
            target=HOMEPAGE_TARGET,
            description="",
        )
    )
    page = HOMEPAGE_TARGET.read_text(encoding="utf-8")
    replacement = _render_homepage_block(source=source, rendered=rendered)
    HOMEPAGE_TARGET.write_text(
        _replace_between(
            page,
            start=HOMEPAGE_START,
            end=HOMEPAGE_END,
            replacement=replacement,
        ),
        encoding="utf-8",
    )


def _render_homepage_block(*, source: str, rendered: str) -> str:
    return (
        f"{HOMEPAGE_START}\n"
        "<!-- Generated from examples/homepage-orders.md by "
        "scripts/render_example_tabs.py. -->\n"
        '<div class="pd-proof-pair" data-provedown-ignore="true" markdown>\n\n'
        '<div class="pd-proof-panel pd-proof-reader">\n\n'
        '<p class="pd-proof-label">Styled reader view</p>\n\n'
        f"{rendered}\n\n"
        "</div>\n\n"
        '<div class="pd-proof-panel pd-proof-source" markdown>\n\n'
        '<p class="pd-proof-label">Provedown source</p>\n\n'
        "````markdown\n"
        f"{source.rstrip()}\n"
        "````\n\n"
        "</div>\n\n"
        "</div>\n"
        f"{HOMEPAGE_END}"
    )


def _replace_between(
    text: str,
    *,
    start: str,
    end: str,
    replacement: str,
) -> str:
    before, marker, rest = text.partition(start)
    if not marker:
        raise ValueError(f"missing start marker: {start}")
    _, marker, after = rest.partition(end)
    if not marker:
        raise ValueError(f"missing end marker: {end}")
    return f"{before}{replacement}{after}"


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" if line else "" for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
