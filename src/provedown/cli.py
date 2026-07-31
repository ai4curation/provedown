"""Command line interface for Provedown."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from provedown.inspection import InspectionEvent, InspectionReport, inspect_file
from provedown.linting import LintReport, lint_file
from provedown.report import Finding, Report, Status
from provedown.runner import verify_file
from provedown.verifiers import default_registry


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "verify":
        return _verify(args)
    if args.command == "inspect":
        return _inspect(args)
    if args.command == "lint":
        return _lint(args)
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
    verify.add_argument(
        "--sandbox",
        choices=("uv",),
        help="verify Python in an isolated uv environment (prototype)",
    )

    inspect = subparsers.add_parser(
        "inspect",
        help="inspect code and result relationships without executing code",
    )
    inspect.add_argument("paths", nargs="+", type=Path)
    inspect.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format",
    )

    lint = subparsers.add_parser(
        "lint",
        help="lint Provedown documents without executing code",
    )
    lint.add_argument("paths", nargs="+", type=Path)
    lint.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format",
    )

    subparsers.add_parser("list-verifiers", help="list available verifier ids")
    return parser


def _verify(args: argparse.Namespace) -> int:
    verifier_ids = args.verifiers
    if (
        args.sandbox is not None
        and verifier_ids is not None
        and set(verifier_ids) != {"python-results"}
    ):
        print(
            "provedown verify: --sandbox uv currently supports only "
            "--verifier python-results",
            file=sys.stderr,
        )
        return 2

    reports: list[Report] = []
    for path in args.paths:
        reports.append(
            verify_file(
                path,
                verifier_ids=verifier_ids,
                sandbox=args.sandbox,
            )
        )

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


def _inspect(args: argparse.Namespace) -> int:
    reports = [inspect_file(path) for path in args.paths]

    if args.format == "json":
        payload = {
            "ok": all(report.ok for report in reports),
            "reports": [report.to_dict() for report in reports],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_inspection(reports)

    return 0 if all(report.ok for report in reports) else 1


def _lint(args: argparse.Namespace) -> int:
    reports = [lint_file(path) for path in args.paths]

    if args.format == "json":
        payload = {
            "ok": all(report.ok for report in reports),
            "reports": [report.to_dict() for report in reports],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_lint(reports)

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


def _print_inspection(reports: Sequence[InspectionReport]) -> None:
    for report in reports:
        summary = report.summary()
        path = report.path if report.path is not None else "<string>"
        print(f"{path}: {'ok' if report.ok else 'issues'}")
        print(
            "  "
            f"events={summary['events']}, "
            f"errors={summary['errors']}, "
            f"warnings={summary['warnings']}"
        )
        for event in report.events:
            print(_format_inspection_event(event))
        for issue in report.issues:
            target = f" target={issue.target!r}" if issue.target is not None else ""
            print(
                f"  [{issue.level}] {issue.kind} "
                f"{issue.location.display()}: {issue.message}{target}"
            )


def _format_inspection_event(event: InspectionEvent) -> str:
    rendered = f"  [{event.index}] {event.kind} {event.location.display()}"
    name = event.name
    if name is not None:
        rendered += f" name={name!r}"
    reference = event.reference
    if reference is not None and reference != name:
        rendered += f" reference={reference!r}"
    compare = event.compare
    if compare is not None:
        rendered += f" compare={compare!r}"
    authored = event.authored
    if authored is not None:
        rendered += f" authored={authored!r}"
    execution = event.execution
    if execution is not None:
        rendered += f" execution={execution!r}"
    target_location = event.target_location
    if target_location is not None:
        rendered += f" target={target_location.display()}"
    return rendered


def _print_lint(reports: Sequence[LintReport]) -> None:
    for report in reports:
        summary = report.summary()
        path = report.path if report.path is not None else "<string>"
        print(f"{path}: {'ok' if report.ok else 'issues'}")
        print(f"  errors={summary['errors']}, warnings={summary['warnings']}")
        for finding in report.findings:
            target = f" target={finding.target!r}" if finding.target is not None else ""
            print(
                f"  [{finding.level}] {finding.code} "
                f"{finding.location.display()}: {finding.message}{target}"
            )


if __name__ == "__main__":
    sys.exit(main())
