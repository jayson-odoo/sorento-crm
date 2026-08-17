"""The plan screen's reads must be able to use the indexes that already exist.

`scm.reorder_recommendation` is indexed on `run_id` and on `(run_id, rec_type)`, but a
predicate written as ``run_id::text = :run_id`` casts the INDEXED SIDE, so Postgres cannot
use either index and falls back to a parallel sequential scan of the whole table. Measured
on the prod-copy database (396,601 rows across 153 runs), the run-history buy count:

    run_id::text = ANY(...)          4,629 ms   90,624 buffers (parallel seq scan)
    run_id = ANY(CAST(... AS uuid[]))    81 ms    1,314 buffers (bitmap index scan)

That is the plan screen's dominant cost, and it grows with the number of runs ever
recorded rather than with the size of the plan being viewed - which is why a production
instance with months of daily runs behind it is far slower than a fresh one at the same
row count.

The cast belongs on the PARAMETER (``CAST(:run_id AS uuid)``), never on the column. A
``SELECT x::text AS x`` projection is fine and deliberate - it is how these endpoints keep
returning ids as strings - so only comparisons are banned here.

One column is deliberately exempt: ``users.id`` is a ``text`` column, so ``id::text`` there
is a no-op relabel rather than a cast away from an indexed type. Those sites drop the
redundant cast instead of gaining a uuid one, and the regex below never sees them because
they no longer carry ``::text``.
"""
from __future__ import annotations

import os
import re

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Every module whose SQL runs while the reorder plan screen is loading.
PLAN_READ_PATH = [
    "app/api/v1/scm/reorder_runs.py",
    "app/services/scm/cover_service.py",
    "app/services/scm/level_suggestion_service.py",
    "app/services/scm/plan_exception_service.py",
    "app/services/scm/price_history_service.py",
    "app/services/scm/product_economics_service.py",
    "app/services/scm/purchase_trend_service.py",
    "app/services/scm/reorder_level_service.py",
    "app/services/scm/trajectory_service.py",
]

# A string cast used as one side of a comparison, in either spelling Postgres accepts:
#   product_id::text = ANY(:pids)      -> the `::` form
#   CAST(product_id AS text) = :pid    -> the functional form
# Projections (`::text AS product_id`, `::text,`) never match: they are not followed by a
# comparison operator. `IN` needs a word boundary so `INNER JOIN` is not a hit.
_COMPARISON = r"\s*(?:=|<>|!=|>|<|\bIN\b)"
_CAST_IN_PREDICATE = re.compile(
    r"(?:::\s*(?:text|varchar|char)" + _COMPARISON + r")"
    r"|(?:\bCAST\s*\([^()]*\bAS\s+(?:text|varchar|char)\s*\)" + _COMPARISON + r")",
    re.IGNORECASE,
)


def _offenders(source: str, label: str) -> list[str]:
    """Hits, reported with the line the cast starts on.

    The SQL in these modules is written across several lines, so a predicate can be split
    between them (``WHERE p.id::text\\n = ANY(:ids)``). Scanning line by line would miss
    exactly the ones most likely to be overlooked in review, so the whitespace is collapsed
    first and the offset mapped back to a line number.
    """
    flat = re.sub(r"\s+", " ", source)
    line_of = []
    line = 1
    prev_ws = False
    for ch in source:
        is_ws = ch.isspace()
        if not (is_ws and prev_ws):
            line_of.append(line)
        if ch == "\n":
            line += 1
        prev_ws = is_ws
    out = []
    for m in _CAST_IN_PREDICATE.finditer(flat):
        n = line_of[m.start()] if m.start() < len(line_of) else -1
        out.append(f"{label}:{n}: {flat[max(0, m.start() - 60):m.end() + 20].strip()}")
    return out


@pytest.mark.parametrize("relpath", PLAN_READ_PATH)
def test_plan_read_path_never_casts_an_indexed_column_to_text(relpath):
    with open(os.path.join(_BACKEND, relpath), encoding="utf-8") as fh:
        source = fh.read()

    offenders = _offenders(source, relpath)

    assert not offenders, (
        "A string cast on the left of a comparison makes the column's index unusable. "
        "Cast the parameter instead - CAST(:run_id AS uuid) / CAST(:ids AS uuid[]):\n  "
        + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------- #
# the guard's own behaviour
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "sql",
    [
        "WHERE run_id::text = :run_id",
        "WHERE product_id::text = ANY(:pids)",
        "WHERE product_id :: text = ANY(:pids)",
        "WHERE code::varchar = :c",
        "WHERE code::char = :c",
        "WHERE CAST(product_id AS text) = :pid",
        "WHERE cast(product_id as varchar) IN (:a, :b)",
        # split across lines, which a line-by-line scan would miss
        "WHERE p.id::text\n      = ANY(:ids)",
    ],
)
def test_the_guard_catches_a_cast_used_in_a_comparison(sql):
    assert _offenders(sql, "probe"), f"guard missed: {sql}"


@pytest.mark.parametrize(
    "sql",
    [
        # Projections are the point of these endpoints: ids reach the API as strings.
        "SELECT id::text AS id, warehouse_code FROM warehouses",
        "SELECT r.product_id::text, r.supplier_id::text FROM scm.reorder_recommendation r",
        "SELECT id::text AS id FROM products WHERE id = ANY(CAST(:ids AS uuid[]))",
        "WHERE run_id = CAST(:run_id AS uuid)",
        "WHERE product_id = ANY(CAST(:pids AS uuid[]))",
        # A NULL-safe sentinel comparison casts INSIDE a COALESCE, not against the column.
        "WHERE COALESCE(warehouse_id::text, :zero) = COALESCE(CAST(:wid AS text), :zero)",
        # `IN` must need a word boundary, or every INNER JOIN after a projection is a hit.
        "SELECT p.id::text AS id FROM products p INNER JOIN stock s ON s.product_id = p.id",
    ],
)
def test_the_guard_leaves_projections_and_parameter_casts_alone(sql):
    assert not _offenders(sql, "probe"), f"guard false-positived on: {sql}"
