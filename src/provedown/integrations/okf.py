"""Compatibility shim for Open Knowledge Format (OKF) documents.

OKF describes structured knowledge as Markdown with YAML frontmatter. Provedown
already parses and preserves that frontmatter, so most OKF concept documents are
valid Provedown documents with no changes at all: authored claims marked with the
Provedown HTML contract are verified, and every OKF key is left untouched.

One OKF convention does not line up. An ``Attested Computation`` carries its
computation as a Markdown fenced code block under a ``# Computation`` heading, or
in a separate file named by the ``computation`` frontmatter key. Provedown
deliberately treats fenced code as a literal example and never executes it, so a
bundle authored the ordinary OKF way gets no coverage.

This module bridges that gap. It parses the document with the normal parser, then
*lifts* the OKF computation into a named :class:`~provedown.model.CodeBlock` that
the regular verifiers can execute, without rewriting the document on disk and
without changing how fenced code behaves for anyone else.

The lifted block is a definition, so reference it by name::

    <span class="result" data-code="#computation">225.50<span
      class="method"></span></span>

Parameterised computations are supported through bindings declared in
frontmatter, which keeps OKF's rule that a producer may supply values only for
declared parameters and must not edit the computation itself::

    provedown:
      okf:
        bindings:
          fy2026: { year: 2026 }

Each binding becomes its own named block with the declared ``@parameter``
placeholders replaced by literals.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from provedown.model import CodeBlock, Document, DocumentEvent, SourceLocation
from provedown.parser import fence_marker, parse_document
from provedown.report import Report
from provedown.runner import verify_document
from provedown.verifiers import VerificationContext, VerifierRegistry

ATTESTED_COMPUTATION_TYPE = "attested computation"
COMPUTATION_HEADING = "computation"
DEFAULT_COMPUTATION_NAME = "computation"

TRUST_UNVERIFIED = "unverified"
TRUST_MACHINE_CONFIRMED = "machine-confirmed"
TRUST_HUMAN_REVIEWED = "human-reviewed"

HUMAN_ACTOR_PREFIX = "human:"

#: OKF ``runtime`` values that a built-in Provedown verifier can execute.
#:
#: Runtimes outside this mapping (``bigquery``, ``postgres``, ``dbt``, ...) are
#: reported rather than silently executed by a verifier that does not speak the
#: same dialect. Set ``provedown.okf.runtime_language`` to override when the
#: computation is portable enough to check locally.
RUNTIME_LANGUAGES: Mapping[str, str] = {
    "duckdb": "duckdb",
    "duckdb-sql": "duckdb",
    "sql": "duckdb",
    "python": "python",
}

_HEADING = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*$")
_PARAMETER_REFERENCE = "@{name}"

_INTEGER_TYPES = {"integer", "int", "int64", "bigint", "smallint"}
_NUMBER_TYPES = {"number", "float", "float64", "double", "numeric", "decimal"}
_BOOLEAN_TYPES = {"boolean", "bool"}


@dataclass(frozen=True)
class OkfParameter:
    """One entry of an Attested Computation's declared ``parameters`` list."""

    name: str
    type: str | None = None
    required: bool = False


@dataclass(frozen=True)
class OkfMetadata:
    """OKF frontmatter, including the v0.2 trust signals.

    Values are normalised but never rewritten: unknown keys stay available on
    ``Document.frontmatter``, as OKF requires of consumers.
    """

    type: str | None = None
    title: str | None = None
    description: str | None = None
    resource: str | None = None
    tags: tuple[str, ...] = ()
    runtime: str | None = None
    computation: str | None = None
    parameters: tuple[OkfParameter, ...] = ()
    generated: Mapping[str, Any] | None = None
    verified: tuple[Mapping[str, Any], ...] = ()
    status: str = "stable"
    stale_after: str | None = None
    sources: tuple[Mapping[str, Any], ...] = ()

    @property
    def is_attested_computation(self) -> bool:
        return (self.type or "").strip().lower() == ATTESTED_COMPUTATION_TYPE

    def parameter(self, name: str) -> OkfParameter | None:
        for parameter in self.parameters:
            if parameter.name == name:
                return parameter
        return None

    def trust_tier(self) -> str:
        """Derive OKF's trust tier from the ``verified`` actors.

        No ``verified`` entry is ``unverified``; machine actors only is
        ``machine-confirmed``; any ``human:`` actor is ``human-reviewed``.
        """

        if not self.verified:
            return TRUST_UNVERIFIED
        for entry in self.verified:
            actor = _text(entry.get("by")) or ""
            if actor.lower().startswith(HUMAN_ACTOR_PREFIX):
                return TRUST_HUMAN_REVIEWED
        return TRUST_MACHINE_CONFIRMED

    def is_stale(self, today: date | None = None) -> bool:
        """Report whether ``stale_after`` has passed.

        A document with no ``stale_after``, or one whose value is not an ISO
        date, is never reported stale: the field is an optional hint, and
        Provedown's own verification is the stronger signal.
        """

        if self.stale_after is None:
            return False
        try:
            deadline = date.fromisoformat(self.stale_after[:10])
        except ValueError:
            return False
        return (today or date.today()) > deadline


@dataclass(frozen=True)
class OkfConfig:
    """The ``provedown.okf`` frontmatter block."""

    computation_name: str = DEFAULT_COMPUTATION_NAME
    runtime_language: str | None = None
    bindings: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class OkfDocument:
    """An OKF document prepared for verification.

    ``document`` is an ordinary Provedown :class:`~provedown.model.Document` and
    can be passed to any verifier, inspector, or linter.
    """

    document: Document
    metadata: OkfMetadata
    config: OkfConfig = field(default_factory=OkfConfig)
    computation: CodeBlock | None = None
    bindings: Mapping[str, CodeBlock] = field(default_factory=dict)


def parse_okf_document(source: str, path: Path | None = None) -> OkfDocument:
    """Parse an OKF document and lift its computation into executable markup."""

    base = parse_document(source, path=path)
    metadata = _metadata(base.frontmatter)
    diagnostics: list[str] = []
    config = _config(base.frontmatter, path, diagnostics)

    if not metadata.is_attested_computation:
        return OkfDocument(
            document=_augmented(base, [], diagnostics),
            metadata=metadata,
            config=config,
        )

    language = _language(metadata, config, path, diagnostics)
    if language is None:
        return OkfDocument(
            document=_augmented(base, [], diagnostics),
            metadata=metadata,
            config=config,
        )

    base = _retargeted(base, language)
    computation = _computation_block(
        source=source,
        document=base,
        metadata=metadata,
        config=config,
        language=language,
        path=path,
        diagnostics=diagnostics,
    )
    bindings = (
        {}
        if computation is None
        else _bindings(
            computation=computation,
            document=base,
            metadata=metadata,
            config=config,
            diagnostics=diagnostics,
        )
    )

    lifted = _lifted(base, computation, bindings)
    return OkfDocument(
        document=_augmented(base, lifted, diagnostics),
        metadata=metadata,
        config=config,
        computation=computation,
        bindings=bindings,
    )


def parse_okf_file(path: Path) -> OkfDocument:
    """Parse one OKF document from disk."""

    return parse_okf_document(path.read_text(encoding="utf-8"), path=path)


def verify_okf_file(
    path: Path,
    registry: VerifierRegistry | None = None,
    verifier_ids: Sequence[str] | None = None,
    sandbox: str | None = None,
) -> Report:
    """Verify one OKF document, lifting its computation first."""

    okf = parse_okf_file(path)
    context = VerificationContext(cwd=path.parent, sandbox=sandbox)
    return verify_document(
        okf.document,
        registry=registry,
        context=context,
        verifier_ids=verifier_ids,
    )


def _metadata(frontmatter: Mapping[str, Any]) -> OkfMetadata:
    return OkfMetadata(
        type=_text(frontmatter.get("type")),
        title=_text(frontmatter.get("title")),
        description=_text(frontmatter.get("description")),
        resource=_text(frontmatter.get("resource")),
        tags=tuple(_texts(frontmatter.get("tags"))),
        runtime=_text(frontmatter.get("runtime")),
        computation=_text(frontmatter.get("computation")),
        parameters=_parameters(frontmatter.get("parameters")),
        generated=_mapping(frontmatter.get("generated")),
        verified=_mappings(frontmatter.get("verified")),
        status=_text(frontmatter.get("status")) or "stable",
        stale_after=_text(frontmatter.get("stale_after")),
        sources=_mappings(frontmatter.get("sources")),
    )


def _parameters(raw: object) -> tuple[OkfParameter, ...]:
    parameters: list[OkfParameter] = []
    for entry in _sequence(raw):
        if not isinstance(entry, Mapping):
            continue
        name = _text(entry.get("name"))
        if name is None:
            continue
        parameters.append(
            OkfParameter(
                name=name,
                type=_text(entry.get("type")),
                required=bool(entry.get("required", False)),
            )
        )
    return tuple(parameters)


def _config(
    frontmatter: Mapping[str, Any],
    path: Path | None,
    diagnostics: list[str],
) -> OkfConfig:
    provedown = frontmatter.get("provedown")
    raw = provedown.get("okf") if isinstance(provedown, Mapping) else None
    if raw is None:
        return OkfConfig()
    if not isinstance(raw, Mapping):
        diagnostics.append(
            _diagnostic(path, "provedown okf frontmatter should be a mapping")
        )
        return OkfConfig()

    bindings: dict[str, Mapping[str, Any]] = {}
    raw_bindings = raw.get("bindings")
    if raw_bindings is not None and not isinstance(raw_bindings, Mapping):
        diagnostics.append(
            _diagnostic(path, "provedown okf bindings should be a mapping")
        )
    elif isinstance(raw_bindings, Mapping):
        for key, value in raw_bindings.items():
            name = str(key).strip()
            if not name:
                continue
            if not isinstance(value, Mapping):
                diagnostics.append(
                    _diagnostic(
                        path,
                        f"binding {name!r} should be a mapping of parameter values",
                    )
                )
                continue
            bindings[name] = {str(k): v for k, v in value.items()}

    return OkfConfig(
        computation_name=(
            _text(raw.get("computation_name")) or DEFAULT_COMPUTATION_NAME
        ),
        runtime_language=_text(raw.get("runtime_language")),
        bindings=bindings,
    )


def _language(
    metadata: OkfMetadata,
    config: OkfConfig,
    path: Path | None,
    diagnostics: list[str],
) -> str | None:
    if config.runtime_language is not None:
        return config.runtime_language

    runtime = (metadata.runtime or "").strip().lower()
    if not runtime:
        diagnostics.append(
            _diagnostic(path, "attested computation is missing a runtime")
        )
        return None

    language = RUNTIME_LANGUAGES.get(runtime)
    if language is None:
        diagnostics.append(
            _diagnostic(
                path,
                f"no built-in verifier runs the {runtime!r} runtime; set "
                "provedown.okf.runtime_language to check the computation with "
                "another language, or register a verifier plugin for it",
            )
        )
    return language


def _computation_block(
    *,
    source: str,
    document: Document,
    metadata: OkfMetadata,
    config: OkfConfig,
    language: str,
    path: Path | None,
    diagnostics: list[str],
) -> CodeBlock | None:
    name = config.computation_name
    if name in document.named_code:
        diagnostics.append(
            _diagnostic(
                path,
                f"document already defines a code block named {name!r}; set "
                "provedown.okf.computation_name to lift the computation under "
                "another name",
            )
        )
        return None

    located = _external_computation(metadata, path, diagnostics)
    if located is None:
        located = _fenced_computation(source, path)
    if located is None:
        diagnostics.append(
            _diagnostic(
                path,
                "attested computation has no computation: add a fenced code "
                f"block under a '# {COMPUTATION_HEADING.title()}' heading, or "
                "name one with the computation frontmatter key",
            )
        )
        return None

    code, location = located
    if not code.strip():
        diagnostics.append(_diagnostic(path, "attested computation is empty"))
        return None

    return CodeBlock(
        code=code.strip("\n"),
        location=location,
        name=name,
        language=language,
        attributes={"data-okf": "computation"},
    )


def _external_computation(
    metadata: OkfMetadata,
    path: Path | None,
    diagnostics: list[str],
) -> tuple[str, SourceLocation] | None:
    reference = metadata.computation
    if reference is None:
        return None

    target = Path(reference)
    if not target.is_absolute():
        if path is None:
            diagnostics.append(
                _diagnostic(
                    path,
                    f"cannot resolve relative computation {reference!r} for a "
                    "document parsed without a path",
                )
            )
            return None
        target = path.parent / target

    try:
        code = target.read_text(encoding="utf-8")
    except OSError as exc:
        diagnostics.append(
            _diagnostic(path, f"cannot read computation {reference!r}: {exc}")
        )
        return None

    return code, SourceLocation(path=target, line=1, column=1)


def _fenced_computation(
    source: str,
    path: Path | None,
) -> tuple[str, SourceLocation] | None:
    """Locate the first fenced block under the ``# Computation`` heading.

    Fence detection is shared with the parser, so the region lifted here is
    exactly the region the parser masks.
    """

    lines = source.splitlines(keepends=True)
    index = _body_start(lines)
    in_computation_section = False
    while index < len(lines):
        line = lines[index]
        marker = fence_marker(line)

        if marker is not None:
            closing = _fence_close(lines, index + 1, marker)
            if in_computation_section:
                body = "".join(lines[index + 1 : closing])
                return body, SourceLocation(path=path, line=index + 2, column=1)
            index = closing + 1
            continue

        heading = _HEADING.match(line.rstrip("\n"))
        if heading is not None:
            title = heading.group("title").strip().lower()
            in_computation_section = title == COMPUTATION_HEADING
        index += 1

    return None


def _fence_close(
    lines: Sequence[str],
    start: int,
    marker: tuple[str, int],
) -> int:
    char, length = marker
    for index in range(start, len(lines)):
        closing = fence_marker(lines[index])
        if closing is not None and closing[0] == char and closing[1] >= length:
            return index
    return len(lines)


def _body_start(lines: Sequence[str]) -> int:
    """Return the first line index after YAML frontmatter.

    Mirrors the parser's frontmatter rule so a ``# Computation`` comment inside
    frontmatter is never mistaken for the body heading.
    """

    if not lines or lines[0].strip() != "---":
        return 0
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() in {"---", "..."}:
            return index + 1
    return len(lines)


def _bindings(
    *,
    computation: CodeBlock,
    document: Document,
    metadata: OkfMetadata,
    config: OkfConfig,
    diagnostics: list[str],
) -> dict[str, CodeBlock]:
    path = document.path
    referenced = _referenced_parameters(computation.code, metadata)

    bindings: dict[str, CodeBlock] = {}
    for name, values in config.bindings.items():
        if name in document.named_code or name == computation.name:
            diagnostics.append(
                _diagnostic(
                    path,
                    f"binding {name!r} collides with an existing code block name",
                )
            )
            continue

        code = _bind(
            computation=computation,
            binding=name,
            values=values,
            metadata=metadata,
            referenced=referenced,
            path=path,
            diagnostics=diagnostics,
        )
        if code is None:
            continue

        bindings[name] = dataclasses.replace(
            computation,
            code=code,
            name=name,
            attributes={"data-okf": "binding", "data-okf-binding": name},
        )
    return bindings


def _bind(
    *,
    computation: CodeBlock,
    binding: str,
    values: Mapping[str, Any],
    metadata: OkfMetadata,
    referenced: frozenset[str],
    path: Path | None,
    diagnostics: list[str],
) -> str | None:
    ok = True

    for supplied in values:
        if metadata.parameter(supplied) is None:
            diagnostics.append(
                _diagnostic(
                    path,
                    f"binding {binding!r} supplies {supplied!r}, which the "
                    "computation does not declare as a parameter",
                )
            )
            ok = False

    for parameter in metadata.parameters:
        if parameter.name in values:
            continue
        if parameter.required:
            diagnostics.append(
                _diagnostic(
                    path,
                    f"binding {binding!r} is missing required parameter "
                    f"{parameter.name!r}",
                )
            )
            ok = False
        elif parameter.name in referenced:
            diagnostics.append(
                _diagnostic(
                    path,
                    f"binding {binding!r} is missing parameter "
                    f"{parameter.name!r}, which the computation references",
                )
            )
            ok = False

    if not ok:
        return None

    code = computation.code
    for parameter in metadata.parameters:
        if parameter.name not in values:
            continue
        literal = _literal(
            values[parameter.name],
            parameter=parameter,
            language=computation.language,
        )
        if literal is None:
            diagnostics.append(
                _diagnostic(
                    path,
                    f"binding {binding!r} value for {parameter.name!r} is not a "
                    f"valid {parameter.type}",
                )
            )
            return None
        code = code.replace(_PARAMETER_REFERENCE.format(name=parameter.name), literal)
    return code


def _referenced_parameters(code: str, metadata: OkfMetadata) -> frozenset[str]:
    """Return declared parameters that appear as ``@name`` in the computation.

    Only declared names count, so an ``@`` inside a string literal (an email
    address, say) is never mistaken for a placeholder.
    """

    return frozenset(
        parameter.name
        for parameter in metadata.parameters
        if _PARAMETER_REFERENCE.format(name=parameter.name) in code
    )


def _literal(
    value: Any,
    *,
    parameter: OkfParameter,
    language: str,
) -> str | None:
    declared = (parameter.type or "").strip().lower()

    try:
        if declared in _INTEGER_TYPES:
            coerced: Any = int(value)
        elif declared in _NUMBER_TYPES:
            coerced = float(value)
        elif declared in _BOOLEAN_TYPES:
            coerced = bool(value)
        else:
            coerced = str(value)
    except (TypeError, ValueError):
        return None

    if language.strip().lower() in {"python", "py"}:
        return repr(coerced)
    if isinstance(coerced, bool):
        return "TRUE" if coerced else "FALSE"
    if isinstance(coerced, (int, float)):
        return str(coerced)
    return "'" + str(coerced).replace("'", "''") + "'"


def _lifted(
    document: Document,
    computation: CodeBlock | None,
    bindings: Mapping[str, CodeBlock],
) -> list[CodeBlock]:
    """Choose which lifted blocks to register as named code.

    A parameterised computation that no claim references directly is only a
    template for its bindings: registering it would leave a block nothing can
    run, since its placeholders are still in place.
    """

    if computation is None:
        return []
    blocks = list(bindings.values())
    if not bindings or computation.name in set(document.referenced_code_names()):
        blocks.insert(0, computation)
    return blocks


def _retargeted(document: Document, language: str) -> Document:
    """Point events with no explicit language at the OKF runtime's language.

    An OKF document states its language once, as ``runtime``. Without this the
    document's claims would fall back to Provedown's ``python`` default, and a
    DuckDB computation would be quietly *skipped* by the Python verifier rather
    than checked. An explicit ``provedown.default_language`` still wins, as do
    per-element language attributes.
    """

    provedown = document.frontmatter.get("provedown")
    if isinstance(provedown, Mapping) and _text(provedown.get("default_language")):
        return document

    events = [_retarget(event, language) for event in document.events]
    named_code = {
        event.name: event
        for event in events
        if isinstance(event, CodeBlock) and event.name is not None
    }
    return dataclasses.replace(
        document,
        events=events,
        named_code=named_code,
        provedown=dataclasses.replace(document.provedown, default_language=language),
    )


def _retarget(event: DocumentEvent, language: str) -> DocumentEvent:
    if _has_explicit_language(event.attributes):
        return event
    return dataclasses.replace(event, language=language)


def _has_explicit_language(attributes: Mapping[str, str]) -> bool:
    return any(
        attributes.get(key, "").strip()
        for key in ("data-language", "language", "lang")
    )


def _augmented(
    document: Document,
    lifted: Sequence[CodeBlock],
    diagnostics: Sequence[str],
) -> Document:
    """Return ``document`` with lifted blocks and OKF diagnostics folded in.

    Lifted blocks are registered as named definitions only, never appended to
    ``events``: a computation runs where a claim references it, and a
    parameterised one is never executed with its placeholders still in place.
    """

    if not lifted and not diagnostics:
        return document

    named_code = dict(document.named_code)
    for block in lifted:
        if block.name is not None:
            named_code[block.name] = block

    return dataclasses.replace(
        document,
        named_code=named_code,
        diagnostics=[*document.diagnostics, *diagnostics],
    )


def _diagnostic(path: Path | None, message: str) -> str:
    location = SourceLocation(path=path, line=1, column=1)
    return f"{location.display()}: okf: {message}"


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _texts(raw: object) -> list[str]:
    return [text for text in (_text(item) for item in _sequence(raw)) if text]


def _sequence(raw: object) -> list[Any]:
    if raw is None or isinstance(raw, (str, bytes, Mapping)):
        return []
    if isinstance(raw, Sequence):
        return list(raw)
    return []


def _mapping(raw: object) -> Mapping[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    return {str(key): value for key, value in raw.items()}


def _mappings(raw: object) -> tuple[Mapping[str, Any], ...]:
    mappings: list[Mapping[str, Any]] = []
    for entry in _sequence(raw):
        mapping = _mapping(entry)
        if mapping is not None:
            mappings.append(mapping)
    return tuple(mappings)
