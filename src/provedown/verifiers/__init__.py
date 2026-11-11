"""Verifier plugin interfaces and default registry."""

from __future__ import annotations

from collections.abc import Iterable, Sequence, Set
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Protocol

from provedown.compare import ComparatorRegistry, default_comparators
from provedown.model import Document
from provedown.report import Finding, Report

# Installed packages advertise verifiers under this entry-point group. Each
# entry point names a verifier class, or any callable that takes no arguments
# and returns a verifier, e.g. in the plugin's pyproject.toml:
#
#   [project.entry-points."provedown.verifiers"]
#   quotes = "my_package.provedown_plugin:QuoteVerifier"
VERIFIER_ENTRY_POINT_GROUP = "provedown.verifiers"


class PluginLoadError(RuntimeError):
    """Raised when an installed verifier plugin cannot be loaded or registered."""


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
        selected = (
            [self._verifiers[name] for name in verifier_ids]
            if verifier_ids is not None
            else [self._verifiers[name] for name in self.names()]
        )
        findings: list[Finding] = []
        for verifier in selected:
            findings.extend(verifier.verify(document, active_context))
        return Report.from_findings(findings)


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
        for verifier in _load_plugins(taken=set(registry.names())):
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

    return _load_plugins(taken=set())


def _load_plugins(taken: Set[str]) -> list[Verifier]:
    found = sorted(
        entry_points(group=VERIFIER_ENTRY_POINT_GROUP),
        key=lambda entry_point: entry_point.name,
    )
    used = set(taken)
    verifiers: list[Verifier] = []
    for entry_point in found:
        verifier = _load_plugin(entry_point)
        if verifier.verifier_id in used:
            raise PluginLoadError(
                f"verifier plugin {_describe(entry_point)} uses the id "
                f"{verifier.verifier_id!r}, which is already registered"
            )
        used.add(verifier.verifier_id)
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
