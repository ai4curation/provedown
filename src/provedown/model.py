"""Document IR shared by parsers, renderers, and verifier plugins."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any


@dataclass(frozen=True)
class SourceLocation:
    """Best-effort location of a parsed element in the source document."""

    path: Path | None
    line: int
    column: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _as_path(self.path))

    def display(self) -> str:
        prefix = str(self.path) if self.path is not None else "<string>"
        return f"{prefix}:{self.line}:{self.column}"


@dataclass(frozen=True)
class CodeBlock:
    """A code definition or execution cell parsed from a ``<code>`` element."""

    code: str
    location: SourceLocation
    name: str | None = None
    language: str = "python"
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CodeUse:
    """Execution site for a named ``CodeBlock``."""

    name: str
    location: SourceLocation
    language: str = "python"
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultAssertion:
    """An authored scalar result and the expression that should reproduce it."""

    authored: str
    code: str
    location: SourceLocation
    compare: str = "exact"
    language: str = "python"
    attributes: Mapping[str, str] = field(default_factory=dict)

    @property
    def referenced_code_name(self) -> str | None:
        if self.code.startswith("#") and len(self.code) > 1:
            return self.code[1:]
        return None


DocumentEvent = CodeBlock | CodeUse | ResultAssertion


@dataclass(frozen=True)
class ProvedownConfig:
    """Optional configuration parsed from a document's ``provedown`` frontmatter."""

    aliases: Mapping[str, str] = field(default_factory=dict)
    environments: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    last_validated: str | None = None
    default_language: str = "python"
    pyproject: str | None = None


@dataclass(frozen=True)
class Document:
    """Parsed Provedown document.

    The IR is intentionally language-neutral. Verifiers choose which events and
    languages they understand.
    """

    source: str
    path: Path | None
    events: list[DocumentEvent]
    named_code: Mapping[str, CodeBlock]
    frontmatter: Mapping[str, Any] = field(default_factory=dict)
    provedown: ProvedownConfig = field(default_factory=ProvedownConfig)
    diagnostics: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _as_path(self.path))

    def start_location(self) -> SourceLocation:
        """The document's first line, for findings about the whole document.

        Its path is ``None`` unless the document's path is a real path, so the
        findings that report errors can always be built.
        """

        path = self.path if isinstance(self.path, PurePath) else None
        return SourceLocation(path=path, line=1, column=1)

    def referenced_code_names(self) -> list[str]:
        names: list[str] = []
        for event in self.events:
            if isinstance(event, CodeUse):
                names.append(event.name)
            elif isinstance(event, ResultAssertion):
                name = event.referenced_code_name
                if name is not None:
                    names.append(name)
        return names

    def code_definitions(self) -> dict[str, CodeBlock]:
        return dict(self.named_code)


def _as_path(value: Any) -> Any:
    """Convert a ``str`` or other path-like from an untyped caller to a ``Path``.

    Anything else is returned unchanged, for the caller's own checks to reject.
    """

    if isinstance(value, str | os.PathLike) and not isinstance(value, PurePath):
        return Path(value)
    return value
