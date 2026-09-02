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
    # S3 perf quick wins (AC-3.1/3.2/3.3): the decisions list and the plans-list counts
    # both resolve a recommendation's draft/active PO line through
    # `ix_purchase_order_lines_source_ref_system` (`_po_for_rec`, `_pos_for_recs`,
    # `_refresh_run_counts`) - the same "never cast the compared column away from its
    # indexed type" rule applies here.
    "app/services/scm/decision_service.py",
]

# A string cast used as one side of a comparison, in either spelling Postgres accepts:
#   product_id::text = ANY(:pids)      -> the `::` form
#   CAST(product_id AS text) = :pid    -> the functional form
# Projections (`::text AS product_id`, `::text,`) never match: they are not followed by a
# comparison operator. `IN` needs a word boundary so `INNER JOIN` is not a hit.
_COMPARISON = r"\s*(?:=|<>|!=|>|<|\bIN\b)"
#: Review finding (S3 perf PR): the two alternatives above only catch the cast on the LEFT
#: of the operator (`col::text = ...`). A parameter compared against a cast column in the
#: REVERSED order (`:param = col::text`) is the identical violation - the column is still
#: cast away from its indexed type - and went uncaught. Scoped to a bind PARAMETER on the
#: left (`:word`, optionally `ANY(:word)`) rather than "anything", so a genuine two-column
#: join that casts the UNINDEXED side to match an indexed column left bare (e.g.
#: `pol.source_ref = r.id::text`, `decision_service._refresh_run_counts`) is not a false
#: positive: that shape has a real column on the left, never a parameter marker.
_PARAM = r":\w+|\bANY\s*\(\s*:\w+\s*\)"
_CAST_AFTER_PARAM = r"(?:" + _PARAM + r")" + _COMPARISON + r"\s*"
_CAST_IN_PREDICATE = re.compile(
    r"(?:::\s*(?:text|varchar|char)" + _COMPARISON + r")"
    r"|(?:\bCAST\s*\([^()]*\bAS\s+(?:text|varchar|char)\s*\)" + _COMPARISON + r")"
    r"|(?:" + _CAST_AFTER_PARAM + r"\w+(?:\.\w+)?\s*::\s*(?:text|varchar|char)\b)"
    r"|(?:" + _CAST_AFTER_PARAM + r"\bCAST\s*\(\s*\w+(?:\.\w+)?\s+AS\s+(?:text|varchar|char)\s*\))",
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
        # Review finding: the SAME violation, operand order reversed - a parameter on the
        # LEFT compared against the cast column on the RIGHT.
        "WHERE :run_id = run_id::text",
        "WHERE :pid = product_id :: text",
        "WHERE :pid = CAST(product_id AS text)",
        "WHERE ANY(:ids) = p.id::text",
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
        # A genuine two-column join across mismatched types casts the UNINDEXED side to
        # match the indexed one left BARE - `decision_service._refresh_run_counts`'s own
        # `pol.source_ref = r.id::text` (the new `ix_purchase_order_lines_source_ref_system`
        # covers `pol.source_ref`, untouched here; `r.id` is a uuid primary key cast only to
        # join against `source_ref`'s varchar). The right-side-of-operator probe added above
        # is scoped to a bind PARAMETER on the left precisely so this real, correct join
        # shape does not become a false positive of that fix.
        "ON pol.source_ref = r.id::text AND pol.source_system IN (:src, :src_product)",
    ],
)
def test_the_guard_leaves_projections_and_parameter_casts_alone(sql):
    assert not _offenders(sql, "probe"), f"guard false-positived on: {sql}"
