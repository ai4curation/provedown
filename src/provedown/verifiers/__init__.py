"""Verifier plugin interfaces and default registry."""

from __future__ import annotations

import traceback
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Protocol

from provedown.compare import ComparatorRegistry, default_comparators
from provedown.model import Document, SourceLocation
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
        self._verifiers[verifier.verifier_id] = verifier

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
        self.check_ids(verifier_ids or ())
        selected = (
            [self._verifiers[name] for name in verifier_ids]
            if verifier_ids is not None
            else [self._verifiers[name] for name in self.names()]
        )
        findings: list[Finding] = []
        for verifier in selected:
            findings.extend(_run_verifier(verifier, document, active_context))
        return Report.from_findings(findings)

    def check_ids(self, verifier_ids: Iterable[str]) -> None:
        """Raise ``UnknownVerifierError`` for the first id that is not registered."""

        for verifier_id in verifier_ids:
            if verifier_id not in self._verifiers:
                raise UnknownVerifierError(
                    f"unknown verifier {verifier_id!r}; available: "
                    f"{', '.join(self.names())}"
                )


def _run_verifier(
    verifier: Verifier,
    document: Document,
    context: VerificationContext,
) -> list[Finding]:
    """Run one verifier, turning a raise or a non-``Finding`` into an error.

    Verifiers should return ``error`` findings rather than raise. Plugins are
    third-party code, so one that raises anyway, or yields something that is
    not a ``Finding``, is reported against its own id, with the traceback in the
    finding's evidence, instead of discarding the findings of every other
    verifier and document. Findings yielded before the problem are kept.
    """

    findings: list[Finding] = []
    try:
        for finding in verifier.verify(document, context):
            if not isinstance(finding, Finding):
                raise TypeError(f"verifier yielded {finding!r}, which is not a Finding")
            findings.append(finding)
    except Exception as exc:  # Verifier code may be a third-party plugin.
        findings.append(
            Finding(
                verifier_id=verifier.verifier_id,
                status=Status.ERROR,
                location=SourceLocation(path=document.path, line=1, column=1),
                message=f"verifier raised {type(exc).__name__}: {exc}",
                evidence={"traceback": traceback.format_exc()},
            )
        )
    return findings


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
        for verifier in _load_plugins(taken):
            registry.register(verifier)
    return registry


def load_plugin_verifiers() -> list[Verifier]:
    """Instantiate the verifiers advertised in the ``provedown.verifiers`` group.

    Entry points are loaded in name order. A plugin that cannot be imported or
    constructed, that does not return a verifier with a ``verifier_id``, or
    whose id an earlier plugin already uses, raises ``PluginLoadError`` naming
    the entry point and the distribution that provides it, so a broken install
    is easy to trace.
    """

    return _load_plugins({})


def _load_plugins(taken: Mapping[str, str]) -> list[Verifier]:
    """Load plugins in name order; ``taken`` maps used ids to who holds them."""

    found = sorted(
        entry_points(group=VERIFIER_ENTRY_POINT_GROUP),
        key=lambda entry_point: entry_point.name,
    )
    holders = dict(taken)
    verifiers: list[Verifier] = []
    for entry_point in found:
        verifier = _load_plugin(entry_point)
        holder = holders.get(verifier.verifier_id)
        if holder is not None:
            raise PluginLoadError(
                f"verifier plugin {_describe(entry_point)} uses the id "
                f"{verifier.verifier_id!r}, which is already registered by "
                f"{holder}"
            )
        holders[verifier.verifier_id] = _describe(entry_point)
        verifiers.append(verifier)
    return verifiers


def _load_plugin(entry_point: EntryPoint) -> Verifier:
    try:
        factory = entry_point.load()
        verifier = factory()
    except Exception as exc:  # Plugin code is outside Provedown's control.
        raise PluginLoadError(
            f"cannot load verifier plugin {_describe(entry_point)}: {exc}"
        ) from exc
    # Verifier is a Protocol, so nothing checked what the factory returned.
    verifier_id = getattr(verifier, "verifier_id", None)
    if not isinstance(verifier_id, str) or not verifier_id:
        raise PluginLoadError(
            f"verifier plugin {_describe(entry_point)} returned {verifier!r}, "
            "which has no verifier_id"
        )
    if not callable(getattr(verifier, "verify", None)):
        raise PluginLoadError(
            f"verifier plugin {_describe(entry_point)} returned {verifier!r}, "
            "which has no verify() method"
        )
    loaded: Verifier = verifier
    return loaded


def _describe(entry_point: EntryPoint) -> str:
    distribution = entry_point.dist.name if entry_point.dist is not None else None
    origin = f" from {distribution}" if distribution else ""
    return f"{entry_point.name!r}{origin} ({entry_point.value})"
