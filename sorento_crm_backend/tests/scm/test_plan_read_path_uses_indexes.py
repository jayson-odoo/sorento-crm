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
    "app/services/scm/price_history_service.py",
    "app/services/scm/purchase_trend_service.py",
    "app/services/scm/trajectory_service.py",
]

# `::text` used as one side of a comparison. Projections (`::text AS`, `::text,`) do not
# match, because they are never followed by an equals sign.
_CAST_IN_PREDICATE = re.compile(r"::text\s*(?:=|<>|!=)")


@pytest.mark.parametrize("relpath", PLAN_READ_PATH)
def test_plan_read_path_never_casts_an_indexed_column_to_text(relpath):
    source = open(os.path.join(_BACKEND, relpath)).read()
    offenders = [
        f"{relpath}:{n}: {line.strip()}"
        for n, line in enumerate(source.splitlines(), start=1)
        if _CAST_IN_PREDICATE.search(line)
    ]
    assert not offenders, (
        "A ::text cast on the left of a comparison makes the column's index unusable. "
        "Cast the parameter instead - CAST(:run_id AS uuid) / CAST(:ids AS uuid[]):\n  "
        + "\n  ".join(offenders)
    )
