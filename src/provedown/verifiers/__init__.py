"""Verifier plugin interfaces and default registry."""

from __future__ import annotations

import reprlib
import traceback
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Protocol

from provedown.compare import ComparatorRegistry, default_comparators
from provedown.model import Document
from provedown.report import Finding, Report, Status

# Installed packages advertise verifiers under this entry-point group. Each
# entry point names a verifier class, or any callable that takes no arguments
# and returns a verifier, e.g. in the plugin's pyproject.toml:
#
#   [project.entry-points."provedown.verifiers"]
#   quotes = "my_package.provedown_plugin:QuoteVerifier"
VERIFIER_ENTRY_POINT_GROUP = "provedown.verifiers"


class PluginLoadError(RuntimeError):
    """Raised when an installed verifier plugin cannot be loaded or registered."""


class UnknownVerifierError(KeyError):
    """Raised when a requested verifier id is not registered."""

    def __str__(self) -> str:
        # KeyError's own __str__ shows the message in quotes, as a repr.
        return str(self.args[0]) if self.args else super().__str__()


@dataclass
class VerificationContext:
    """Runtime options shared by verifier plugins."""

    cwd: Path | None = None
    comparators: ComparatorRegistry = field(default_factory=default_comparators)
    sandbox: str | None = None


class Verifier(Protocol):
    """Protocol implemented by all verifier plugins."""

    verifier_id: str

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        """Return findings for a parsed document."""


class VerifierRegistry:
    """Small plugin registry for verifier-neutral orchestration."""

    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {}

    def register(self, verifier: Verifier) -> None:
        """Register ``verifier`` under its id, replacing one with the same id.

        Raises ``TypeError`` unless it has a non-empty string ``verifier_id``
        and a ``verify()`` method, the shape the rest of the registry relies on.
        """

        try:
            verifier_id = _validated_id(verifier)
        except _NotAVerifier as problem:
            raise TypeError(
                f"cannot register {_short_repr(verifier)}: {problem}"
            ) from problem.__cause__
        self._register_as(verifier_id, verifier)

    def _register_as(self, verifier_id: str, verifier: Verifier) -> None:
        # For an id already validated by _validated_id.
        self._verifiers[verifier_id] = verifier

    def get(self, verifier_id: str) -> Verifier:
        self.check_ids([verifier_id])
        return self._verifiers[verifier_id]

    def names(self) -> list[str]:
        return sorted(self._verifiers)

    def verify(
        self,
        document: Document,
        context: VerificationContext | None = None,
        verifier_ids: Sequence[str] | None = None,
    ) -> Report:
        active_context = context or VerificationContext()
        self.check_requested_ids(verifier_ids)
        # A repeated id runs its verifier once.
        selected = (
            list(dict.fromkeys(verifier_ids))
            if verifier_ids is not None
            else self.names()
        )
        findings: list[Finding] = []
        for verifier_id in selected:
            findings.extend(
                _run_verifier(
                    verifier_id, self._verifiers[verifier_id], document, active_context
                )
            )
        return Report.from_findings(findings)

    def check_requested_ids(self, verifier_ids: Sequence[str] | None) -> None:
        """Check a request to run ``verifier_ids``, where ``None`` means all.

        Raises ``ValueError`` for an empty list, since running nothing must not
        look like a passing report, and ``UnknownVerifierError`` for an id that
        is not registered.
        """

        if verifier_ids is None:
            return
        if not verifier_ids:
            raise ValueError("no verifier ids given; pass None to run them all")
        self.check_ids(verifier_ids)

    def check_ids(self, verifier_ids: Iterable[str]) -> None:
        """Raise ``UnknownVerifierError`` for the first id that is not registered."""

        for verifier_id in verifier_ids:
            if verifier_id not in self._verifiers:
                raise UnknownVerifierError(
                    f"unknown verifier {verifier_id!r}; available: "
                    f"{', '.join(self.names())}"
                )


def _run_verifier(
    verifier_id: str,
    verifier: Verifier,
    document: Document,
    context: VerificationContext,
) -> list[Finding]:
    """Run one verifier, turning a raise or a non-``Finding`` into an error.

    Verifiers should return ``error`` findings rather than raise. Plugins are
    third-party code, so one that raises anyway, or yields something that is
    not a ``Finding``, is reported against its own id instead of discarding the
    findings of every other verifier and document. Findings yielded before the
    problem are kept.
    """

    findings: list[Finding] = []
    location = document.start_location()
    try:
        results = verifier.verify(document, context)
        try:
            for finding in results:
                if not isinstance(finding, Finding):
                    yielded = _short_repr(finding)
                    findings.append(
                        Finding(
                            verifier_id=verifier_id,
                            status=Status.ERROR,
                            location=location,
                            message=(
                                f"verifier yielded {yielded}, which is not a Finding"
                            ),
                            evidence={"yielded": yielded},
                        )
                    )
                    break
                findings.append(finding)
        finally:
            # Let a generator run its own cleanup now, not whenever it is freed.
            close = getattr(results, "close", None)
            if callable(close):
                close()
    except Exception as exc:  # Verifier code may be a third-party plugin.
        findings.append(
            Finding(
                verifier_id=verifier_id,
                status=Status.ERROR,
                location=location,
                message=f"verifier raised {type(exc).__name__}: {_safe_str(exc)}",
                evidence={"traceback": _short_traceback(exc)},
            )
        )
    return findings


_SHORT_REPR_LIMIT = 200
_SHORT_REPR = reprlib.Repr()
_SHORT_REPR.maxstring = _SHORT_REPR.maxother = _SHORT_REPR_LIMIT


def _short_repr(value: object) -> str:
    """Return ``repr(value)`` cut to a fixed length for a report.

    ``reprlib`` stops early on large built-in containers and strings, and
    replaces a third-party ``__repr__`` that raises with the type name; an
    arbitrary object's own ``__repr__`` still runs in full before the cut.
    """

    text = _SHORT_REPR.repr(value)
    limit = _SHORT_REPR_LIMIT
    return text if len(text) <= limit else text[: limit - 3] + "..."


_MESSAGE_LIMIT = 200


def _safe_str(exc: BaseException) -> str:
    """Return ``str(exc)`` cut to the report length, even if its ``__str__`` raises.

    An f-string calls ``__str__`` unguarded, unlike ``traceback`` formatting,
    which already tolerates a raising ``__str__``.
    """

    try:
        text = str(exc)
    except Exception:  # A plugin's exception is outside Provedown's control.
        return f"<unprintable {type(exc).__name__}>"
    limit = _MESSAGE_LIMIT
    return text if len(text) <= limit else text[: limit - 3] + "..."


_TRACEBACK_LIMIT = 4000


_TRACEBACK_PIECE_LIMIT = 500


def _short_traceback(exc: BaseException) -> str:
    """Format ``exc`` as ``traceback`` does, chained causes included, bounded.

    Each piece (a frame, or an exception's message line) is cut on its own, so
    one huge message cannot push the frames out. If the whole still does not
    fit, both its start and its end are kept, since the end holds the error.
    """

    pieces = traceback.TracebackException.from_exception(exc).format()
    text = "".join(
        piece
        if len(piece) <= _TRACEBACK_PIECE_LIMIT
        else piece[: _TRACEBACK_PIECE_LIMIT - 4] + "...\n"
        for piece in pieces
    )
    if len(text) <= _TRACEBACK_LIMIT:
        return text
    head = (_TRACEBACK_LIMIT - 5) // 2
    return text[:head] + "\n...\n" + text[-(_TRACEBACK_LIMIT - 5 - head) :]


class _NotAVerifier(Exception):
    """Says why an object is not a usable verifier, as "it ..."."""


def _validated_id(verifier: object) -> str:
    """Return the id of a usable verifier, or raise ``_NotAVerifier``.

    The id is read once, here; callers keep this value rather than reading the
    attribute again, so the id that was checked is the one used.
    """

    verifier_id = _read_attribute(verifier, "verifier_id", "verifier_id")
    if not isinstance(verifier_id, str) or not verifier_id:
        raise _NotAVerifier("it has no verifier_id")
    if not callable(_read_attribute(verifier, "verify", "verify attribute")):
        raise _NotAVerifier("it has no verify() method")
    return verifier_id


def _read_attribute(verifier: object, name: str, label: str) -> object:
    """Read ``name`` from a plugin object, or ``None`` when it has no such attribute.

    An exception raised while reading it, including an ``AttributeError`` from
    inside a property defined on the object, becomes ``_NotAVerifier`` chained to
    the plugin's exception, rather than being mistaken for a missing attribute.
    """

    try:
        return getattr(verifier, name)
    except AttributeError as exc:
        # Imported here: only a broken plugin reaches this branch.
        import inspect
        import types

        static = inspect.getattr_static(verifier, name, None)
        if static is None or isinstance(static, types.MemberDescriptorType):
            # Not defined, or an unset __slots__ entry: the attribute is absent.
            return None
        raise _NotAVerifier(
            f"it raised {type(exc).__name__} when its {label} was read"
        ) from exc
    except Exception as exc:  # A plugin's attributes are outside our control.
        raise _NotAVerifier(
            f"it raised {type(exc).__name__} when its {label} was read"
        ) from exc


def default_registry(*, plugins: bool = True) -> VerifierRegistry:
    """Return the built-in verifiers plus, unless ``plugins`` is false, any
    verifiers that installed packages advertise as entry points in the
    ``provedown.verifiers`` group.

    A plugin may not take the id of a verifier that is already registered.
    Raises ``PluginLoadError`` when a plugin cannot be loaded.
    """

    from provedown.verifiers.python import PythonResultVerifier
    from provedown.verifiers.sql import SQLResultVerifier

    registry = VerifierRegistry()
    registry.register(PythonResultVerifier())
    registry.register(SQLResultVerifier())
    if plugins:
        taken = dict.fromkeys(registry.names(), "a built-in verifier")
        for verifier_id, verifier in _load_plugins(taken):
            registry._register_as(verifier_id, verifier)
    return registry


def load_plugin_verifiers() -> list[Verifier]:
    """Instantiate the verifiers advertised in the ``provedown.verifiers`` group.

    Entry points are loaded in name order. A plugin that cannot be imported or
    constructed, that does not return a verifier with a ``verifier_id``, or
    whose id an earlier plugin already uses, raises ``PluginLoadError`` naming
    the entry point and the distribution that provides it, so a broken install
    is easy to trace.
    """

    return [verifier for _, verifier in _load_plugins({})]


def _load_plugins(taken: Mapping[str, str]) -> list[tuple[str, Verifier]]:
    """Load plugins in name order as ``(verifier_id, verifier)`` pairs.

    ``taken`` maps used ids to who holds them. Each id is the one validated at
    load time, used for clash detection and registration alike.
    """

    found = sorted(
        entry_points(group=VERIFIER_ENTRY_POINT_GROUP),
        key=lambda entry_point: entry_point.name,
    )
    holders = dict(taken)
    loaded: list[tuple[str, Verifier]] = []
    for entry_point in found:
        verifier_id, verifier = _load_plugin(entry_point)
        holder = holders.get(verifier_id)
        if holder is not None:
            raise PluginLoadError(
                f"verifier plugin {_describe(entry_point)} uses the id "
                f"{verifier_id!r}, which is already registered by {holder}"
            )
        holders[verifier_id] = _describe(entry_point)
        loaded.append((verifier_id, verifier))
    return loaded


def _load_plugin(entry_point: EntryPoint) -> tuple[str, Verifier]:
    try:
        factory = entry_point.load()
        verifier = factory()
    except Exception as exc:  # Plugin code is outside Provedown's control.
        raise PluginLoadError(
            f"cannot load verifier plugin {_describe(entry_point)}: "
            f"{type(exc).__name__}: {_safe_str(exc)}"
        ) from exc
    # Verifier is a Protocol, so nothing checked what the factory returned.
    try:
        verifier_id = _validated_id(verifier)
    except _NotAVerifier as problem:
        which = str(problem).removeprefix("it ")
        raise PluginLoadError(
            f"{_returned(entry_point, verifier)}, which {which}"
        ) from problem.__cause__
    loaded: Verifier = verifier
    return verifier_id, loaded


def _returned(entry_point: EntryPoint, verifier: object) -> str:
    # Built only on failure, so a loaded plugin's __repr__ never runs.
    return f"verifier plugin {_describe(entry_point)} returned {_short_repr(verifier)}"


def _describe(entry_point: EntryPoint) -> str:
    distribution = entry_point.dist.name if entry_point.dist is not None else None
    origin = f" from {distribution}" if distribution else ""
    return f"{entry_point.name!r}{origin} ({entry_point.value})"
