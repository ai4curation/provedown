"""Static lints for fragile Provedown documents."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from provedown.inspection import inspect_document
from provedown.model import CodeBlock, Document, ResultAssertion, SourceLocation
from provedown.parser import parse_file

LintLevel = Literal["error", "warning"]

# Minimum line distance between a global's first definition and a later,
# in-place mutation of it before the mutation is treated as "widely separated"
# document locations. Adjacent definition-then-mutation is a common, readable
# idiom; a mutation many lines away is the spooky action the lint targets.
MUTATION_SEPARATION_LINES = 10

# Methods that mutate their receiver in place. A call to one of these on a
# global object is a hidden state change even though nothing is reassigned.
_MUTATING_METHODS = frozenset(
    {
        "append",
        "appendleft",
        "extend",
        "extendleft",
        "insert",
        "remove",
        "pop",
        "popitem",
        "clear",
        "update",
        "add",
        "discard",
        "sort",
        "reverse",
        "setdefault",
        "difference_update",
        "intersection_update",
        "symmetric_difference_update",
        "__setitem__",
        "__delitem__",
    }
)


@dataclass(frozen=True)
class LintFinding:
    """One lint finding tied to a document location."""

    level: LintLevel
    code: str
    location: SourceLocation
    message: str
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "level": self.level,
            "code": self.code,
            "location": self.location.display(),
            "message": self.message,
        }
        if self.target is not None:
            payload["target"] = self.target
        return payload


@dataclass(frozen=True)
class LintReport:
    """Aggregate lint report for one document."""

    path: Path | None
    findings: list[LintFinding]

    @property
    def ok(self) -> bool:
        return not any(finding.level == "error" for finding in self.findings)

    def summary(self) -> dict[str, int]:
        return {
            "errors": sum(1 for finding in self.findings if finding.level == "error"),
            "warnings": sum(
                1 for finding in self.findings if finding.level == "warning"
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path is not None else None,
            "ok": self.ok,
            "summary": self.summary(),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def lint_file(path: Path) -> LintReport:
    """Parse and lint one Provedown document from disk."""

    return lint_document(parse_file(path))


def lint_document(document: Document) -> LintReport:
    """Lint a parsed document without executing code."""

    findings: list[LintFinding] = []
    _add_relationship_lints(document, findings)
    _add_result_policy_lints(document, findings)
    _add_python_fragility_lints(document, findings)
    _add_mutation_lints(document, findings)
    return LintReport(path=document.path, findings=findings)


def _add_relationship_lints(
    document: Document,
    findings: list[LintFinding],
) -> None:
    for issue in inspect_document(document).issues:
        if issue.kind == "parser-diagnostic":
            findings.append(
                LintFinding(
                    level="error",
                    code="parser-diagnostic",
                    location=issue.location,
                    message=issue.message,
                    target=issue.target,
                )
            )
        elif issue.kind in {"unresolved-code-use", "unresolved-result-reference"}:
            findings.append(
                LintFinding(
                    level="error",
                    code=issue.kind,
                    location=issue.location,
                    message=issue.message,
                    target=issue.target,
                )
            )
        elif issue.kind == "unused-named-code":
            findings.append(
                LintFinding(
                    level="warning",
                    code=issue.kind,
                    location=issue.location,
                    message=issue.message,
                    target=issue.target,
                )
            )


def _add_result_policy_lints(
    document: Document,
    findings: list[LintFinding],
) -> None:
    none_results: list[ResultAssertion] = []
    for event in document.events:
        if not isinstance(event, ResultAssertion) or event.compare != "none":
            continue
        none_results.append(event)
        if not _has_justification(event):
            findings.append(
                LintFinding(
                    level="warning",
                    code="unjustified-none-compare",
                    location=event.location,
                    message=(
                        'result uses data-compare="none" without data-reason '
                        "or data-justification"
                    ),
                    target=event.authored,
                )
            )

    if len(none_results) > 3:
        findings.append(
            LintFinding(
                level="warning",
                code="excessive-none-compare",
                location=none_results[0].location,
                message=(
                    f"document has {len(none_results)} unverified result "
                    "assertions"
                ),
            )
        )


def _add_python_fragility_lints(
    document: Document,
    findings: list[LintFinding],
) -> None:
    for event in document.events:
        if isinstance(event, CodeBlock) and _is_python(event.language):
            _lint_python_source(
                event.code,
                mode="exec",
                location=event.location,
                findings=findings,
                skip_random=_has_seed(event),
            )
        elif (
            isinstance(event, ResultAssertion)
            and _is_python(event.language)
            and event.referenced_code_name is None
            and event.compare != "none"
        ):
            _lint_python_source(
                event.code,
                mode="eval",
                location=event.location,
                findings=findings,
                skip_random=_has_seed(event),
            )


def _add_mutation_lints(
    document: Document,
    findings: list[LintFinding],
) -> None:
    """Flag in-place mutation of a global defined in an earlier, distant block.

    Python cells share one namespace, so a list or dict created in one block and
    mutated many lines later is hidden state: reading the second block in
    isolation does not reveal that its behaviour depends on, and changes, an
    object from elsewhere in the document. Reordering or re-running then produces
    different results, which is exactly the fragility verification should avoid.
    """

    definitions: dict[str, SourceLocation] = {}
    for event in document.events:
        if not isinstance(event, CodeBlock) or not _is_python(event.language):
            continue
        try:
            tree = ast.parse(event.code, mode="exec")
        except SyntaxError:
            # Syntax errors are reported separately by the fragility lints.
            continue

        rebound = _module_scope_bindings(tree.body)
        for name in sorted(_module_scope_mutations(tree.body)):
            def_location = definitions.get(name)
            if def_location is None or name in rebound:
                # First seen here, or this block rebinds a fresh object it owns.
                continue
            distance = abs(event.location.line - def_location.line)
            if distance < MUTATION_SEPARATION_LINES:
                continue
            findings.append(
                LintFinding(
                    level="warning",
                    code="distant-global-mutation",
                    location=event.location,
                    message=(
                        f"mutates global {name!r} defined {distance} lines "
                        f"earlier at {def_location.display()}; distant mutation "
                        "creates hidden state across the document"
                    ),
                    target=name,
                )
            )

        for name in rebound:
            definitions.setdefault(name, event.location)


def _module_scope_statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements executed in module scope, skipping nested function/class bodies.

    Mutations and bindings inside a ``def`` or ``class`` only take effect when
    that scope runs, so they are not module-level state changes for this lint.
    Control-flow bodies (``if``/``for``/``while``/``with``/``try``/``match``) are
    followed because their statements do run at module scope.
    """

    collected: list[ast.stmt] = []
    for statement in body:
        collected.append(statement)
        if isinstance(
            statement,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue
        for child in _child_statement_bodies(statement):
            collected.extend(_module_scope_statements(child))
    return collected


def _child_statement_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    bodies: list[list[ast.stmt]] = []
    for field_name in ("body", "orelse", "finalbody"):
        child = getattr(statement, field_name, None)
        if isinstance(child, list):
            bodies.append(child)
    for handler in getattr(statement, "handlers", []):
        bodies.append(handler.body)
    for case in getattr(statement, "cases", []):
        bodies.append(case.body)
    return bodies


def _module_scope_bindings(body: list[ast.stmt]) -> set[str]:
    """Names freshly bound to a new object in module scope.

    Augmented assignment (``x += 1``) is deliberately excluded: it mutates an
    existing binding rather than creating a new object.
    """

    names: set[str] = set()
    for statement in _module_scope_statements(body):
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                names |= _target_names(target)
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name) and statement.value is not None:
                names.add(statement.target.id)
        elif isinstance(
            statement,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            names.add(statement.name)
        elif isinstance(statement, (ast.Import, ast.ImportFrom)):
            for alias in statement.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(statement, (ast.For, ast.AsyncFor)):
            names |= _target_names(statement.target)
        elif isinstance(statement, (ast.With, ast.AsyncWith)):
            for item in statement.items:
                if item.optional_vars is not None:
                    names |= _target_names(item.optional_vars)
    return names


def _module_scope_mutations(body: list[ast.stmt]) -> set[str]:
    """Root names of objects mutated in place in module scope."""

    names: set[str] = set()
    for statement in _module_scope_statements(body):
        if isinstance(statement, ast.AugAssign):
            _add_root(statement.target, names)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, (ast.Subscript, ast.Attribute)):
                    _add_root(target, names)
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, (ast.Subscript, ast.Attribute)):
                _add_root(statement.target, names)
        elif isinstance(statement, ast.Delete):
            for target in statement.targets:
                if isinstance(target, (ast.Subscript, ast.Attribute)):
                    _add_root(target, names)
        elif isinstance(statement, ast.Expr) and isinstance(
            statement.value, ast.Call
        ):
            func = statement.value.func
            if isinstance(func, ast.Attribute) and func.attr in _MUTATING_METHODS:
                _add_root(func.value, names)
    return names


def _target_names(node: ast.expr) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Starred):
        return _target_names(node.value)
    if isinstance(node, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in node.elts:
            names |= _target_names(element)
        return names
    return set()


def _add_root(node: ast.expr, names: set[str]) -> None:
    root = _root_name(node)
    if root is not None:
        names.add(root)


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, (ast.Subscript, ast.Attribute)):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def _lint_python_source(
    source: str,
    mode: Literal["exec", "eval"],
    location: SourceLocation,
    findings: list[LintFinding],
    *,
    skip_random: bool,
) -> None:
    try:
        tree = ast.parse(source, mode=mode)
    except SyntaxError as exc:
        findings.append(
            LintFinding(
                level="error",
                code="python-syntax-error",
                location=location,
                message=f"python syntax error: {exc.msg}",
            )
        )
        return

    visitor = _FragilityVisitor(skip_random=skip_random)
    visitor.visit(tree)
    for message in visitor.messages:
        findings.append(
            LintFinding(
                level="warning",
                code="fragile-python",
                location=location,
                message=message,
            )
        )


class _FragilityVisitor(ast.NodeVisitor):
    def __init__(self, *, skip_random: bool) -> None:
        self.skip_random = skip_random
        self.messages: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = _qualified_name(node.func)
        if name is not None:
            self._check_call(name)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        name = _qualified_name(node.value)
        if name in {"os.environ"}:
            self._add_once("reads environment variables through os.environ")
        self.generic_visit(node)

    def _check_call(self, name: str) -> None:
        if not self.skip_random and _is_random_call(name):
            self._add_once(
                "uses random values without an explicit seed attribute nearby"
            )
        if name in {"time.time", "time.monotonic", "time.perf_counter"}:
            self._add_once("uses wall-clock or process-clock time")
        if name in {"datetime.datetime.now", "datetime.datetime.utcnow"}:
            self._add_once("uses current datetime")
        if name in {"datetime.date.today"}:
            self._add_once("uses current date")
        if name in {"requests.get", "requests.post", "urllib.request.urlopen"}:
            self._add_once("uses a network call during verification")

    def _add_once(self, message: str) -> None:
        if message not in self.messages:
            self.messages.append(message)


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        if parent is None:
            return node.attr
        return f"{parent}.{node.attr}"
    return None


def _is_random_call(name: str) -> bool:
    return name in {
        "random",
        "randint",
        "randrange",
        "uniform",
        "choice",
        "choices",
        "shuffle",
        "sample",
        "random.random",
        "random.randint",
        "random.randrange",
        "random.uniform",
        "random.choice",
        "random.choices",
        "random.shuffle",
        "random.sample",
        "np.random.random",
        "np.random.randint",
        "np.random.choice",
        "numpy.random.random",
        "numpy.random.randint",
        "numpy.random.choice",
    }


def _has_justification(event: ResultAssertion) -> bool:
    return bool(
        event.attributes.get("data-reason", "").strip()
        or event.attributes.get("data-justification", "").strip()
    )


def _has_seed(event: CodeBlock | ResultAssertion) -> bool:
    return bool(
        event.attributes.get("seed", "").strip()
        or event.attributes.get("data-seed", "").strip()
    )


def _is_python(language: str) -> bool:
    return language.strip().lower() in {"python", "py"}
