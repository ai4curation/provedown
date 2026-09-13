"""Deterministic attester for the Acme Retail bundle.

Compares the SQL an executor reports having run against the sanctioned SQL in
the concept document. Provedown never calls this: attestation is OKF's half of
the problem, and this file is here to show where the boundary falls.
"""

from __future__ import annotations

import re
from typing import Any

_COMMENT = re.compile(r"--[^\n]*")
_WHITESPACE = re.compile(r"\s+")


def canonicalize(sql: str) -> str:
    """Reduce SQL to a form that ignores comments, spacing, and keyword case."""

    without_comments = _COMMENT.sub(" ", sql)
    return _WHITESPACE.sub(" ", without_comments).strip().rstrip(";").lower()


def bind(sql: str, parameters: dict[str, Any]) -> str:
    """Substitute declared ``@name`` parameters, as the executor is required to.

    The executor reports the statement it actually ran, so the sanctioned SQL
    has to be bound the same way before the two can be compared.
    """

    for name, value in parameters.items():
        literal = (
            str(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else "'" + str(value).replace("'", "''") + "'"
        )
        sql = sql.replace(f"@{name}", literal)
    return sql


def attest(
    sanctioned_sql: str,
    parameters: dict[str, Any],
    receipt: dict[str, Any],
    displayed: Any,
) -> bool:
    """Return whether a receipt may be displayed.

    Provenance: the executed SQL must canonicalize to the sanctioned SQL bound
    with the declared parameters, so a swapped table or an added filter fails.
    Fidelity: the value about to be shown must be the value the receipt carries.
    """

    expected = canonicalize(bind(sanctioned_sql, parameters))
    if canonicalize(receipt.get("executed_sql", "")) != expected:
        return False

    rows = receipt.get("result") or []
    return bool(rows) and rows[0] == displayed
