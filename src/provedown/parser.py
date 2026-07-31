"""Parser for the Provedown HTML contract in Markdown or HTML documents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml

from provedown.model import (
    CodeBlock,
    CodeUse,
    Document,
    DocumentEvent,
    ProvedownConfig,
    ResultAssertion,
    SourceLocation,
)


class ParseError(ValueError):
    """Raised when source cannot be parsed into a coherent Provedown document."""


@dataclass
class _CodeBuilder:
    location: SourceLocation
    name: str | None
    language: str
    attributes: Mapping[str, str]
    parts: list[str] = field(default_factory=list)

    def build(self) -> CodeBlock:
        return CodeBlock(
            code="".join(self.parts).strip("\n"),
            location=self.location,
            name=self.name,
            language=self.language,
            attributes=self.attributes,
        )


@dataclass
class _ResultBuilder:
    location: SourceLocation
    code: str
    compare: str
    language: str
    attributes: Mapping[str, str]
    span_depth: int = 1
    method_depth: int = 0
    parts: list[str] = field(default_factory=list)

    def build(self) -> ResultAssertion:
        return ResultAssertion(
            authored="".join(self.parts).strip(),
            code=self.code,
            compare=self.compare,
            language=self.language,
            location=self.location,
            attributes=self.attributes,
        )


@dataclass(frozen=True)
class _Frontmatter:
    data: Mapping[str, Any] = field(default_factory=dict)
    provedown: ProvedownConfig = field(default_factory=ProvedownConfig)
    diagnostics: list[str] = field(default_factory=list)
    end_line: int = 0


class _ProvedownHTMLParser(HTMLParser):
    def __init__(
        self,
        source: str,
        path: Path | None,
        default_language: str,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.path = path
        self.default_language = default_language
        self.events: list[DocumentEvent] = []
        self.named_code: dict[str, CodeBlock] = {}
        self.diagnostics: list[str] = []
        self._code: _CodeBuilder | None = None
        self._results: list[_ResultBuilder] = []
        self._ignore_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: Sequence[tuple[str, str | None]],
    ) -> None:
        attr_map = _attrs_to_dict(attrs)
        location = self._location()

        if self._ignore_depth > 0:
            self._ignore_depth += 1
            return

        if _is_ignored_region(attr_map):
            self._ignore_depth = 1
            return

        if self._code is not None:
            self.diagnostics.append(
                f"{location.display()}: nested HTML tag inside <code> was ignored"
            )
            return

        if tag == "code":
            self._start_code(attr_map, location)
            return

        if tag == "span" and self._results:
            self._results[-1].span_depth += 1
            if _has_class(attr_map, "method"):
                self._results[-1].method_depth += 1

        if tag == "span" and _has_class(attr_map, "result"):
            self._start_result(attr_map, location)

    def handle_startendtag(
        self,
        tag: str,
        attrs: Sequence[tuple[str, str | None]],
    ) -> None:
        attr_map = _attrs_to_dict(attrs)
        location = self._location()

        if self._ignore_depth > 0 or _is_ignored_region(attr_map):
            return

        if tag == "code":
            if "use" in attr_map:
                self._append_code_use(attr_map, location)
            else:
                self._append_code_block(
                    CodeBlock(
                        code="",
                        location=location,
                        name=_empty_to_none(attr_map.get("name")),
                        language=_language(attr_map, self.default_language),
                        attributes=attr_map,
                    )
                )
            return

        if tag == "span" and _has_class(attr_map, "result"):
            self._start_result(attr_map, location)
            self._finish_result()

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return

        if self._code is not None:
            self._code.parts.append(data)
            return

        if self._results and self._results[-1].method_depth == 0:
            self._results[-1].parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")

    def handle_endtag(self, tag: str) -> None:
        if self._ignore_depth > 0:
            self._ignore_depth -= 1
            return

        if tag == "code" and self._code is not None:
            code = self._code.build()
            self._code = None
            self._append_code_block(code)
            return

        if tag == "span" and self._results:
            current = self._results[-1]
            if current.method_depth > 0:
                current.method_depth -= 1
            current.span_depth -= 1
            if current.span_depth <= 0:
                self._finish_result()

    def close(self) -> None:
        super().close()
        if self._code is not None:
            self.diagnostics.append(
                f"{self._code.location.display()}: unclosed <code> block"
            )
            code = self._code.build()
            self._code = None
            self._append_code_block(code)
        while self._results:
            result = self._results[-1]
            self.diagnostics.append(
                f"{result.location.display()}: unclosed result span"
            )
            self._finish_result()

    def _start_code(
        self,
        attr_map: Mapping[str, str],
        location: SourceLocation,
    ) -> None:
        if "use" in attr_map:
            self._append_code_use(attr_map, location)
            return

        self._code = _CodeBuilder(
            location=location,
            name=_empty_to_none(attr_map.get("name")),
            language=_language(attr_map, self.default_language),
            attributes=attr_map,
        )

    def _append_code_use(
        self,
        attr_map: Mapping[str, str],
        location: SourceLocation,
    ) -> None:
        name = attr_map.get("use", "").strip()
        if not name:
            self.diagnostics.append(f"{location.display()}: empty code use")
            return
        self.events.append(
            CodeUse(
                name=name,
                location=location,
                language=_language(attr_map, self.default_language),
                attributes=attr_map,
            )
        )

    def _append_code_block(self, code: CodeBlock) -> None:
        self.events.append(code)
        if code.name is None:
            return
        if code.name in self.named_code:
            self.diagnostics.append(
                f"{code.location.display()}: duplicate code block name "
                f"{code.name!r}; later definition wins"
            )
        self.named_code[code.name] = code

    def _start_result(
        self,
        attr_map: Mapping[str, str],
        location: SourceLocation,
    ) -> None:
        code = attr_map.get("data-code", "").strip()
        if not code:
            self.diagnostics.append(
                f"{location.display()}: result span missing data-code"
            )
        self._results.append(
            _ResultBuilder(
                location=location,
                code=code,
                compare=_compare_policy(attr_map),
                language=_language(attr_map, self.default_language),
                attributes=attr_map,
            )
        )

    def _finish_result(self) -> None:
        result = self._results.pop().build()
        self.events.append(result)

    def _location(self) -> SourceLocation:
        line, column = self.getpos()
        return SourceLocation(path=self.path, line=line, column=column + 1)


def parse_document(source: str, path: Path | None = None) -> Document:
    """Parse a Markdown or HTML document containing Provedown HTML contracts."""

    frontmatter = _extract_frontmatter(source, path)
    parser = _ProvedownHTMLParser(
        source=source,
        path=path,
        default_language=frontmatter.provedown.default_language,
    )
    parser.diagnostics.extend(frontmatter.diagnostics)
    try:
        masked = _mask_markdown_fenced_code(
            _mask_frontmatter(source, frontmatter.end_line)
        )
        parser.feed(masked)
        parser.close()
    except Exception as exc:  # pragma: no cover - HTMLParser is broad by design.
        raise ParseError(str(exc)) from exc

    return Document(
        source=source,
        path=path,
        events=parser.events,
        named_code=parser.named_code,
        frontmatter=frontmatter.data,
        provedown=frontmatter.provedown,
        diagnostics=parser.diagnostics,
    )


def parse_file(path: Path) -> Document:
    return parse_document(path.read_text(encoding="utf-8"), path=path)


def _extract_frontmatter(source: str, path: Path | None) -> _Frontmatter:
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return _Frontmatter()

    closing_line = _frontmatter_closing_line(lines)
    if closing_line is None:
        return _Frontmatter()

    diagnostics: list[str] = []
    text = "".join(lines[1:closing_line])
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: invalid YAML frontmatter: "
            f"{exc}"
        )
        return _Frontmatter(diagnostics=diagnostics, end_line=closing_line + 1)

    if loaded is None:
        data: dict[str, Any] = {}
    elif isinstance(loaded, Mapping):
        data = {str(key): value for key, value in loaded.items()}
    else:
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: YAML frontmatter "
            "should be a mapping"
        )
        data = {}

    return _Frontmatter(
        data=data,
        provedown=_provedown_config(data, path, diagnostics),
        diagnostics=diagnostics,
        end_line=closing_line + 1,
    )


def _frontmatter_closing_line(lines: Sequence[str]) -> int | None:
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() in {"---", "..."}:
            return index
    return None


def _provedown_config(
    frontmatter: Mapping[str, Any],
    path: Path | None,
    diagnostics: list[str],
) -> ProvedownConfig:
    raw = frontmatter.get("provedown")
    if raw is None:
        return ProvedownConfig()

    if not isinstance(raw, Mapping):
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: provedown frontmatter "
            "should be a mapping"
        )
        return ProvedownConfig()

    aliases: dict[str, str] = {}
    aliases.update(_aliases(raw.get("data_aliases"), path, diagnostics))
    aliases.update(_aliases(raw.get("aliases"), path, diagnostics))

    return ProvedownConfig(
        aliases=aliases,
        environments=_environments(raw.get("environments"), path, diagnostics),
        last_validated=_optional_text(raw.get("last_validated")),
        default_language=(
            _optional_text(raw.get("default_language")) or "python"
        ),
        pyproject=(
            _optional_text(raw.get("pyproject"))
            or _optional_text(raw.get("pyproject_toml"))
        ),
    )


def _environments(
    raw: object,
    path: Path | None,
    diagnostics: list[str],
) -> dict[str, Mapping[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: provedown environments "
            "should be a mapping"
        )
        return {}

    environments: dict[str, Mapping[str, Any]] = {}
    for key, value in raw.items():
        name = str(key).strip() if key is not None else ""
        if not name:
            diagnostics.append(
                f"{_frontmatter_location(path).display()}: provedown environment "
                "name should not be empty"
            )
            continue
        if not isinstance(value, Mapping):
            diagnostics.append(
                f"{_frontmatter_location(path).display()}: provedown environment "
                f"{name!r} should be a mapping"
            )
            continue
        environments[name] = {str(item_key): item for item_key, item in value.items()}
    return environments


def _aliases(
    raw: object,
    path: Path | None,
    diagnostics: list[str],
) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        diagnostics.append(
            f"{_frontmatter_location(path).display()}: provedown aliases "
            "should be a mapping"
        )
        return {}

    aliases: dict[str, str] = {}
    for key, value in raw.items():
        if key is None or value is None:
            continue
        alias = str(key).strip()
        target = str(value).strip()
        if alias and target:
            aliases[alias] = target
    return aliases


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _frontmatter_location(path: Path | None) -> SourceLocation:
    return SourceLocation(path=path, line=1, column=1)


def _mask_frontmatter(source: str, end_line: int) -> str:
    if end_line <= 0:
        return source

    lines = source.splitlines(keepends=True)
    return "".join(
        _mask_line_preserving_newline(line) if index < end_line else line
        for index, line in enumerate(lines)
    )


def _attrs_to_dict(attrs: Sequence[tuple[str, str | None]]) -> dict[str, str]:
    return {name: value or "" for name, value in attrs}


def _has_class(attrs: Mapping[str, str], class_name: str) -> bool:
    return class_name in attrs.get("class", "").split()


def _is_ignored_region(attrs: Mapping[str, str]) -> bool:
    return attrs.get("data-provedown-ignore", "").lower() in {
        "1",
        "true",
        "yes",
    } or _has_class(attrs, "provedown-ignore")


def _language(attrs: Mapping[str, str], default_language: str) -> str:
    return (
        attrs.get("data-language")
        or attrs.get("language")
        or attrs.get("lang")
        or default_language
        or "python"
    ).strip() or "python"


def _compare_policy(attrs: Mapping[str, str]) -> str:
    if "data-compare" in attrs and attrs["data-compare"].strip():
        return attrs["data-compare"].strip()
    if "tol" in attrs or "data-tol" in attrs:
        return "tol"
    if "seed" in attrs or "data-seed" in attrs:
        return "seed"
    return "exact"


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _mask_markdown_fenced_code(source: str) -> str:
    """Hide Markdown fenced-code contents from the HTML parser.

    Provedown's contract is expressed as HTML in Markdown, but documentation
    often needs to show that raw HTML contract inside fenced code blocks. The
    parser does not otherwise understand Markdown, so this lightweight mask
    prevents examples from becoming live assertions while preserving line and
    column positions for real HTML outside the fences.
    """

    lines = source.splitlines(keepends=True)
    masked: list[str] = []
    fence_char: str | None = None
    fence_len = 0

    for line in lines:
        marker = _fence_marker(line)
        if fence_char is None:
            masked.append(line)
            if marker is not None:
                fence_char, fence_len = marker
            continue

        if (
            marker is not None
            and marker[0] == fence_char
            and marker[1] >= fence_len
        ):
            masked.append(line)
            fence_char = None
            fence_len = 0
        else:
            masked.append(_mask_line_preserving_newline(line))

    return "".join(masked)


def _fence_marker(line: str) -> tuple[str, int] | None:
    stripped = line.lstrip()
    if not stripped.startswith(("```", "~~~")):
        return None

    char = stripped[0]
    count = 0
    for character in stripped:
        if character != char:
            break
        count += 1
    if count < 3:
        return None
    return char, count


def _mask_line_preserving_newline(line: str) -> str:
    return "".join("\n" if character == "\n" else " " for character in line)
