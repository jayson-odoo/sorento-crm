"""SCM M2 - demand engine golden + pure-maths tests (AC-M2.1/2.2/2.3/2.13).

Golden numbers (avg_daily_demand / demand_cv / method) are blessed in
``fixtures/golden_m2.json``, derived INDEPENDENTLY from the real prod-copy outflow
by ``scripts/scm_m2_golden_derive.py`` (a different code path than the engine). The
demand run is scoped to the golden product_ids with a FIXED ``as_of`` so the window
is deterministic; everything runs inside the rolled-back savepoint.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.services.scm import analytics_service as svc
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

_GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "golden_m2.json")))
_AS_OF = date.fromisoformat(_GOLDEN["as_of"])


def _pid(db, code):
    return db.execute(text("SELECT id FROM products WHERE product_code = :c"), {"c": code}).scalar()


def _wid(db, code):
    return db.execute(text("SELECT id FROM warehouses WHERE warehouse_code = :c"), {"c": code}).scalar()


# ---------------------------------------------------------------------------
# Pure maths - no DB (AC-M2.2: trim ONLY the moderate-variability Y band)
# ---------------------------------------------------------------------------

def test_bucket_stats_steady_x_band_uses_plain_mean():
    """X band (CV<=0.5): steady demand -> plain mean, baseline == total."""
    s = svc.bucket_stats([100.0, 100.0, 100.0])
    assert s["method"] == "mean" and s["band"] == "X"
    assert s["cv"] == pytest.approx(0.0, abs=1e-9)
    assert s["baseline_total"] == pytest.approx(300.0)


def test_bucket_stats_y_band_trims_and_is_not_inflated():
    """Y band (0.5<CV<=1.0): an occasional 4x spike week is trimmed so it can NOT
    inflate the baseline (asserted vs the naive sum)."""
    series = [100.0] * 11 + [400.0, 0.0]  # 13 weekly totals -> CV ~0.75 (Y band)
    s = svc.bucket_stats(series)
    naive_total = sum(series)  # 1500 - inflated by the spike
    assert 0.5 < s["cv"] <= 1.0 and s["band"] == "Y"
    assert s["method"] == "trimmed_mean"
    assert s["baseline_total"] < naive_total
    # floor(0.10*13)=1 each tail -> drop the 400 spike and the 0 dip -> kept mean 100
    assert s["baseline_total"] == pytest.approx(1300.0)


def test_bucket_stats_z_band_lumpy_uses_plain_mean_and_is_nonzero():
    """Z band (CV>1.0): lumpy demand IS the signal - a single real spike week among
    zeros (the C-FH24 shape) must NOT be trimmed to a zero baseline. Plain mean keeps
    the whole outflow; the Z class letter carries the low-confidence signal."""
    s = svc.bucket_stats([1246.0] + [0.0] * 12)  # 13 weekly totals, one lone spike
    assert s["cv"] > 1.0 and s["band"] == "Z"
    assert s["method"] == "mean"
    # trimming here would drop the ONLY non-zero week -> baseline 0; plain mean keeps it
    assert s["baseline_total"] == pytest.approx(1246.0)
    assert s["baseline_total"] > 0.0


def test_bucket_stats_weekly_trim_drops_one_period_each_tail():
    """The engine's ~13 weekly buckets in the Y band: floor(0.10*13)=1 period is dropped
    off each tail, so an occasional spike week cannot inflate the baseline."""
    weekly = [100.0] * 11 + [400.0, 0.0]  # 13 weekly totals -> Y band
    s = svc.bucket_stats(weekly)
    assert 0.5 < s["cv"] <= 1.0 and s["method"] == "trimmed_mean"
    # drop the 400 spike and the 0 dip -> kept mean 100 -> baseline 100*13
    assert s["baseline_total"] == pytest.approx(1300.0)
    assert s["baseline_total"] < sum(weekly)  # 1500 naive is not used


def test_bucket_stats_daily_rate_cv_neutralizes_short_bucket():
    """S3: CV is computed over per-bucket DAILY RATES so the short oldest bucket (the
    6-day weekly remainder) can't structurally inflate variability. A flat daily rate
    across all 13 buckets reads CV≈0 even though the oldest bucket carries fewer units;
    computing CV over the RAW totals instead manufactures spurious variability."""
    lengths = svc.BUCKET_DAY_LENGTHS  # [7]*12 + [6]
    buckets = [70.0] * 12 + [60.0]  # constant 10/day everywhere (70=7*10, 60=6*10)
    s = svc.bucket_stats(buckets, day_lengths=lengths)
    assert s["cv"] == pytest.approx(0.0, abs=1e-9)  # flat daily rate → zero variability
    assert s["band"] == "X"
    raw = svc.bucket_stats(buckets)  # equal lengths → CV over raw totals (the old bias)
    assert raw["cv"] > 0.0


def test_bucket_stats_small_n_y_band_trim_is_noop_numerically():
    """Edge (pure-function): with only 3 periods the 10% trim removes 0 periods, so a
    Y-band key still reports the plain sum as baseline (branch label = trimmed_mean).
    The engine runs on ~13 weekly buckets where the trim DOES fire - this pins the
    small-n boundary itself."""
    s = svc.bucket_stats([100.0, 50.0, 10.0])  # CV ~0.69 (Y band), n=3
    assert s["method"] == "trimmed_mean" and s["band"] == "Y"
    assert s["baseline_total"] == pytest.approx(160.0)


# ---------------------------------------------------------------------------
# Golden demand over real outflow (AC-M2.1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("g", _GOLDEN["demand"], ids=[f"{g['product_code']}@{g['warehouse_code']}" for g in _GOLDEN["demand"]])
def test_demand_stat_matches_golden(scm_app, g):
    _, db, _, _ = scm_app
    pid, wid = _pid(db, g["product_code"]), _wid(db, g["warehouse_code"])
    assert pid and wid, f"{g['product_code']}@{g['warehouse_code']} not in DB"

    pids = [_pid(db, x["product_code"]) for x in _GOLDEN["demand"]]
    svc.run_analytics(db, scope={"product_ids": pids}, config={"as_of": _AS_OF})

    row = db.execute(text(
        "SELECT avg_daily_demand, demand_cv, method FROM scm.demand_stat "
        "WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": pid, "w": wid}).fetchone()
    assert row is not None, "demand_stat not written"
    assert float(row.avg_daily_demand) == pytest.approx(g["avg_daily_demand"], abs=0.01)
    assert float(row.demand_cv) == pytest.approx(g["demand_cv"], abs=0.01)
    assert row.method == g["method"]


# ---------------------------------------------------------------------------
# Robust trim fires on REAL weekly data (AC-M2.2 - weekly bucketing)
# ---------------------------------------------------------------------------

def test_weekly_trim_fires_on_real_data(scm_app):
    """AC-M2.2 on real data: with ~13 weekly buckets a high-CV SKU's trimmed_mean
    baseline is STRICTLY below its plain window total because a spike week is dropped
    - the trim is no longer the 3-bucket no-op. Proven end-to-end via explain_demand's
    baseline_total, cross-checked against the independently-derived golden number."""
    _, db, _, _ = scm_app
    g = next(x for x in _GOLDEN["demand"] if x.get("trim_demonstration"))
    pid, wid = _pid(db, g["product_code"]), _wid(db, g["warehouse_code"])
    assert pid and wid

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})
    e = svc.explain_demand(db, pid, wid, config={"as_of": _AS_OF})

    assert e["method"] == "trimmed_mean"
    assert e["demand_cv"] > 0.5
    # the trim actually removed demand: robust baseline < the naive window sum
    assert e["baseline_total"] < e["total"], "weekly trim did not fire (no-op)"
    assert e["baseline_total"] == pytest.approx(g["baseline_total"], abs=0.1)
    assert e["total"] == pytest.approx(g["total"], abs=0.5)
    # avg_daily is the trimmed baseline over 90 days, below the naive rate
    assert e["avg_daily_demand"] == pytest.approx(g["avg_daily_demand"], abs=0.01)
    assert e["avg_daily_demand"] < g["total"] / _GOLDEN["window_days"]
    assert len(e["buckets"]) == _GOLDEN["num_buckets"]  # ~13 weekly sample points


def test_lumpy_z_sku_uses_plain_mean_and_is_nonzero(scm_app):
    """AC-M2.2 (revised): a lumpy Z SKU (CV>1.0) with real outflow concentrated in a
    single spike week (C-FH24: one 1246-unit order) must NOT be trimmed to a zero
    baseline. The Z band uses the plain mean end-to-end, so avg_daily_demand reflects
    the real sale - a regression against the old 'trim both tails => 0 demand' bug."""
    _, db, _, _ = scm_app
    g = next(x for x in _GOLDEN["demand"] if x.get("lumpy_nonzero_demonstration"))
    pid, wid = _pid(db, g["product_code"]), _wid(db, g["warehouse_code"])
    assert pid and wid

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})
    e = svc.explain_demand(db, pid, wid, config={"as_of": _AS_OF})

    assert e["demand_cv"] > 1.0 and e["band"] == "Z"
    assert e["method"] == "mean"  # lumpy demand kept whole, not trimmed
    # the plain mean keeps the full window outflow -> baseline == total, strictly > 0
    assert e["baseline_total"] == pytest.approx(e["total"], abs=0.5)
    assert e["baseline_total"] == pytest.approx(g["baseline_total"], abs=0.5)
    assert e["baseline_total"] > 0.0
    assert e["avg_daily_demand"] == pytest.approx(g["avg_daily_demand"], abs=0.01)
    assert e["avg_daily_demand"] > 0.0

    # persisted demand_stat agrees: plain-mean method, non-zero rate
    row = db.execute(text(
        "SELECT avg_daily_demand, method FROM scm.demand_stat "
        "WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": pid, "w": wid}).fetchone()
    assert row.method == "mean"
    assert float(row.avg_daily_demand) > 0.0


# ---------------------------------------------------------------------------
# Channel split + no double-count (AC-M2.3)
# ---------------------------------------------------------------------------

def test_channel_split_separates_and_does_not_double_count(scm_app):
    _, db, _, _ = scm_app
    cs = _GOLDEN["channel_split_sku"]
    pid, wid = _pid(db, cs["product_code"]), _wid(db, cs["warehouse_code"])
    assert pid and wid

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})
    row = db.execute(text(
        "SELECT channel_split FROM scm.demand_stat WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": pid, "w": wid}).fetchone()
    split = row.channel_split
    cont = float(split["continuous"]["qty"])
    spike = float(split["spike"]["qty"])
    # blessed: continuous(tagged+untagged) and spike are separated, and reconcile to
    # the window total - a project (spike) sale is NOT also counted as continuous.
    assert cont == pytest.approx(cs["continuous_qty"])
    assert spike == pytest.approx(cs["spike_qty"])
    assert cont + spike == pytest.approx(cs["total"])
    assert spike > 0 and cont > 0


# ---------------------------------------------------------------------------
# Zero-outflow SKU degrades gracefully (no divide-by-zero)
# ---------------------------------------------------------------------------

def test_zero_outflow_sku_is_graceful(scm_app):
    _, db, _, _ = scm_app
    # a planning key present in net_position_v but with no consumption in the window
    key = db.execute(text("""
        SELECT np.product_id, np.warehouse_id FROM scm.net_position_v np
        WHERE NOT EXISTS (
          SELECT 1 FROM scm.consumption_v c
          WHERE c.product_id = np.product_id AND c.warehouse_id = np.warehouse_id
            AND c.day >= :lo AND c.day < :as_of)
        LIMIT 1
    """), {"lo": _AS_OF - timedelta(days=90), "as_of": _AS_OF}).fetchone()
    if key is None:
        pytest.skip("no zero-outflow planning key found")
    svc.run_analytics(db, scope={"product_ids": [key.product_id]}, config={"as_of": _AS_OF})
    row = db.execute(text(
        "SELECT avg_daily_demand, method, demand_cv FROM scm.demand_stat "
        "WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": key.product_id, "w": key.warehouse_id}).fetchone()
    assert row is not None
    assert float(row.avg_daily_demand) == pytest.approx(0.0)
    assert row.method == "insufficient_data"
    assert row.demand_cv is None


# ---------------------------------------------------------------------------
# Explain determinism (AC-M2.13)
# ---------------------------------------------------------------------------

def test_explain_demand_deterministic_and_matches_stored(scm_app):
    _, db, _, _ = scm_app
    g = _GOLDEN["demand"][0]  # WESERP10B@BRW
    pid, wid = _pid(db, g["product_code"]), _wid(db, g["warehouse_code"])
    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})

    e1 = svc.explain_demand(db, pid, wid, config={"as_of": _AS_OF})
    e2 = svc.explain_demand(db, pid, wid, config={"as_of": _AS_OF})
    assert e1 == e2  # same inputs -> identical output
    assert e1["avg_daily_demand"] == pytest.approx(g["avg_daily_demand"], abs=0.01)
    assert e1["method"] == g["method"]
    assert [b["qty"] for b in e1["buckets"]] == list(reversed(g["buckets"]))  # oldest->newest

    stored = db.execute(text(
        "SELECT avg_daily_demand FROM scm.demand_stat WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": pid, "w": wid}).scalar()
    assert e1["avg_daily_demand"] == pytest.approx(float(stored), abs=0.01)
