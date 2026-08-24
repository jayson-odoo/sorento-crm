"""SCM M1 - product-lifecycle filter tests (Postgres-backed, rolled back).

The dashboard defaults to the FOCUSED view (active + ongoing) so inactive /
discontinued SKUs never inflate the headline stockout / valuation figures. These
tests flip a real product's ``is_active`` / ``is_discontinued`` inside the
savepoint and assert every dashboard read (rollups + net-position) moves in
lock-step:

  * default focus excludes inactive + discontinued (the rollup Stockouts count
    drops by exactly the flipped SKU's stockout warehouse-rows),
  * ``active_status=all&lifecycle=all`` includes them again,
  * ``lifecycle=discontinued`` returns only discontinued SKUs.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _focused_stockout_candidate(db):
    """Pick an active + ongoing product that is stocked out in ≥1 warehouse.

    Returns (product_id, sku, stockout_row_count) or None if the demo has none.
    ``stockout_row_count`` = the SKU×warehouse net-position rows with on_hand ≤ 0,
    i.e. exactly how many the rollup Stockouts count loses when we exclude it.
    """
    row = db.execute(text(
        """
        SELECT p.id, p.product_code,
               COUNT(*) FILTER (WHERE np.quantity_on_hand <= 0) AS stockout_rows
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        WHERE p.is_active = true AND p.is_discontinued = false
        GROUP BY p.id, p.product_code
        HAVING COUNT(*) FILTER (WHERE np.quantity_on_hand <= 0) > 0
        ORDER BY stockout_rows DESC
        LIMIT 1
        """
    )).fetchone()
    return (row[0], row[1], int(row[2])) if row else None


def _rollup(client, **params):
    res = client.get("/api/v1/scm/dashboard/rollups", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _net_position_skus(client, sku, **params):
    params.setdefault("query", sku)
    res = client.get("/api/v1/scm/dashboard/net-position", params=params)
    assert res.status_code == 200, res.text
    return {r["sku"] for r in res.json()["data"]}


def test_default_focus_excludes_inactive(scm_app):
    """Flipping a product to inactive drops it from the focused rollup + grid,
    reducing Stockouts by exactly its stockout-row count; ``all`` keeps it."""
    app, db = _client(scm_app, "purchasing")
    cand = _focused_stockout_candidate(db)
    if not cand:
        pytest.skip("demo has no active+ongoing stocked-out SKU")
    pid, sku, stockout_rows = cand

    with TestClient(app) as c:
        before = _rollup(c)["stockout_count"]
        all_before = _rollup(c, active_status="all", lifecycle="all")["stockout_count"]
        assert sku in _net_position_skus(c, sku)  # visible while active

        db.execute(text("UPDATE products SET is_active = false WHERE id = :id"), {"id": pid})
        db.flush()

        after = _rollup(c)["stockout_count"]
        assert after == before - stockout_rows  # dropped from the focused count
        assert sku not in _net_position_skus(c, sku)  # gone from the focused grid

        # the all-statuses scope still counts the SKU (unchanged by the flip) and
        # keeps the row visible.
        all_after = _rollup(c, active_status="all", lifecycle="all")["stockout_count"]
        assert all_after == all_before
        assert sku in _net_position_skus(c, sku, active_status="all", lifecycle="all")


def test_default_focus_excludes_discontinued(scm_app):
    """A discontinued SKU drops from the focused view; lifecycle=discontinued
    returns ONLY discontinued SKUs (the flipped one present, an ongoing one not)."""
    app, db = _client(scm_app, "purchasing")
    cand = _focused_stockout_candidate(db)
    if not cand:
        pytest.skip("demo has no active+ongoing stocked-out SKU")
    pid, sku, stockout_rows = cand

    # a second, still-ongoing stocked-out SKU to prove the discontinued view excludes it
    other = db.execute(text(
        """
        SELECT p.product_code
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        WHERE p.is_active = true AND p.is_discontinued = false
          AND np.quantity_on_hand <= 0 AND p.id <> :pid
        LIMIT 1
        """
    ), {"pid": pid}).scalar()

    with TestClient(app) as c:
        before = _rollup(c)["stockout_count"]

        db.execute(text("UPDATE products SET is_discontinued = true WHERE id = :id"), {"id": pid})
        db.flush()

        # focused (default) excludes the now-discontinued SKU.
        after = _rollup(c)["stockout_count"]
        assert after == before - stockout_rows
        assert sku not in _net_position_skus(c, sku)

        # lifecycle=discontinued (any status) returns the discontinued SKU only.
        disc = _net_position_skus(c, sku, active_status="all", lifecycle="discontinued")
        assert sku in disc
        if other:
            assert other not in _net_position_skus(
                c, other, active_status="all", lifecycle="discontinued"
            )


def test_all_scope_is_superset_of_focus(scm_app):
    """``active_status=all&lifecycle=all`` is a strict superset - its Stockouts
    count is ≥ the focused default (the demo carries inactive/discontinued SKUs)."""
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        focused = _rollup(c)["stockout_count"]
        all_scope = _rollup(c, active_status="all", lifecycle="all")["stockout_count"]
    assert all_scope >= focused


def test_bad_lifecycle_param_falls_back_to_focus(scm_app):
    """An unrecognised lifecycle value normalises to the focused default rather
    than 500-ing or silently widening the scope."""
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        focused = _rollup(c)["stockout_count"]
        garbage = _rollup(c, active_status="nonsense", lifecycle="")["stockout_count"]
    assert garbage == focused
