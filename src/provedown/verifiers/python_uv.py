"""uv execution adapter for the built-in Python result verifier."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from provedown.model import (
    CodeBlock,
    CodeUse,
    Document,
    ResultAssertion,
    SourceLocation,
)
from provedown.report import Finding, Status
from provedown.verifiers import VerificationContext
from provedown.verifiers.python import (
    VERIFIER_ID,
    _deferred_code_names,
    _document_location,
    _is_python,
    _seed_value,
)


@dataclass(frozen=True)
class _UVAction:
    kind: Literal["exec", "eval"]
    code: str
    location: SourceLocation
    result: ResultAssertion | None = None
    seed: int | None = None


@dataclass
class UVPythonRunner:
    """Execute a Python verification plan in a fresh uv environment."""

    document: Document
    context: VerificationContext

    def verify(self) -> list[Finding]:
        plan = self._build_plan()
        actions = [item for item in plan if isinstance(item, _UVAction)]
        if not actions:
            return [item for item in plan if isinstance(item, Finding)]

        outcomes = self._run_worker(actions)
        if isinstance(outcomes, Finding):
            early_findings = [item for item in plan if isinstance(item, Finding)]
            early_findings.append(outcomes)
            return early_findings

        findings: list[Finding] = []
        outcome_index = 0
        for item in plan:
            if isinstance(item, Finding):
                findings.append(item)
                continue
            outcome = outcomes[outcome_index]
            outcome_index += 1
            finding = self._outcome_finding(item, outcome)
            if finding is not None:
                findings.append(finding)
        return findings

    def _build_plan(self) -> list[Finding | _UVAction]:
        plan: list[Finding | _UVAction] = []
        deferred_names = _deferred_code_names(self.document)
        for event in self.document.events:
            if isinstance(event, CodeBlock):
                if event.name not in deferred_names and _is_python(event.language):
                    plan.append(
                        _UVAction(
                            kind="exec",
                            code=event.code,
                            location=event.location,
                        )
                    )
            elif isinstance(event, CodeUse):
                item = self._plan_code_use(event)
                if item is not None:
                    plan.append(item)
            elif isinstance(event, ResultAssertion):
                item = self._plan_result(event)
                if item is not None:
                    plan.append(item)
        return plan

    def _plan_code_use(self, event: CodeUse) -> Finding | _UVAction | None:
        block = self.document.named_code.get(event.name)
        if block is None:
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=event.location,
                message=f"unknown code block reference: {event.name}",
            )
        if not _is_python(block.language):
            return None
        return _UVAction(
            kind="exec",
            code=block.code,
            location=event.location,
        )

    def _plan_result(self, result: ResultAssertion) -> Finding | _UVAction | None:
        if not _is_python(result.language):
            return None

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
            if not _is_python(referenced.language):
                return Finding(
                    verifier_id=VERIFIER_ID,
                    status=Status.SKIP,
                    location=result.location,
                    message=(
                        "python verifier does not handle referenced language "
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
                evidence={
                    "code": expression,
                    "compare": result.compare,
                    "sandbox": "uv",
                },
            )

        return _UVAction(
            kind="eval",
            code=expression,
            location=result.location,
            result=result,
            seed=_seed_value(result.attributes),
        )

    def _run_worker(self, actions: list[_UVAction]) -> list[dict[str, Any]] | Finding:
        command = self._sandbox_command()
        if isinstance(command, Finding):
            return command

        payload = {
            "version": 1,
            "document_path": (
                str(self.document.path) if self.document.path is not None else None
            ),
            "actions": [
                {
                    "kind": action.kind,
                    "code": action.code,
                    "filename": action.location.display(),
                    "seed": action.seed,
                }
                for action in actions
            ],
        }
        environment = os.environ.copy()
        environment.pop("VIRTUAL_ENV", None)
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(payload),
                check=False,
                capture_output=True,
                text=True,
                cwd=self._execution_cwd(),
                env=environment,
            )
        except FileNotFoundError:
            return self._sandbox_error(
                "uv sandbox setup failed: uv executable was not found"
            )

        if completed.returncode != 0:
            detail = _last_output_line(completed.stderr, completed.stdout)
            message = f"uv sandbox setup failed with exit code {completed.returncode}"
            if detail:
                message += f": {detail}"
            return self._sandbox_error(
                message,
                evidence={"sandbox": "uv", "stderr": completed.stderr.strip()},
            )

        try:
            response = json.loads(completed.stdout)
            outcomes = response["results"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return self._sandbox_error(
                "uv sandbox worker returned an invalid response",
                evidence={
                    "sandbox": "uv",
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
            )
        if not isinstance(outcomes, list) or len(outcomes) != len(actions):
            return self._sandbox_error(
                "uv sandbox worker returned the wrong number of results",
                evidence={"sandbox": "uv"},
            )
        if not all(isinstance(outcome, dict) for outcome in outcomes):
            return self._sandbox_error(
                "uv sandbox worker returned malformed results",
                evidence={"sandbox": "uv"},
            )
        return outcomes

    def _sandbox_command(self) -> list[str] | Finding:
        environment = self.document.provedown.environments.get("python", {})
        dependencies = environment.get("dependencies", [])
        if not isinstance(dependencies, (list, tuple)) or not all(
            isinstance(item, str) and item.strip() for item in dependencies
        ):
            return self._sandbox_error(
                "python environment dependencies must be a list of non-empty strings"
            )

        requires_python = environment.get("requires-python")
        if requires_python is not None and (
            not isinstance(requires_python, str) or not requires_python.strip()
        ):
            return self._sandbox_error(
                "python environment requires-python must be a non-empty string"
            )

        command = ["uv", "run", "--isolated", "--no-progress", "--color", "never"]
        project = self._project_directory()
        if isinstance(project, Finding):
            return project
        if project is None:
            command.append("--no-project")
        else:
            command.extend(["--project", str(project)])
        if isinstance(requires_python, str):
            command.extend(["--python", requires_python.strip()])
        for dependency in dependencies:
            command.extend(["--with", dependency.strip()])
        command.append(str(Path(__file__).with_name("_python_uv_worker.py")))
        return command

    def _project_directory(self) -> Path | Finding | None:
        configured = self.document.provedown.pyproject
        if configured is None:
            return None
        path = (self._execution_cwd() / configured).resolve()
        if path.is_dir() and (path / "pyproject.toml").is_file():
            return path
        if path.is_file() and path.name == "pyproject.toml":
            return path.parent
        return self._sandbox_error(
            f"configured pyproject was not found: {path}",
            evidence={"sandbox": "uv", "pyproject": str(path)},
        )

    def _outcome_finding(
        self,
        action: _UVAction,
        outcome: dict[str, Any],
    ) -> Finding | None:
        evidence = {
            "code": action.code,
            "sandbox": "uv",
        }
        stdout = outcome.get("stdout")
        stderr = outcome.get("stderr")
        if stdout:
            evidence["stdout"] = str(stdout)
        if stderr:
            evidence["stderr"] = str(stderr)

        status = outcome.get("status")
        if status == "error":
            exception_type = str(outcome.get("exception_type", "Exception"))
            message = str(outcome.get("message", ""))
            label = "cell" if action.kind == "exec" else "result"
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=action.location,
                message=f"python {label} raised {exception_type}: {message}",
                expected=(
                    action.result.authored if action.result is not None else None
                ),
                evidence=evidence,
            )
        if status != "ok":
            return Finding(
                verifier_id=VERIFIER_ID,
                status=Status.ERROR,
                location=action.location,
                message="uv sandbox worker returned a malformed action result",
                expected=(
                    action.result.authored if action.result is not None else None
                ),
                evidence=evidence,
            )
        if action.result is None:
            return None

        actual = str(outcome.get("actual", ""))
        comparison = self.context.comparators.compare(
            action.result.compare,
            action.result.authored,
            actual,
            action.result.attributes,
        )
        evidence["compare"] = action.result.compare
        return Finding(
            verifier_id=VERIFIER_ID,
            status=comparison.status,
            location=action.location,
            message=comparison.message,
            expected=comparison.expected,
            actual=comparison.actual,
            evidence=evidence,
        )

    def _sandbox_error(
        self,
        message: str,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> Finding:
        return Finding(
            verifier_id=VERIFIER_ID,
            status=Status.ERROR,
            location=_document_location(self.document),
            message=message,
            evidence=evidence or {"sandbox": "uv"},
        )

    def _execution_cwd(self) -> Path:
        if self.context.cwd is not None:
            return self.context.cwd
        if self.document.path is not None:
            return self.document.path.parent
        return Path.cwd()


def _last_output_line(*streams: str) -> str:
    for stream in streams:
        lines = [line.strip() for line in stream.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return ""
