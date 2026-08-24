"""SCM M0 CP4 - golden-set regression anchor.

Pins the seeded demo's net_position + valuation for a representative dozen SKUs
(one per pattern: fast / multi-warehouse / stockout / dead / lumpy / open-PO).
`expected_reorder_point`/`safety_stock`/`order_qty` are NULL here and get BLESSED
IN M3 when the engine exists (AC-M3.1). Requires the demo seed to be loaded;
skips gracefully otherwise.
"""
from __future__ import annotations

import json
import os
import re

import pytest
from sqlalchemy import create_engine, text


def _pg_url() -> str | None:
    # DATABASE_URL env wins (CI/container); .env is a local fallback and is NOT
    # shipped in the CI image, so its absence must skip these tests, not crash.
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        if not os.path.exists(env):
            return None
        with open(env) as fh:
            for line in fh:
                if line.startswith("DATABASE_URL"):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not raw:
        return None
    return re.sub(r"^postgresql\+\w+", "postgresql", raw)


URL = _pg_url()
pytestmark = pytest.mark.skipif(
    not URL or not URL.startswith("postgresql"),
    reason="golden-set anchor requires a live Postgres DATABASE_URL",
)

GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "golden_set.json")))["skus"]


@pytest.fixture()
def conn():
    eng = create_engine(URL)
    with eng.connect() as c:
        yield c
    eng.dispose()


def test_golden_set_has_all_patterns(conn):
    """The fixture covers the representative dozen (structure invariant)."""
    assert len(GOLDEN) >= 10, "golden set should carry ~a dozen representative SKUs"
    # both a healthy fast mover and a stockout must be present
    nets = {g["product_code"]: g["net_position"] for g in GOLDEN}
    assert any(v and v > 100 for v in nets.values()), "need a healthy high-net SKU"
    # a stockout/deficit SKU: net <= 0 (net < 0 = stockout WITH committed demand - the reorder signal)
    assert any(v is not None and v <= 0 for v in nets.values()), "need a stockout/deficit SKU"
    assert any(v is not None and v < 0 for v in nets.values()), "need a stockout-with-committed (negative net) SKU"


@pytest.mark.parametrize("g", GOLDEN, ids=[g["product_code"] for g in GOLDEN])
def test_net_position_matches_golden(conn, g):
    """Regression: seeded net_position/valuation stay put. Skips a SKU if the
    seed isn't loaded (so the suite is green on an unseeded DB)."""
    row = conn.execute(text(
        "select np.quantity_on_hand, np.on_order, np.committed, np.net_position, "
        "round(np.quantity_on_hand * p.cost_price, 2) as valuation "
        "from scm.net_position_v np join products p on p.id = np.product_id "
        "where p.product_code = :code and (:wid is null or np.warehouse_id = :wid) "
        "order by np.net_position desc nulls last limit 1"
    ), {"code": g["product_code"], "wid": g["warehouse_id"]}).fetchone()
    if row is None:
        pytest.skip(f"{g['product_code']} not present (seed not loaded)")
    on_hand, on_order, committed, net, valuation = row
    assert float(net) == pytest.approx(g["net_position"]), (
        f"{g['product_code']} net_position drifted: {net} vs golden {g['net_position']}"
    )
    assert float(on_hand) + float(on_order) - float(committed) == pytest.approx(float(net))
    if g["valuation"] is not None and valuation is not None:
        assert float(valuation) == pytest.approx(g["valuation"])
