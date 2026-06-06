"""Comparison policies for authored result assertions."""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from provedown.report import Status


@dataclass(frozen=True)
class ComparisonResult:
    """Result of comparing an authored scalar with a computed value."""

    status: Status
    message: str
    expected: str
    actual: str


Comparator = Callable[[str, Any, Mapping[str, str]], ComparisonResult]


class ComparatorRegistry:
    """Registry for auditable comparison policies.

    External verifiers can ignore this entirely. Python-style scalar verifiers
    can reuse it and register additional policies.
    """

    def __init__(self) -> None:
        self._comparators: dict[str, Comparator] = {}

    def register(self, name: str, comparator: Comparator) -> None:
        self._comparators[name] = comparator

    def compare(
        self,
        name: str,
        authored: str,
        actual: Any,
        attributes: Mapping[str, str],
    ) -> ComparisonResult:
        comparator = self._comparators.get(name)
        if comparator is None:
            return ComparisonResult(
                status=Status.ERROR,
                message=f"unknown comparison policy: {name}",
                expected=authored,
                actual=stringify(actual),
            )
        return comparator(authored, actual, attributes)


def stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def default_comparators() -> ComparatorRegistry:
    registry = ComparatorRegistry()
    registry.register("exact", exact_compare)
    registry.register("numeric", numeric_compare)
    registry.register("tol", tolerance_compare)
    registry.register("set", set_compare)
    registry.register("seed", exact_compare)
    registry.register("none", none_compare)
    return registry


def exact_compare(
    authored: str,
    actual: Any,
    attributes: Mapping[str, str],
) -> ComparisonResult:
    del attributes
    actual_text = stringify(actual)
    if authored == actual_text:
        return ComparisonResult(
            status=Status.PASS,
            message="value matches exactly",
            expected=authored,
            actual=actual_text,
        )
    return ComparisonResult(
        status=Status.FAIL,
        message="value differs",
        expected=authored,
        actual=actual_text,
    )


def numeric_compare(
    authored: str,
    actual: Any,
    attributes: Mapping[str, str],
) -> ComparisonResult:
    del attributes
    authored_number = _to_decimal(authored)
    actual_text = stringify(actual)
    actual_number = _to_decimal(actual_text)
    if authored_number is None or actual_number is None:
        return ComparisonResult(
            status=Status.ERROR,
            message="numeric comparison requires numeric authored and actual values",
            expected=authored,
            actual=actual_text,
        )
    if authored_number == actual_number:
        return ComparisonResult(
            status=Status.PASS,
            message="numeric values match",
            expected=authored,
            actual=actual_text,
        )
    return ComparisonResult(
        status=Status.FAIL,
        message="numeric values differ",
        expected=authored,
        actual=actual_text,
    )


def tolerance_compare(
    authored: str,
    actual: Any,
    attributes: Mapping[str, str],
) -> ComparisonResult:
    tolerance_text = attributes.get("tol") or attributes.get("data-tol")
    actual_text = stringify(actual)
    authored_number = _to_decimal(authored)
    actual_number = _to_decimal(actual_text)
    tolerance = _to_decimal(tolerance_text) if tolerance_text else None
    if authored_number is None or actual_number is None or tolerance is None:
        return ComparisonResult(
            status=Status.ERROR,
            message="tolerance comparison requires numeric values and a tol attribute",
            expected=authored,
            actual=actual_text,
        )
    delta = abs(authored_number - actual_number)
    if delta <= tolerance:
        return ComparisonResult(
            status=Status.PASS,
            message=f"numeric values are within tolerance {tolerance}",
            expected=authored,
            actual=actual_text,
        )
    return ComparisonResult(
        status=Status.FAIL,
        message=f"numeric values differ by {delta}, above tolerance {tolerance}",
        expected=authored,
        actual=actual_text,
    )


def set_compare(
    authored: str,
    actual: Any,
    attributes: Mapping[str, str],
) -> ComparisonResult:
    del attributes
    authored_set = _to_set(authored)
    actual_text = stringify(actual)
    actual_set = _to_set(actual)
    if authored_set is None or actual_set is None:
        return ComparisonResult(
            status=Status.ERROR,
            message="set comparison requires parseable collections",
            expected=authored,
            actual=actual_text,
        )
    if authored_set == actual_set:
        return ComparisonResult(
            status=Status.PASS,
            message="sets match",
            expected=authored,
            actual=actual_text,
        )
    return ComparisonResult(
        status=Status.FAIL,
        message="sets differ",
        expected=authored,
        actual=actual_text,
    )


def none_compare(
    authored: str,
    actual: Any,
    attributes: Mapping[str, str],
) -> ComparisonResult:
    del attributes
    return ComparisonResult(
        status=Status.SKIP,
        message="assertion explicitly marked as not verified",
        expected=authored,
        actual=stringify(actual),
    )


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _to_set(value: Any) -> set[str] | None:
    if isinstance(value, (set, frozenset, list, tuple)):
        return {stringify(item) for item in value}
    if isinstance(value, dict):
        return {stringify(item) for item in value}
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    if not stripped:
        return set()

    parsed = _literal_eval(stripped)
    if parsed is not None:
        return _to_set(parsed)

    return {item.strip() for item in stripped.split(",") if item.strip()}


def _literal_eval(value: str) -> Any | None:
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return None
