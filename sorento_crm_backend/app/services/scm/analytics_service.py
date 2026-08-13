"""SCM M2 analytics engine — deterministic demand rate, ABC/XYZ, supplier performance.

One entry point ``run_analytics(db, scope, config)`` computes, over a shared window:

  1. **Demand** (``scm.demand_stat``, SKU x warehouse) — DO outflow read the way
     ``scm.consumption_v`` reads it (order_lines joined orders, NOT stock_ledger),
     bucketed into ~13 trailing 7-day (weekly) periods. Channel-split continuous vs spike
     by customer -> market_segment -> demand_nature (untagged defaults to continuous).
     Baseline = plain sum in the X (CV<=0.5) and Z (CV>1.0) bands; robust trimmed mean
     ONLY in the Y band (0.5<CV<=1.0). Z (lumpy) is kept whole — a single-spike Z SKU
     must not be trimmed to a zero baseline. ``avg_daily_demand = baseline_total / window_days``.
  2. **Classification** (``scm.item_classification``) — ABC by cumulative trailing-12mo
     annual value (qty*cost) over ALL costed keys (A<=80% / B<=95% / C=rest); null-cost
     keys => abc_class NULL (unknown). XYZ by demand CV (X<=0.5 / Y<=1.0 / Z>1.0).
  3. **Supplier performance** (``scm.supplier_performance``, supplier x product) — from
     PO -> GR (picking) pairs the way ``scm.receipt_lead_v`` reads them: on_time
     (receipt <= expected + grace), avg_lead_time from the COMPLETING receipt,
     lead_time_variance, reject/fill rate, weighted composite. Below min_sample it
     falls back to the supplier-level aggregate (confidence 'medium', or 'low' when the
     supplier itself is thin) — never a fabricated score. Denormalises the supplier
     composite onto ``suppliers.current_performance_score``.

Every execution writes one ``scm.scm_analytics_run`` row (status / scope / counts /
window / duration / channel-coverage %). ``explain_demand`` re-derives a single SKU's
working deterministically for debugging (AC-M2.13). Config tables (``abc_xyz_policy``,
``supplier_scoring_policy``) are ensured with locked defaults and drive the maths with
no code change (AC-M2.5/2.8). No LLM anywhere — pure maths (AC-M2.15).
"""
from __future__ import annotations

import statistics as _st
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID, resolve_write_company_id

# --- locked engine constants (see PLAN/UAC M2 + golden derivation) -----------
WINDOW_DAYS = 90
BUCKET_DAYS = 7  # weekly buckets — makes CV + the 10% trim meaningful
# ceil(90/7) = 13 trailing weekly buckets over the 90-day window; the oldest
# bucket is a short (~6-day) remainder. Window stays 90d for the daily rate.
NUM_BUCKETS = (WINDOW_DAYS + BUCKET_DAYS - 1) // BUCKET_DAYS  # == 13
# Per-bucket day counts, newest-first. Buckets 0..11 are full 7-day weeks; the
# oldest (index 12) is the short remainder clamped to the 90-day window start
# (90-84 = 6 days). CV is computed over per-bucket DAILY RATES (qty/day) using
# these lengths so the short oldest bucket does not structurally inflate variability.
BUCKET_DAY_LENGTHS = [
    min(BUCKET_DAYS * (i + 1), WINDOW_DAYS) - BUCKET_DAYS * i for i in range(NUM_BUCKETS)
]  # == [7,7,7,7,7,7,7,7,7,7,7,7,6]
ANNUAL_DAYS = 365

# policy defaults (seeded into the config tables when absent; editable thereafter)
DEFAULT_ABC_A_PCT = 80
DEFAULT_ABC_B_PCT = 95
DEFAULT_XYZ_X_MAX = 0.5
DEFAULT_XYZ_Y_MAX = 1.0
DEFAULT_DELIVERY_WEIGHT = 0.5
DEFAULT_QUALITY_WEIGHT = 0.5
DEFAULT_GRACE_DAYS = 2
DEFAULT_MIN_SAMPLE_SIZE = 3

_SEED = "engine"


# ---------------------------------------------------------------------------
# Policy defaults (idempotent ensure — never rely on empty policy tables)
# ---------------------------------------------------------------------------

def ensure_policy_defaults(db: Session) -> None:
    """Guarantee one active ``abc_xyz_policy`` + one active ``supplier_scoring_policy``.

    Idempotent: only inserts when no active row exists, so re-runs and hand-edited
    values are never clobbered.
    """
    has_abc = db.execute(text(
        "SELECT 1 FROM scm.abc_xyz_policy WHERE is_active = true LIMIT 1"
    )).first()
    if not has_abc:
        db.execute(text(
            "INSERT INTO scm.abc_xyz_policy "
            "(id, abc_a_pct, abc_b_pct, xyz_x_max, xyz_y_max, is_active, "
            " source_system, source_ref, created_at, updated_at) "
            "VALUES (:id, :a, :b, :x, :y, true, :s, 'defaults', now(), now())"
        ), {"id": str(uuid.uuid4()), "a": DEFAULT_ABC_A_PCT, "b": DEFAULT_ABC_B_PCT,
            "x": DEFAULT_XYZ_X_MAX, "y": DEFAULT_XYZ_Y_MAX, "s": _SEED})

    has_sup = db.execute(text(
        "SELECT 1 FROM scm.supplier_scoring_policy WHERE is_active = true LIMIT 1"
    )).first()
    if not has_sup:
        db.execute(text(
            "INSERT INTO scm.supplier_scoring_policy "
            "(id, delivery_weight, quality_weight, grace_days, min_sample_size, is_active, "
            " source_system, source_ref, created_at, updated_at) "
            "VALUES (:id, :dw, :qw, :g, :m, true, :s, 'defaults', now(), now())"
        ), {"id": str(uuid.uuid4()), "dw": DEFAULT_DELIVERY_WEIGHT, "qw": DEFAULT_QUALITY_WEIGHT,
            "g": DEFAULT_GRACE_DAYS, "m": DEFAULT_MIN_SAMPLE_SIZE, "s": _SEED})


def _normalize_abc_cuts(a_raw: float, b_raw: float) -> tuple[float, float]:
    """Return canonical CUMULATIVE cut points (0..100) for A and B.

    Robust to two historical conventions found in the wild:
      * canonical:  abc_a_pct=80, abc_b_pct=95 (cumulative percent).
      * legacy seed: abc_a_pct=0.80, abc_b_pct=0.15 (A fraction + B *band* fraction).
    A value <= 1 is read as a fraction (x100); a B cut below the A cut is read as a
    band width (B cut = A + band). Both map to (80, 95).
    """
    a = float(a_raw)
    b = float(b_raw)
    if a <= 1:
        a *= 100.0
        b *= 100.0
    if b < a:  # b is a band width, not a cumulative cut
        b = a + b
    return a, b


def _abc_xyz_policy(db: Session) -> dict:
    row = db.execute(text(
        "SELECT abc_a_pct, abc_b_pct, xyz_x_max, xyz_y_max FROM scm.abc_xyz_policy "
        "WHERE is_active = true ORDER BY updated_at DESC, created_at ASC LIMIT 1"
    )).fetchone()
    if not row:
        return {"a": DEFAULT_ABC_A_PCT, "b": DEFAULT_ABC_B_PCT,
                "x": DEFAULT_XYZ_X_MAX, "y": DEFAULT_XYZ_Y_MAX}
    a, b = _normalize_abc_cuts(row[0], row[1])
    return {"a": a, "b": b, "x": float(row[2]), "y": float(row[3])}


def _supplier_policy(db: Session) -> dict:
    row = db.execute(text(
        "SELECT delivery_weight, quality_weight, grace_days, min_sample_size "
        "FROM scm.supplier_scoring_policy WHERE is_active = true "
        "ORDER BY updated_at DESC, created_at ASC LIMIT 1"
    )).fetchone()
    if not row:
        return {"dw": DEFAULT_DELIVERY_WEIGHT, "qw": DEFAULT_QUALITY_WEIGHT,
                "grace": DEFAULT_GRACE_DAYS, "min_sample": DEFAULT_MIN_SAMPLE_SIZE}
    return {"dw": float(row[0]), "qw": float(row[1]),
            "grace": int(row[2]) if row[2] is not None else DEFAULT_GRACE_DAYS,
            "min_sample": int(row[3]) if row[3] is not None else DEFAULT_MIN_SAMPLE_SIZE}


# ---------------------------------------------------------------------------
# Pure maths (unit-testable in isolation — no DB)
# ---------------------------------------------------------------------------

def bucket_stats(buckets: list[float], x_max: float = DEFAULT_XYZ_X_MAX,
                 y_max: float = DEFAULT_XYZ_Y_MAX,
                 day_lengths: Optional[Sequence[float]] = None) -> dict:
    """Demand stats over the period buckets.

    Returns total / mean / cv / band / method / method_reason / baseline_total.
    ``cv`` is measured over per-bucket DAILY RATES (``bucket_qty / bucket_days``) when
    ``day_lengths`` is supplied, so the short oldest weekly bucket (a 6-day remainder)
    does not structurally inflate variability (S3). With equal lengths — or none —
    this is identical to the CV of the raw totals (CV is scale-invariant). The
    baseline maths stays on the raw weekly totals; only the CV/band decision uses rates.

    The robust trim fires ONLY in the moderate-variability (Y) band — the same
    CV cut points that drive XYZ so the branch and the class letter agree:

      * X  (CV<=x_max, default 0.5): steady demand -> **plain mean** (baseline == total).
      * Y  (x_max<CV<=y_max, default 0.5..1.0): occasional spikes -> **trimmed mean**,
        drop the top+bottom 10% of periods (``floor(0.10*n)`` each tail; one weekly
        period off each end on the ~13 buckets) so a spike week can't inflate the baseline.
      * Z  (CV>y_max, default 1.0): lumpy demand IS the signal -> **plain mean** (NOT
        trimmed). Trimming a single-spike Z SKU dropped both tails and zeroed a real
        seller; Z already flags low confidence via its class letter, so keep the demand
        whole. ``method`` is 'mean' (same as X); ``band``/``method_reason`` carry the why.
    """
    n = len(buckets)
    total = float(sum(buckets))
    mean = total / n if n else 0.0
    # CV over per-bucket DAILY RATES (unequal bucket lengths don't bias variability).
    lengths = day_lengths if day_lengths is not None else [1.0] * n
    rates = [buckets[i] / lengths[i] for i in range(n)] if n else []
    rate_mean = (sum(rates) / n) if n else 0.0
    cv = (_st.pstdev(rates) / rate_mean) if rate_mean > 0 else 0.0
    band = "X" if cv <= x_max else ("Y" if cv <= y_max else "Z")
    if band == "Y":
        # robust branch — trim only the moderate-variability band
        trim = int(n * 0.10)
        kept = sorted(buckets)[trim: n - trim] if trim else list(buckets)
        kept_mean = (sum(kept) / len(kept)) if kept else mean
        baseline_total = kept_mean * n
        return {"total": total, "mean": mean, "cv": cv, "band": band,
                "method": "trimmed_mean", "baseline_total": baseline_total,
                "method_reason": (f"Y band ({x_max}<CV<={y_max}): trimmed 10% tails to "
                                  "tame occasional spikes")}
    reason = (f"X band (CV<={x_max}): steady demand, plain mean" if band == "X"
              else f"Z band (CV>{y_max}): lumpy demand kept whole (spikes are the signal, "
                   "not trimmed to zero)")
    return {"total": total, "mean": mean, "cv": cv, "band": band,
            "method": "mean", "baseline_total": total, "method_reason": reason}


def abc_classify(ranked_values: list[float], a_cut: float, b_cut: float) -> list[str]:
    """ABC letters for values already sorted DESC by annual value.

    The class is decided on the cumulative share of the grand total BEFORE the item
    itself is added (``prev_cum``): A when ``prev_cum <= a_cut``, B when
    ``prev_cum <= b_cut``, else C. Standard ABC (B1) — the boundary-crossing item
    lands in the HIGHER class and rank-1 (``prev_cum == 0``) is ALWAYS A, even when
    that single SKU alone exceeds the A cut. Deciding on the cumulative-INCLUSIVE
    share instead pushed a dominant rank-1 SKU into B (or C).
    """
    grand = sum(ranked_values)
    out: list[str] = []
    running = 0.0
    for value in ranked_values:
        prev_cum = (100.0 * running / grand) if grand else 0.0
        out.append("A" if prev_cum <= a_cut else ("B" if prev_cum <= b_cut else "C"))
        running += value
    return out


def xyz_class(cv: Optional[float], x_max: float, y_max: float) -> Optional[str]:
    if cv is None:
        return None
    if cv <= x_max:
        return "X"
    if cv <= y_max:
        return "Y"
    return "Z"


def _window_lo(as_of: date) -> date:
    """Inclusive lower bound of the demand window (as_of - WINDOW_DAYS)."""
    return as_of - timedelta(days=WINDOW_DAYS)


def _bucket_windows(as_of: date) -> list[tuple[date, date]]:
    """Newest-first ``(from, to)`` half-open bounds for each weekly bucket.

    Bucket i covers ``[as_of - 7*(i+1), as_of - 7*i)``; the oldest bucket is clamped
    to the 90-day window start so it is the short remainder. Index 0 is the most
    recent 7 days — the same ordering as the aggregated bucket lists.
    """
    lo = _window_lo(as_of)
    out: list[tuple[date, date]] = []
    for i in range(NUM_BUCKETS):
        to = as_of - timedelta(days=BUCKET_DAYS * i)
        frm = max(as_of - timedelta(days=BUCKET_DAYS * (i + 1)), lo)
        out.append((frm, to))
    return out


# ---------------------------------------------------------------------------
# Stage 1 — demand
# ---------------------------------------------------------------------------

def _ids(values: Optional[Iterable]) -> Optional[list[str]]:
    """Coerce an id list to text so ``col::text = ANY(:x)`` works for str OR UUID input."""
    return [str(v) for v in values] if values else None


def _demand_rows(db: Session, as_of: date, product_ids: Optional[list[str]]):
    """One row per (SKU, warehouse, demand_nature, weekly bucket) over the window.

    ``bucket_idx`` is 0 for the most recent 7 days and grows toward the oldest week:
    ``floor((as_of - day - 1) / 7)`` matches ``_bucket_windows`` exactly.
    """
    lo = _window_lo(as_of)
    pids = _ids(product_ids)
    sql = """
        SELECT product_id, warehouse_id, demand_nature,
          ((:as_of - day - 1) / {bw})::int AS bucket_idx,
          COALESCE(SUM(qty_out),0) AS qty
        FROM scm.consumption_v
        WHERE day >= :lo AND day < :as_of
        {pid}
        GROUP BY product_id, warehouse_id, demand_nature, bucket_idx
    """.format(bw=BUCKET_DAYS, pid="AND product_id::text = ANY(:pids)" if pids else "")
    params: dict[str, Any] = {"lo": lo, "as_of": as_of}
    if pids:
        params["pids"] = pids
    return db.execute(text(sql), params).fetchall()


def _k(pid, wid) -> tuple:
    """Canonical string key so UUID-from-DB and str-from-API inputs always match."""
    return (str(pid), str(wid) if wid is not None else None)


def _aggregate_demand(rows) -> dict:
    """(product_id, warehouse_id) -> {continuous:[w0..w12], spike:[...], combined:[...]}.

    Each list has NUM_BUCKETS weekly entries, newest-first (index 0 == most recent
    7 days), matching ``_bucket_windows`` ordering.
    """
    keys: dict[tuple, dict] = {}
    for r in rows:
        key = _k(r.product_id, r.warehouse_id)
        acc = keys.setdefault(key, {"continuous": [0.0] * NUM_BUCKETS,
                                    "spike": [0.0] * NUM_BUCKETS})
        channel = "spike" if r.demand_nature == "spike" else "continuous"
        idx = int(r.bucket_idx)
        idx = 0 if idx < 0 else (NUM_BUCKETS - 1 if idx >= NUM_BUCKETS else idx)
        acc[channel][idx] += float(r.qty)
    for acc in keys.values():
        acc["combined"] = [acc["continuous"][i] + acc["spike"][i] for i in range(NUM_BUCKETS)]
    return keys


def _planning_keys(db: Session, product_ids: Optional[list[str]]):
    sql = "SELECT product_id, warehouse_id FROM scm.net_position_v"
    params: dict[str, Any] = {}
    pids = _ids(product_ids)
    if pids:
        sql += " WHERE product_id::text = ANY(:pids)"
        params["pids"] = pids
    return db.execute(text(sql), params).fetchall()


def _upsert_demand_stat(db: Session, key, stats, now):
    # Delete-then-insert per key (not ON CONFLICT): warehouse_id is nullable and
    # Postgres treats NULLs as DISTINCT, so an ``ON CONFLICT (product_id, warehouse_id)``
    # never fires for network-level (warehouse_id IS NULL) rows and they duplicate every
    # run — multiplying the dashboard LEFT JOIN. ``IS NOT DISTINCT FROM`` matches the
    # null-warehouse row so this stays idempotent for both keyed and network rows (S2).
    db.execute(text(
        "DELETE FROM scm.demand_stat WHERE product_id = :pid "
        "AND warehouse_id IS NOT DISTINCT FROM :wid"
    ), {"pid": key[0], "wid": key[1]})
    db.execute(text("""
        INSERT INTO scm.demand_stat
          (id, product_id, warehouse_id, avg_daily_demand, baseline_rate, spike_rate,
           demand_cv, variability, window_days, sample_days, method, channel_split,
           computed_at, source_system, source_ref, created_at)
        VALUES (:id, :pid, :wid, :add, :base, :spike, :cv, :var, :win, :sample,
                :method, CAST(:split AS jsonb), :now, :src, 'run', now())
    """), {"id": str(uuid.uuid4()), **stats, "now": now, "src": _SEED,
           "pid": key[0], "wid": key[1]})


def _demand_stat_payload(agg: Optional[dict], policy: dict) -> dict:
    """Build the persisted demand_stat values from a key's aggregated buckets."""
    if agg is None:
        return {"add": 0.0, "base": 0.0, "spike": 0.0, "cv": None, "var": None,
                "win": WINDOW_DAYS, "sample": 0, "method": "insufficient_data",
                "split": _json({"continuous": {"qty": 0}, "spike": {"qty": 0},
                                "coverage": "no_outflow"})}
    combined = bucket_stats(agg["combined"], policy["x"], policy["y"], BUCKET_DAY_LENGTHS)
    cont_total = float(sum(agg["continuous"]))
    spike_total = float(sum(agg["spike"]))
    add = round(combined["baseline_total"] / WINDOW_DAYS, 6)
    base = round(cont_total / WINDOW_DAYS, 6)
    spike = round(spike_total / WINDOW_DAYS, 6)
    cv = round(combined["cv"], 6)
    split = {
        "continuous": {"qty": cont_total, "daily": base, "buckets": agg["continuous"]},
        "spike": {"qty": spike_total, "daily": spike, "buckets": agg["spike"]},
        "total_qty": combined["total"],
    }
    return {"add": add, "base": base, "spike": spike, "cv": cv,
            "var": round(_st.pstdev(agg["combined"]), 6),
            "win": WINDOW_DAYS, "sample": NUM_BUCKETS, "method": combined["method"],
            "split": _json(split)}


def _json(obj) -> str:
    import json
    return json.dumps(obj, default=str)  # UUIDs / dates -> str


# ---------------------------------------------------------------------------
# Stage 2 — classification (ABC always ranked over the full costed universe)
# ---------------------------------------------------------------------------

def _abc_map(db: Session, as_of: date, policy: dict) -> dict:
    """(product_id, warehouse_id) -> abc_class, ranked GLOBALLY by trailing-12mo value.

    Always spans the whole costed universe (independent of scope) so a scoped run
    yields the same class a full run would. Null-cost keys are simply absent here
    (=> classified 'unknown'/NULL by the caller).
    """
    lo = as_of - timedelta(days=ANNUAL_DAYS)
    rows = db.execute(text("""
        SELECT ol.product_id, ol.warehouse_id,
               SUM(ol.quantity * p.cost_price) AS annual_value
        FROM order_lines ol JOIN orders o ON o.id = ol.order_id
        JOIN products p ON p.id = ol.product_id
        WHERE o.is_cancelled = false AND o.order_date >= :lo AND o.order_date < :as_of
          AND p.cost_price IS NOT NULL AND p.cost_price > 0
        GROUP BY ol.product_id, ol.warehouse_id
    """), {"lo": lo, "as_of": as_of}).fetchall()
    ranked = sorted(
        ((float(r.annual_value), r.product_id, r.warehouse_id) for r in rows),
        key=lambda t: (-t[0], str(t[1]), str(t[2] or "")),
    )
    letters = abc_classify([v for v, _, _ in ranked], policy["a"], policy["b"])
    out: dict[tuple, dict] = {}
    for (value, pid, wid), abc in zip(ranked, letters):
        out[_k(pid, wid)] = {"abc": abc, "annual_value": value}
    return out


def _upsert_classification(db: Session, key, abc, xyz, annual_value, cv, now):
    # Delete-then-insert per key so network-level (warehouse_id IS NULL) rows stay
    # idempotent across re-runs — see _upsert_demand_stat for why ON CONFLICT can't
    # dedupe a nullable warehouse_id (S2).
    db.execute(text(
        "DELETE FROM scm.item_classification WHERE product_id = :pid "
        "AND warehouse_id IS NOT DISTINCT FROM :wid"
    ), {"pid": key[0], "wid": key[1]})
    db.execute(text("""
        INSERT INTO scm.item_classification
          (id, product_id, warehouse_id, abc_class, xyz_class, annual_value, demand_cv,
           computed_at, source_system, source_ref, created_at)
        VALUES (:id, :pid, :wid, :abc, :xyz, :av, :cv, :now, :src, 'run', now())
    """), {"id": str(uuid.uuid4()), "pid": key[0], "wid": key[1], "abc": abc,
           "xyz": xyz, "av": annual_value, "cv": cv, "now": now, "src": _SEED})


# ---------------------------------------------------------------------------
# Stage 3 — supplier performance
# ---------------------------------------------------------------------------

def _completing_receipts(db: Session, supplier_ids: Optional[list[str]],
                         product_ids: Optional[list[str]]):
    """One row per PO line that reached full receipt, keyed to its COMPLETING GR.

    Reads PO -> picking (goods_received) the way ``scm.receipt_lead_v`` does, but
    resolves the *completing* receipt: order picking lines of a PO line by
    picking_date and pick the receipt at which cumulative picked qty first reaches
    qty_ordered. lead_days measured from PO issue_date to that receipt; on-time vs
    the PO line's expected_date. reject/received summed across ALL of the line's GRs.
    """
    filters = ["ph.picking_type = 'goods_received'",
               "ph.source_entity_type = 'purchase_order'"]
    params: dict[str, Any] = {}
    sids, pids = _ids(supplier_ids), _ids(product_ids)
    if sids:
        filters.append("po.supplier_id::text = ANY(:sids)")
        params["sids"] = sids
    if pids:
        filters.append("pol.product_id::text = ANY(:pids)")
        params["pids"] = pids
    where = " AND ".join(filters)
    rows = db.execute(text(f"""
        SELECT pol.id AS po_line_id, po.supplier_id, pol.product_id,
               po.issue_date, COALESCE(pol.expected_date, po.expected_date) AS expected_date,
               pol.qty_ordered, ph.picking_date,
               COALESCE(pl.quantity_picked, 0) AS quantity_picked,
               COALESCE(pl.qty_accepted, 0) AS qty_accepted,
               COALESCE(pl.qty_rejected, 0) AS qty_rejected
        FROM picking_lines pl
        JOIN picking_headers ph ON ph.id = pl.picking_header_id
        JOIN purchase_order_lines pol ON pol.id = pl.po_line_id
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        WHERE {where}
        ORDER BY pol.id, ph.picking_date, ph.picking_number
    """), params).fetchall()

    # fold GRs per PO line -> completing receipt
    lines: dict[str, dict] = {}
    for r in rows:
        acc = lines.setdefault(str(r.po_line_id), {
            "supplier_id": r.supplier_id, "product_id": r.product_id,
            "issue_date": r.issue_date, "expected_date": r.expected_date,
            "qty_ordered": float(r.qty_ordered or 0),
            "grs": [],
        })
        acc["grs"].append(r)
    return lines


def _line_metrics(line: dict, grace: int) -> Optional[dict]:
    """Per completed PO line: lead time (completing GR), on_time, received/rejected."""
    qty_ordered = line["qty_ordered"]
    grs = line["grs"]
    total_received = sum(float(g.quantity_picked) for g in grs)
    total_accepted = sum(float(g.qty_accepted) for g in grs)
    total_rejected = sum(float(g.qty_rejected) for g in grs)
    # completing receipt = first GR at which cumulative picked reaches qty_ordered
    cumulative = 0.0
    completing = None
    for g in grs:
        cumulative += float(g.quantity_picked)
        if qty_ordered > 0 and cumulative >= qty_ordered:
            completing = g
            break
    if completing is None:
        return None  # never fully received -> not a supplier-perf sample yet
    lead = (completing.picking_date - line["issue_date"]).days if line["issue_date"] else None
    on_time = None
    if line["expected_date"] is not None:
        on_time = completing.picking_date <= line["expected_date"] + timedelta(days=grace)
    return {"supplier_id": line["supplier_id"], "product_id": line["product_id"],
            "lead": lead, "on_time": on_time, "ordered": qty_ordered,
            "received": total_received, "accepted": total_accepted, "rejected": total_rejected,
            "receipt_date": completing.picking_date, "issue_date": line["issue_date"]}


def _score(samples: list[dict], policy: dict) -> Optional[dict]:
    """Aggregate a set of completed-line samples into a scorecard."""
    if not samples:
        return None
    leads = [s["lead"] for s in samples if s["lead"] is not None]
    on_flags = [s["on_time"] for s in samples if s["on_time"] is not None]
    sum_received = sum(s["received"] for s in samples)
    sum_ordered = sum(s["ordered"] for s in samples)
    sum_rejected = sum(s["rejected"] for s in samples)
    on_time_rate = (sum(1 for f in on_flags if f) / len(on_flags)) if on_flags else None
    reject_rate = (sum_rejected / sum_received) if sum_received else 0.0
    fill_rate = (sum_received / sum_ordered) if sum_ordered else None
    composite = None
    if on_time_rate is not None:
        composite = policy["dw"] * on_time_rate + policy["qw"] * (1.0 - reject_rate)
    return {
        "sample_size": len(samples),
        "on_time_rate": round(on_time_rate, 6) if on_time_rate is not None else None,
        "avg_lead_time_days": round(_st.mean(leads), 6) if leads else None,
        "lead_time_variance": round(_st.pvariance(leads), 6) if len(leads) >= 1 else None,
        "reject_rate": round(reject_rate, 6),
        "fill_rate": round(fill_rate, 6) if fill_rate is not None else None,
        "composite_score": round(composite, 6) if composite is not None else None,
        # ``purchase_orders.issue_date`` / receipt dates are nullable — a group whose
        # completing receipts all have null dates must yield a null period, never crash
        # ``min()``/``max()`` on an empty sequence (B2).
        "period_start": min((s["issue_date"] for s in samples if s["issue_date"]), default=None),
        "period_end": max((s["receipt_date"] for s in samples if s["receipt_date"]), default=None),
    }


def _upsert_supplier_performance(db: Session, supplier_id, product_id, score,
                                 confidence, sample_size, now):
    # hard delete the prior row for this exact key then insert (no unique constraint
    # on supplier x product in the schema, so upsert-by-delete keeps it idempotent)
    db.execute(text(
        "DELETE FROM scm.supplier_performance WHERE supplier_id = :sid "
        "AND product_id IS NOT DISTINCT FROM :pid"
    ), {"sid": supplier_id, "pid": product_id})
    db.execute(text("""
        INSERT INTO scm.supplier_performance
          (id, supplier_id, product_id, period_start, period_end, on_time_rate,
           avg_lead_time_days, lead_time_variance, reject_rate, fill_rate,
           composite_score, sample_size, confidence, computed_at, source_system,
           source_ref, created_at)
        VALUES (:id, :sid, :pid, :ps, :pe, :otr, :alt, :ltv, :rr, :fr, :cs,
                :ss, :conf, :now, :src, 'run', now())
    """), {"id": str(uuid.uuid4()), "sid": supplier_id, "pid": product_id,
           "ps": score["period_start"] if score else None,
           "pe": score["period_end"] if score else None,
           "otr": score["on_time_rate"] if score else None,
           "alt": score["avg_lead_time_days"] if score else None,
           "ltv": score["lead_time_variance"] if score else None,
           "rr": score["reject_rate"] if score else None,
           "fr": score["fill_rate"] if score else None,
           "cs": score["composite_score"] if score else None,
           "ss": sample_size, "conf": confidence, "now": now, "src": _SEED})


def _compute_supplier_performance(db: Session, as_of, supplier_ids, product_ids,
                                  policy, now) -> int:
    lines = _completing_receipts(db, supplier_ids, product_ids)
    # bucket completed-line metrics by supplier and supplier x product
    by_supplier: dict[str, list[dict]] = {}
    by_pair: dict[tuple, list[dict]] = {}
    for line in lines.values():
        m = _line_metrics(line, policy["grace"])
        if m is None:
            continue
        # A receipt line with no supplier cannot be attributed. Skip it rather
        # than bucketing under str(None) == "None", which later reaches
        # `supplier_id = :sid` on a uuid column and aborts the whole run with
        # `invalid input syntax for type uuid: "None"`.
        supplier_id = m.get("supplier_id")
        if supplier_id is None:
            continue
        sid = str(supplier_id)
        product_id = m.get("product_id")
        by_supplier.setdefault(sid, []).append(m)
        # product_id may legitimately be NULL — keep it as None so the
        # `IS NOT DISTINCT FROM` delete matches the supplier-level row.
        by_pair.setdefault(
            (sid, str(product_id) if product_id is not None else None), []
        ).append(m)

    written = 0
    supplier_scores: dict[str, Optional[dict]] = {}
    # supplier-level aggregate rows (product_id NULL)
    for sid, samples in by_supplier.items():
        score = _score(samples, policy)
        supplier_scores[sid] = score
        confidence = "high" if len(samples) >= policy["min_sample"] else "low"
        _upsert_supplier_performance(db, sid, None, score, confidence, len(samples), now)
        written += 1
        if score and score["composite_score"] is not None:
            db.execute(text(
                "UPDATE suppliers SET current_performance_score = :s WHERE id = :id"
            ), {"s": score["composite_score"], "id": sid})

    # supplier x product rows (min-sample fallback to supplier-level)
    for (sid, pid), samples in by_pair.items():
        if len(samples) >= policy["min_sample"]:
            score = _score(samples, policy)
            confidence = "high"
        else:
            supplier_total = len(by_supplier.get(sid, []))
            score = supplier_scores.get(sid) or _score(by_supplier.get(sid, []), policy)
            confidence = "medium" if supplier_total >= policy["min_sample"] else "low"
        _upsert_supplier_performance(db, sid, pid, score, confidence, len(samples), now)
        written += 1
    return written


def refresh_supplier_performance(db: Session, supplier_id: str,
                                 product_id: Optional[str] = None,
                                 config: Optional[dict] = None) -> int:
    """On-GR hook (AC-M2.11): recompute ONLY one supplier (optionally one product),
    never the whole catalog. Commits its own transaction."""
    ensure_policy_defaults(db)
    policy = _supplier_policy(db)
    as_of = _as_of(config)
    now = datetime.utcnow()
    written = _compute_supplier_performance(
        db, as_of, [supplier_id], [product_id] if product_id else None, policy, now)
    db.commit()
    return written


def on_goods_receipt_posted(db: Session, supplier_id: str,
                            product_id: Optional[str] = None,
                            config: Optional[dict] = None) -> int:
    """On-GR trigger (AC-M2.11): after a PO-linked goods-receipt is posted, recompute
    ONLY the affected supplier×product ``supplier_performance`` (never a full run).

    Best-effort: a scoring failure is logged and swallowed (session rolled back) so it
    can NEVER roll back or block the GR commit that triggered it. Returns the number of
    ``supplier_performance`` rows written (0 on failure).

    INTEGRATION POINT — where this attaches:
      Call this AFTER a goods-receipt (``picking_headers.picking_type='goods_received'``
      with ``source_entity_type='purchase_order'``) and its ``qty_received`` /
      ``qty_accepted`` are committed, passing that GR's ``po.supplier_id`` and the
      received line's ``product_id``.

      No runtime "create GR from PO" flow exists in this branch yet — that lands in
      **M4 (create-GR-from-PO)**. Until then the only writers of the SCM PO→GR link are
      ``scripts/seed_scm_demo.py`` and the M2 tests, and the nightly ``scm_analytics``
      full run keeps supplier scores fresh. When M4's post-GR service method lands, wire
      this call at the end of it (after commit), scoped to the received supplier×product.
    """
    import logging as _logging
    log = _logging.getLogger(__name__)
    try:
        return refresh_supplier_performance(db, supplier_id, product_id, config=config)
    except Exception:  # noqa: BLE001 — GR posting must not be blocked by scoring
        log.exception(
            "on_goods_receipt_posted: supplier=%s product=%s refresh failed",
            supplier_id, product_id,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return 0


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _as_of(config: Optional[dict]) -> date:
    if config and config.get("as_of"):
        v = config["as_of"]
        return v if isinstance(v, date) else date.fromisoformat(str(v))
    return date.today()


def _channel_coverage_pct(db: Session, as_of: date, product_ids) -> Optional[float]:
    """% of window outflow qty attributable to a TAGGED segment (non-null demand_nature)."""
    lo = _window_lo(as_of)
    pids = _ids(product_ids)
    sql = """
        SELECT COALESCE(SUM(qty_out),0) AS total,
               COALESCE(SUM(qty_out) FILTER (WHERE demand_nature IS NOT NULL),0) AS tagged
        FROM scm.consumption_v WHERE day >= :lo AND day < :as_of {pid}
    """.format(pid="AND product_id::text = ANY(:pids)" if pids else "")
    params: dict[str, Any] = {"lo": lo, "as_of": as_of}
    if pids:
        params["pids"] = pids
    row = db.execute(text(sql), params).fetchone()
    if row is None:
        return None
    total = float(row.total or 0)
    if total <= 0:
        return None
    return round(100.0 * float(row.tagged or 0) / total, 2)


def run_analytics(db: Session, scope: Optional[dict] = None,
                  config: Optional[dict] = None) -> dict:
    """Compute demand + classification + supplier performance over a shared window.

    ``scope`` (optional): ``product_ids`` / ``warehouse_ids`` / ``supplier_ids`` to
    restrict the run (ABC ranking still spans the full costed universe so classes are
    stable). ``config`` (optional): ``as_of`` (date) — default today. Writes one
    ``scm.scm_analytics_run`` row and returns its summary. Commits.
    """
    scope = scope or {}
    product_ids = scope.get("product_ids")
    supplier_ids = scope.get("supplier_ids")
    as_of = _as_of(config)
    started = datetime.utcnow()
    run_id = str(uuid.uuid4())

    # open the run log first so a crash still leaves a 'running'/'failed' trace.
    # `company_id` is stamped by hand: this is raw SQL, so the ORM `before_insert`
    # hook never fires, and an analytics run with a NULL company is hidden from
    # every scoped read of the table it just wrote.
    db.execute(text(
        "INSERT INTO scm.scm_analytics_run "
        "(id, started_at, status, scope, window_days, config_ref, source_system, source_ref, "
        "company_id, created_at) "
        "VALUES (:id, :started, 'running', CAST(:scope AS jsonb), :win, :cfg, :src, 'run', "
        ":company_id, now())"
    ), {"id": run_id, "started": started, "scope": _json(scope),
        "win": WINDOW_DAYS, "cfg": as_of.isoformat(), "src": _SEED,
        # `ambiguous=DEFAULT_COMPANY_ID`: the nightly recompute runs on the scheduler,
        # which has no request and therefore no scope at all, and a run that refused to
        # start would take the whole night's analytics with it. One recompute serves the
        # whole install today; a per-company nightly run is its own slice.
        "company_id": resolve_write_company_id(
            get_company_scope(db), ambiguous=DEFAULT_COMPANY_ID)})
    db.commit()

    try:
        ensure_policy_defaults(db)
        abc_policy = _abc_xyz_policy(db)
        sup_policy = _supplier_policy(db)
        now = datetime.utcnow()

        # --- demand ---
        demand_agg = _aggregate_demand(_demand_rows(db, as_of, product_ids))
        keys = [_k(r.product_id, r.warehouse_id) for r in _planning_keys(db, product_ids)]
        # include any consumption key not in net_position_v (defensive) so nothing is dropped
        seen = set(keys)
        for k in demand_agg:
            if k not in seen:
                keys.append(k)
                seen.add(k)
        demand_count = 0
        for key in keys:
            payload = _demand_stat_payload(demand_agg.get(key), abc_policy)
            _upsert_demand_stat(db, key, payload, now)
            demand_count += 1

        # --- classification ---
        abc_map = _abc_map(db, as_of, abc_policy)
        class_count = 0
        for key in keys:
            agg = demand_agg.get(key)
            cv = None
            if agg is not None:
                cv = round(bucket_stats(agg["combined"], abc_policy["x"], abc_policy["y"], BUCKET_DAY_LENGTHS)["cv"], 6)
            abc_entry = abc_map.get(key)
            abc = abc_entry["abc"] if abc_entry else None  # null-cost -> unknown
            annual_value = abc_entry["annual_value"] if abc_entry else None
            xyz = xyz_class(cv, abc_policy["x"], abc_policy["y"])
            _upsert_classification(db, key, abc, xyz, annual_value, cv, now)
            class_count += 1

        # --- supplier performance ---
        supplier_count = _compute_supplier_performance(
            db, as_of, supplier_ids, product_ids, sup_policy, now)

        coverage = _channel_coverage_pct(db, as_of, product_ids)
        finished = datetime.utcnow()
        counts = {
            "demand_stat": demand_count,
            "item_classification": class_count,
            "supplier_performance": supplier_count,
            "planning_skus": len(keys),
            "channel_coverage_pct": coverage,
            "duration_ms": int((finished - started).total_seconds() * 1000),
        }
        db.execute(text(
            "UPDATE scm.scm_analytics_run SET finished_at=:fin, status='completed', "
            "counts=CAST(:counts AS jsonb) WHERE id=:id"
        ), {"fin": finished, "counts": _json(counts), "id": run_id})
        db.commit()
        return {"run_id": run_id, "status": "completed", "window_days": WINDOW_DAYS,
                "as_of": as_of.isoformat(), "counts": counts}
    except Exception as exc:  # noqa: BLE001 — record then re-raise
        db.rollback()
        db.execute(text(
            "UPDATE scm.scm_analytics_run SET finished_at=now(), status='failed', "
            "error_text=:err WHERE id=:id"
        ), {"err": str(exc)[:2000], "id": run_id})
        db.commit()
        raise


# ---------------------------------------------------------------------------
# Explain (deterministic debug — AC-M2.13)
# ---------------------------------------------------------------------------

def _demand_dos(db: Session, as_of: date, product_id: str,
                warehouse_id: Optional[str]) -> list[dict]:
    """M8-A2 — the delivery orders (DOs) that drove the outflow in the demand window,
    as a navigable list (one row per DO: order id + DO number + date + qty out).

    ``scm.consumption_v`` carries no order id, so this hits the base ``orders`` /
    ``order_lines`` tables directly with the SAME window + cancellation filter the demand
    aggregation uses (``is_cancelled = false``, ``order_date::date`` within
    ``[as_of - WINDOW_DAYS, as_of)``). Filtered to ``warehouse_id`` when the cell has one;
    otherwise all of the product's DOs in the window. Newest DO first."""
    lo = _window_lo(as_of)
    wh = "AND ol.warehouse_id = :wid" if warehouse_id else ""
    params: dict[str, Any] = {"pid": product_id, "lo": lo, "as_of": as_of}
    if warehouse_id:
        params["wid"] = warehouse_id
    rows = db.execute(text(f"""
        SELECT o.id AS order_id, o.order_number AS do_number,
               o.order_date, COALESCE(SUM(ol.quantity), 0) AS qty_out
        FROM order_lines ol
        JOIN orders o ON o.id = ol.order_id
        WHERE o.is_cancelled = false
          AND ol.product_id = :pid
          AND o.order_date::date >= :lo AND o.order_date::date < :as_of
          {wh}
        GROUP BY o.id, o.order_number, o.order_date
        ORDER BY o.order_date DESC NULLS LAST
    """), params).mappings().all()
    return [{
        "order_id": str(r["order_id"]),
        "do_number": r["do_number"],
        "order_date": r["order_date"].isoformat() if r["order_date"] else None,
        "qty_out": float(r["qty_out"] or 0.0),
    } for r in rows]


def explain_demand(db: Session, product_id: str, warehouse_id: Optional[str],
                   config: Optional[dict] = None) -> dict:
    """Deterministically re-derive one SKU's demand working: window, per-week sample
    points, channel split, method, CV. Same inputs => identical output (no writes).

    M8-A2: also carries ``demand_dos`` — the delivery orders behind the outflow in the
    window as a navigable list (so days-cover demand reads as real DOs, not raw weekly
    buckets)."""
    as_of = _as_of(config)
    policy = _abc_xyz_policy(db)
    windows = _bucket_windows(as_of)  # newest-first (from, to)
    # present oldest->newest for reading (index NUM_BUCKETS-1 down to 0)
    order = list(reversed(range(NUM_BUCKETS)))
    rows = _demand_rows(db, as_of, [product_id])
    demand_dos = _demand_dos(db, as_of, product_id, warehouse_id)
    agg = _aggregate_demand(rows).get(_k(product_id, warehouse_id))
    if agg is None:
        return {
            "product_id": product_id, "warehouse_id": warehouse_id,
            "as_of": as_of.isoformat(), "window_days": WINDOW_DAYS,
            "num_buckets": NUM_BUCKETS,
            "buckets": [{"from": windows[i][0].isoformat(), "to": windows[i][1].isoformat(),
                         "qty": 0.0} for i in order],
            "combined": [0.0] * NUM_BUCKETS, "continuous": [0.0] * NUM_BUCKETS,
            "spike": [0.0] * NUM_BUCKETS, "method": "insufficient_data",
            "method_reason": "no outflow in the window",
            "band": None, "demand_cv": None, "avg_daily_demand": 0.0,
            "baseline_rate": 0.0, "spike_rate": 0.0,
            "demand_dos": demand_dos,
        }
    combined = bucket_stats(agg["combined"], policy["x"], policy["y"], BUCKET_DAY_LENGTHS)
    return {
        "product_id": product_id, "warehouse_id": warehouse_id,
        "as_of": as_of.isoformat(), "window_days": WINDOW_DAYS, "num_buckets": NUM_BUCKETS,
        "buckets": [{"from": windows[i][0].isoformat(), "to": windows[i][1].isoformat(),
                     "qty": agg["combined"][i]} for i in order],
        "combined": agg["combined"], "continuous": agg["continuous"], "spike": agg["spike"],
        "total": combined["total"], "method": combined["method"],
        "method_reason": combined["method_reason"], "band": combined["band"],
        "demand_cv": round(combined["cv"], 6),
        "baseline_total": round(combined["baseline_total"], 6),
        "avg_daily_demand": round(combined["baseline_total"] / WINDOW_DAYS, 6),
        "baseline_rate": round(sum(agg["continuous"]) / WINDOW_DAYS, 6),
        "spike_rate": round(sum(agg["spike"]) / WINDOW_DAYS, 6),
        "demand_dos": demand_dos,
    }
