"""Pure-stdlib worker used by the uv Python sandbox adapter."""

from __future__ import annotations

import ast
import contextlib
import io
import json
import random
import sys
from typing import Any


def main() -> int:
    payload = json.load(sys.stdin)
    namespace: dict[str, Any] = {"__name__": "__provedown__"}
    document_path = payload.get("document_path")
    if document_path is not None:
        namespace["__file__"] = str(document_path)

    results = [_execute(action, namespace) for action in payload["actions"]]
    json.dump({"version": 1, "results": results}, sys.stdout)
    return 0


def _execute(action: dict[str, Any], namespace: dict[str, Any]) -> dict[str, Any]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            if action["kind"] == "exec":
                code = compile(action["code"], action["filename"], "exec")
                exec(code, namespace)
                actual = None
            elif action["kind"] == "eval":
                _seed_random_generators(action.get("seed"), namespace)
                parsed = ast.parse(action["code"], mode="eval")
                code = compile(parsed, action["filename"], "eval")
                actual = _stringify(eval(code, namespace))
            else:
                raise ValueError(f"unknown sandbox action: {action['kind']}")
    except BaseException as exc:
        return {
            "status": "error",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }

    result: dict[str, Any] = {
        "status": "ok",
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }
    if action["kind"] == "eval":
        result["actual"] = actual
    return result


def _seed_random_generators(seed: object, namespace: dict[str, Any]) -> None:
    if seed is None:
        return
    if not isinstance(seed, (int, float, str, bytes, bytearray)):
        raise TypeError("seed must be a supported random seed value")
    random.seed(seed)
    numpy = namespace.get("np")
    if numpy is not None and hasattr(numpy, "random"):
        numpy.random.seed(seed)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
