"""Command line interface for Provedown."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from provedown.report import Finding, Report, Status
from provedown.runner import verify_file
from provedown.verifiers import default_registry


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "verify":
        return _verify(args)
    if args.command == "list-verifiers":
        registry = default_registry()
        for name in registry.names():
            print(name)
        return 0

    parser.error("unknown command")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="provedown")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="verify Provedown documents")
    verify.add_argument("paths", nargs="+", type=Path)
    verify.add_argument(
        "--verifier",
        action="append",
        dest="verifiers",
        help="verifier id to run; may be passed more than once",
    )
    verify.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format",
    )

    subparsers.add_parser("list-verifiers", help="list available verifier ids")
    return parser


def _verify(args: argparse.Namespace) -> int:
    reports: list[Report] = []
    for path in args.paths:
        reports.append(verify_file(path, verifier_ids=args.verifiers))

    if args.format == "json":
        payload = {
            "ok": all(report.ok for report in reports),
            "reports": [
                {
                    "path": str(path),
                    **report.to_dict(),
                }
                for path, report in zip(args.paths, reports, strict=False)
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text(args.paths, reports)

    return 0 if all(report.ok for report in reports) else 1


def _print_text(paths: Sequence[Path], reports: Sequence[Report]) -> None:
    for path, report in zip(paths, reports, strict=False):
        print(f"{path}: {'ok' if report.ok else 'failed'}")
        summary = report.summary()
        print(
            "  "
            + ", ".join(f"{status.value}={summary[status.value]}" for status in Status)
        )
        for finding in report.findings:
            print(_format_finding(finding))


def _format_finding(finding: Finding) -> str:
    rendered = (
        f"  [{finding.status.value}] {finding.verifier_id} "
        f"{finding.location.display()}: {finding.message}"
    )
    if finding.expected is not None:
        rendered += f" expected={finding.expected!r}"
    if finding.actual is not None:
        rendered += f" actual={finding.actual!r}"
    return rendered


if __name__ == "__main__":
    sys.exit(main())
