"""Built-in verifier for Lean 4 result assertions.

Lean has no long-lived REPL kernel, so the notebook semantics Provedown assumes
(one accumulating kernel, document order = execution order) are emulated by
re-elaborating the accumulated source prefix at each execution point. That is
quadratic in the number of cells but stays cheap at document scale, which is
the scale Provedown targets.

Scalar claims are evaluated by appending a generated ``main`` entry point to the
prefix and running ``lean --run``. That gives ``toString`` semantics rather than
``#eval``'s ``Repr`` semantics, so a Lean ``String`` renders as ``hi`` and
matches prose rather than as ``"hi"``.

Lean writes elaboration diagnostics to the same stdout stream as the running
program, and warnings (``declaration uses 'sorry'``, for example) are emitted
even on a successful exit. The exit status therefore does not separate a value
from surrounding diagnostics, so the generated entry point brackets the value
with sentinel lines and only the text between them is read back.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from provedown.model import (
    CodeBlock,
    CodeUse,
    Document,
    ResultAssertion,
    SourceLocation,
)
from provedown.report import Finding, Status
from provedown.verifiers import VerificationContext

LEAN_LANGUAGE_NAMES = {"lean", "lean4"}
LEAN_PROOF_LANGUAGE_NAMES = {"lean-proof", "lean-theorem"}
VERIFIER_ID = "lean-results"

#: Axioms every ordinary Lean proof may use. Anything else -- a bare ``axiom``
#: declaration, or ``sorryAx`` from an unfinished proof -- is an unproved
#: assumption the claim silently rests on, so it is reported.
STANDARD_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})
LEAN_TIMEOUT_SECONDS = 300

_ENTRY_POINT = "main"
_VALUE_BEGIN = "<<provedown:begin>>"
_VALUE_END = "<<provedown:end>>"
_STATEMENT_BEGIN = "<<provedown:statement>>"
_AXIOMS_BEGIN = "<<provedown:axioms>>"
_PROOF_END = "<<provedown:proof-end>>"

_DECLARATION_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.'!?]*$")
_AXIOM_LIST_PATTERN = re.compile(r"depends on axioms: \[([^\]]*)\]")
_NO_AXIOMS_PATTERN = re.compile(r"does not depend on any axioms")
_IMPORT_PATTERN = re.compile(r"^import\s+\S+")
_ENTRY_POINT_PATTERN = re.compile(
    r"^\s*(?:@\[[^\]]*\]\s*)*(?:private\s+|protected\s+|unsafe\s+|partial\s+)*"
    r"def\s+main\b",
    re.MULTILINE,
)
_SORRY_PATTERN = re.compile(r"declaration uses 'sorry'")
_TOSTRING_FAILURE_PATTERN = re.compile(
    r"failed to synthesize\s*\n?\s*ToString",
    re.MULTILINE,
)


@dataclass
class LeanResultVerifier:
    """Elaborate Lean cells and verify scalar result spans."""

    verifier_id: str = VERIFIER_ID

    def verify(
        self,
        document: Document,
        context: VerificationContext,
    ) -> Iterable[Finding]:
        if not _has_lean_events(document):
            return []
        if context.sandbox is not None:
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=_document_location(document),
                    message=(
                        "lean-results does not support sandbox mode "
                        f"{context.sandbox!r}"
                    ),
                )
            ]
        runner = _LeanRunner(document=document, context=context)
        return runner.verify()


@dataclass
class _LeanRunner:
    document: Document
    context: VerificationContext
    imports: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)
    prefix_failure: str | None = None

    def verify(self) -> list[Finding]:
        toolchain = _resolve_toolchain(self._execution_cwd())
        if toolchain is None:
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=_document_location(self.document),
                    message=(
                        "lean toolchain not found on PATH; install Lean 4 "
                        "(https://lean-lang.org/install/) to verify lean claims"
                    ),
                )
            ]

        findings: list[Finding] = []
        deferred_names = _deferred_code_names(self.document)
        with tempfile.TemporaryDirectory(prefix="provedown-lean-") as workdir:
            scratch = Path(workdir)
            for event in self.document.events:
                if isinstance(event, CodeBlock):
                    if event.name in deferred_names:
                        continue
                    findings.extend(self._execute_code_block(event, toolchain, scratch))
                elif isinstance(event, CodeUse):
                    findings.extend(self._execute_code_use(event, toolchain, scratch))
                elif isinstance(event, ResultAssertion):
                    finding = self._verify_result(event, toolchain, scratch)
                    if finding is not None:
                        findings.append(finding)
        return findings

    def _execute_code_use(
        self,
        event: CodeUse,
        toolchain: list[str],
        scratch: Path,
    ) -> list[Finding]:
        block = self.document.named_code.get(event.name)
        if block is None:
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=event.location,
                    message=f"unknown code block reference: {event.name}",
                )
            ]
        return self._execute_code_block(
            block,
            toolchain,
            scratch,
            execution_location=event,
        )

    def _execute_code_block(
        self,
        block: CodeBlock,
        toolchain: list[str],
        scratch: Path,
        execution_location: CodeUse | None = None,
    ) -> list[Finding]:
        if not _is_lean(block.language):
            return []
        location = execution_location.location if execution_location else block.location


        imports, body = _split_imports(block.code)
        for statement in imports:
            if statement not in self.imports:
                self.imports.append(statement)
        if body.strip():
            self.segments.append(body)

        source = self._render_source()
        outcome = _run_lean(toolchain, source, scratch, self._execution_cwd())
        if outcome.timed_out:
            self.prefix_failure = "lean elaboration timed out"
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=location,
                    message=(
                        "lean cell timed out after "
                        f"{LEAN_TIMEOUT_SECONDS} seconds"
                    ),
                    evidence={"code": block.code},
                )
            ]
        if outcome.returncode != 0:
            self.prefix_failure = "a preceding lean cell failed to elaborate"
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=location,
                    message=(
                        "lean cell failed to elaborate: "
                        f"{_summarize(outcome.output)}"
                    ),
                    evidence={"code": block.code, "output": outcome.output},
                )
            ]
        if _SORRY_PATTERN.search(outcome.output):
            return [
                Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.FAIL,
                    location=location,
                    message="lean cell contains 'sorry', so its evidence is incomplete",
                    evidence={"code": block.code, "output": outcome.output},
                )
            ]
        return []

    def _verify_result(
        self,
        result: ResultAssertion,
        toolchain: list[str],
        scratch: Path,
    ) -> Finding | None:
        if not _is_lean(result.language):
            return None
        if _is_lean_proof(result.language):
            return self._verify_proof(result, toolchain, scratch)

        expression = result.code
        ref_name = result.referenced_code_name
        if ref_name is not None:
            referenced = self.document.named_code.get(ref_name)
            if referenced is None:
                return Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.ERROR,
                    location=result.location,
                    message=f"unknown result code reference: {ref_name}",
                    expected=result.authored,
                )
            if not _is_lean(referenced.language):
                return Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.SKIP,
                    location=result.location,
                    message=(
                        "lean verifier does not handle referenced language "
                        f"{referenced.language!r}"
                    ),
                    expected=result.authored,
                )
            expression = referenced.code

        if result.compare == "none":
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.SKIP,
                location=result.location,
                message="assertion explicitly marked as not verified",
                expected=result.authored,
                evidence={"code": expression, "compare": result.compare},
            )

        if self.prefix_failure is not None:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=self.prefix_failure,
                expected=result.authored,
                evidence={"code": expression},
            )

        if any(_ENTRY_POINT_PATTERN.search(segment) for segment in self.segments):
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=(
                    f"a lean cell declares '{_ENTRY_POINT}', which collides with the "
                    "entry point provedown generates to evaluate the claim; rename it"
                ),
                expected=result.authored,
                evidence={"code": expression},
            )

        outcome = self._evaluate(expression, toolchain, scratch, renderer="toString")
        if outcome.timed_out:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=f"lean result timed out after {LEAN_TIMEOUT_SECONDS} seconds",
                expected=result.authored,
                evidence={"code": expression},
            )
        if outcome.returncode != 0 and _TOSTRING_FAILURE_PATTERN.search(outcome.output):
            # Repr-only values (for example `deriving Repr` structures) have no
            # ToString instance. Fall back rather than reporting a spurious error.
            outcome = self._evaluate(expression, toolchain, scratch, renderer="repr")
        if outcome.returncode != 0:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=f"lean result failed: {_summarize(outcome.output)}",
                expected=result.authored,
                evidence={"code": expression, "output": outcome.output},
            )

        actual = _extract_value(outcome.output)
        if actual is None:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message="lean result produced no value output",
                expected=result.authored,
                evidence={"code": expression, "output": outcome.output},
            )

        comparison = self.context.comparators.compare(
            result.compare,
            result.authored,
            actual,
            result.attributes,
        )
        return Finding(
            verifier_id=VERIFIER_ID,
            status=comparison.status,
            location=result.location,
            message=comparison.message,
            expected=comparison.expected,
            actual=comparison.actual,
            evidence={"code": expression, "compare": result.compare},
        )

    def _verify_proof(
        self,
        result: ResultAssertion,
        toolchain: list[str],
        scratch: Path,
    ) -> Finding:
        """Check that a named theorem states the authored claim and proves it.

        Three things can go wrong independently, so all three are checked: the
        declaration may not exist, it may rest on unproved assumptions, and its
        statement may have drifted from the claim the document displays.
        """
        name = result.code.strip()
        evidence = {"declaration": name, "compare": result.compare}

        if result.compare == "none":
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.SKIP,
                location=result.location,
                message="assertion explicitly marked as not verified",
                expected=result.authored,
                evidence=evidence,
            )
        if not _DECLARATION_NAME_PATTERN.match(name):
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=(
                    "a lean proof claim must name a single declaration, "
                    f"not {name!r}"
                ),
                expected=result.authored,
                evidence=evidence,
            )
        if self.prefix_failure is not None:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=self.prefix_failure,
                expected=result.authored,
                evidence=evidence,
            )

        entry = "\n".join(
            [
                f'#eval IO.println "{_STATEMENT_BEGIN}"',
                f"#check @{name}",
                f'#eval IO.println "{_AXIOMS_BEGIN}"',
                f"#print axioms {name}",
                f'#eval IO.println "{_PROOF_END}"',
            ]
        )
        outcome = _run_lean(
            toolchain,
            self._render_source(entry),
            scratch,
            self._execution_cwd(),
        )
        if outcome.timed_out:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=f"lean proof timed out after {LEAN_TIMEOUT_SECONDS} seconds",
                expected=result.authored,
                evidence=evidence,
            )
        if outcome.returncode != 0:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=f"lean proof claim failed: {_summarize(outcome.output)}",
                expected=result.authored,
                evidence={**evidence, "output": outcome.output},
            )

        statement = _section(outcome.output, _STATEMENT_BEGIN, _AXIOMS_BEGIN)
        axioms_text = _section(outcome.output, _AXIOMS_BEGIN, _PROOF_END)
        if statement is None or axioms_text is None:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=result.location,
                message=f"could not read the statement of {name!r}",
                expected=result.authored,
                evidence={**evidence, "output": outcome.output},
            )

        statement = _strip_declaration_prefix(statement, name)
        evidence = {**evidence, "statement": statement}

        unproved = _unexpected_axioms(axioms_text, result.attributes)
        if unproved:
            listed = ", ".join(sorted(unproved))
            detail = (
                "an unfinished proof ('sorry')"
                if "sorryAx" in unproved
                else "an unproved assumption"
            )
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.FAIL,
                location=result.location,
                message=(
                    f"{name} rests on {detail}; it depends on [{listed}]"
                ),
                expected=result.authored,
                actual=statement,
                evidence={**evidence, "axioms": axioms_text},
            )

        if _normalize(statement) != _normalize(result.authored):
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.FAIL,
                location=result.location,
                message=(
                    f"the document states a different theorem than {name} proves"
                ),
                expected=result.authored,
                actual=statement,
                evidence=evidence,
            )

        return Finding(
            verifier_id=VERIFIER_ID,
            status=Status.PASS,
            location=result.location,
            message=f"{name} proves the stated claim with no unproved assumptions",
            expected=result.authored,
            actual=statement,
            evidence=evidence,
        )

    def _evaluate(
        self,
        expression: str,
        toolchain: list[str],
        scratch: Path,
        renderer: str,
    ) -> _LeanOutcome:
        entry = "\n".join(
            [
                f"def {_ENTRY_POINT} : IO Unit := do",
                f'  IO.println "{_VALUE_BEGIN}"',
                f"  IO.println ({renderer} ({expression.strip()}))",
                f'  IO.println "{_VALUE_END}"',
            ]
        )
        source = self._render_source(entry)
        return _run_lean(
            toolchain,
            source,
            scratch,
            self._execution_cwd(),
            run=True,
        )

    def _render_source(self, entry: str | None = None) -> str:
        parts = list(self.imports)
        parts.extend(self.segments)
        if entry is not None:
            parts.append(entry)
        return "\n\n".join(part.strip("\n") for part in parts if part.strip()) + "\n"

    def _execution_cwd(self) -> Path:
        if self.context.cwd is not None:
            return self.context.cwd
        if self.document.path is not None:
            return self.document.path.parent
        return Path.cwd()


@dataclass(frozen=True)
class _LeanOutcome:
    returncode: int
    output: str
    timed_out: bool = False


def _run_lean(
    toolchain: list[str],
    source: str,
    scratch: Path,
    cwd: Path,
    run: bool = False,
) -> _LeanOutcome:
    source_path = scratch / "provedown_cell.lean"
    source_path.write_text(source, encoding="utf-8")
    command = list(toolchain)
    if run:
        command.append("--run")
    command.append(str(source_path))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=LEAN_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _LeanOutcome(returncode=-1, output="", timed_out=True)
    output = completed.stdout
    if completed.returncode != 0 and completed.stderr:
        output = f"{output}{completed.stderr}"
    return _LeanOutcome(returncode=completed.returncode, output=output)


def _resolve_toolchain(cwd: Path) -> list[str] | None:
    """Prefer ``lake env lean`` inside a Lake project so imports resolve."""
    if _has_lakefile(cwd) and shutil.which("lake") is not None:
        return ["lake", "env", "lean"]
    if shutil.which("lean") is not None:
        return ["lean"]
    return None


def _has_lakefile(cwd: Path) -> bool:
    return (cwd / "lakefile.lean").exists() or (cwd / "lakefile.toml").exists()


def _split_imports(code: str) -> tuple[list[str], str]:
    """Hoist ``import`` lines, which Lean only accepts at the top of a file."""
    imports: list[str] = []
    body: list[str] = []
    for line in code.splitlines():
        if _IMPORT_PATTERN.match(line):
            imports.append(line.strip())
        else:
            body.append(line)
    return imports, "\n".join(body)


def _extract_value(output: str) -> str | None:
    """Read the value bracketed by sentinel lines, ignoring Lean diagnostics."""
    lines = output.splitlines()
    try:
        start = lines.index(_VALUE_BEGIN)
        end = lines.index(_VALUE_END, start + 1)
    except ValueError:
        return None
    return "\n".join(lines[start + 1 : end])


def _summarize(output: str) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return "no diagnostic output"
    summary = lines[0]
    if len(lines) > 1:
        summary = f"{summary} ({len(lines) - 1} more line(s))"
    return summary


def _section(output: str, begin: str, end: str) -> str | None:
    """Read the text bracketed by two sentinel lines."""
    lines = output.splitlines()
    try:
        start = lines.index(begin)
        stop = lines.index(end, start + 1)
    except ValueError:
        return None
    return "\n".join(lines[start + 1 : stop])


def _strip_declaration_prefix(statement: str, name: str) -> str:
    """``#check @foo`` prints ``foo : <statement>``; keep the statement."""
    prefix = f"{name} :"
    stripped = statement.strip()
    if stripped.startswith(prefix):
        return stripped[len(prefix) :].strip()
    return stripped


def _unexpected_axioms(
    axioms_text: str,
    attributes: Mapping[str, str],
) -> set[str]:
    """Return the axioms a claim rests on beyond the permitted set."""
    if _NO_AXIOMS_PATTERN.search(axioms_text):
        return set()
    match = _AXIOM_LIST_PATTERN.search(axioms_text)
    if match is None:
        return set()
    found = {item.strip() for item in match.group(1).split(",") if item.strip()}
    declared = attributes.get("axioms") or attributes.get("data-axioms") or ""
    permitted = STANDARD_AXIOMS | {
        item.strip() for item in declared.split(",") if item.strip()
    }
    return found - permitted


def _normalize(text: str) -> str:
    """Compare statements up to the line wrapping the pretty-printer chooses."""
    return " ".join(text.split())


def _is_lean(language: str) -> bool:
    name = language.strip().lower()
    return name in LEAN_LANGUAGE_NAMES or name in LEAN_PROOF_LANGUAGE_NAMES


def _is_lean_proof(language: str) -> bool:
    return language.strip().lower() in LEAN_PROOF_LANGUAGE_NAMES


def _has_lean_events(document: Document) -> bool:
    return any(
        isinstance(event, (CodeBlock, CodeUse, ResultAssertion))
        and _is_lean(event.language)
        for event in document.events
    )


def _deferred_code_names(document: Document) -> set[str]:
    names: set[str] = set()
    for event in document.events:
        if isinstance(event, CodeUse):
            names.add(event.name)
        elif isinstance(event, ResultAssertion):
            ref_name = event.referenced_code_name
            if ref_name is not None:
                names.add(ref_name)
    return names


def _document_location(document: Document) -> SourceLocation:
    return SourceLocation(path=document.path, line=1, column=1)
