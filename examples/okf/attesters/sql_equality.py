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
_STRING = re.compile(r"('(?:[^']|'')*')")  # captured, so split keeps the literals


def canonicalize(sql: str) -> str:
    """Reduce SQL to a form that ignores comments, spacing, and keyword case.

    Case is folded outside string literals only. Lowercasing the whole
    statement would make `order_status = 'delivered'` and `= 'DELIVERED'`
    compare equal, and a changed predicate is exactly what this check exists to
    reject.
    """

    without_comments = _COMMENT.sub(" ", sql)
    folded = "".join(
        part if index % 2 else part.lower()
        for index, part in enumerate(_STRING.split(without_comments))
    )
    collapsed = _WHITESPACE.sub(" ", folded).strip()
    return collapsed.rstrip(";").strip()


def bind(sql: str, parameters: dict[str, Any]) -> str:
    """Substitute declared ``@name`` parameters, as the executor is required to.

    The executor reports the statement it actually ran, so the sanctioned SQL
    has to be bound the same way before the two can be compared. Names are
    matched at a boundary and outside string literals, so `@year` does not
    rewrite `@year_end` or `'ops@yearly.example'`.
    """

    if not parameters:
        return sql

    literals = {
        name: (
            str(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else "'" + str(value).replace("'", "''") + "'"
        )
        for name, value in parameters.items()
    }
    names = sorted(literals, key=len, reverse=True)
    pattern = re.compile(
        r"@(" + "|".join(re.escape(name) for name in names) + r")(?![0-9A-Za-z_])"
    )
    return "".join(
        part if index % 2 else pattern.sub(lambda m: literals[m.group(1)], part)
        for index, part in enumerate(_STRING.split(sql))
    )


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
