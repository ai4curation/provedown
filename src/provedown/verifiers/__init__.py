"""Verifier plugin interfaces and default registry."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
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
    """

    from provedown.verifiers.python import PythonResultVerifier
    from provedown.verifiers.sql import SQLResultVerifier

    registry = VerifierRegistry()
    registry.register(PythonResultVerifier())
    registry.register(SQLResultVerifier())
    if plugins:
        for verifier in load_plugin_verifiers():
            if verifier.verifier_id in registry.names():
                raise PluginLoadError(
                    f"verifier plugin {type(verifier).__qualname__} uses the id "
                    f"{verifier.verifier_id!r}, which is already registered"
                )
            registry.register(verifier)
    return registry


def load_plugin_verifiers() -> list[Verifier]:
    """Instantiate the verifiers advertised in the ``provedown.verifiers`` group.

    Entry points are loaded in name order. A plugin that cannot be imported or
    constructed raises ``PluginLoadError`` naming the entry point and the
    distribution that provides it, so a broken install is easy to trace.
    """

    found = sorted(
        entry_points(group=VERIFIER_ENTRY_POINT_GROUP),
        key=lambda entry_point: entry_point.name,
    )
    return [_load_plugin(entry_point) for entry_point in found]


def _load_plugin(entry_point: EntryPoint) -> Verifier:
    distribution = entry_point.dist.name if entry_point.dist is not None else None
    origin = f" from {distribution}" if distribution else ""
    try:
        factory = entry_point.load()
        verifier: Verifier = factory()
    except Exception as exc:  # Plugin code is outside Provedown's control.
        raise PluginLoadError(
            f"cannot load verifier plugin {entry_point.name!r}{origin} "
            f"({entry_point.value}): {exc}"
        ) from exc
    return verifier
