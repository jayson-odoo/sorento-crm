"""The reorder level: the number the buyer owns, and the movement that suggests it.

The forecast basis sizes an order from `avg_daily_demand` over a rolling window and 51 days
of cover. It is a correct policy and it stays selectable. It is not how Sorento buys: a
2-unit project order produced a 15.933 recommendation, because the order played no part in
the number.

What the buyer actually does is hold a level per item per location, look at the position, and
order the difference. So the level is stored, owned, and editable, and the movement history
only ever SUGGESTS it. The suggestion is kept in its own column beside the stored level and
is never merged into it - an engine that quietly replaces the buyer's number is the thing
that made the forecast basis unusable.

Movement is read from `scm.consumption_v` (delivery-order lines), not from open orders:
what actually left the building is the business's own rule for setting a level, and open
orders are demand, netted elsewhere.

The suggestion itself is the industry formula (captain, 27 Aug):

    ADU   = delivery-order quantity over the last 90 days / 90, every warehouse
    level = ADU x lead_time + ADU x 14        (14 days of safety), rounded up

It replaces the older `avg monthly movement x cover months`, which sized a level off a
cover window nobody could point at a supplier for. The lead time is the product's own
supplier lead time; 30 days when nobody knows one.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException

# The months of movement the popover charts behind the suggestion. Overridable per policy
# scope; this is only the fallback for a policy row that has not set it.
DEFAULT_STUDY_MONTHS = 3

#: The study window ADU is averaged over: 90 days of delivery orders (captain, 27 Aug).
LEVEL_WINDOW_DAYS = 90
#: Days of safety stock carried on top of the lead time's demand.
LEVEL_SAFETY_DAYS = 14.0
#: What a lead time is worth when the product has no supplier lead time on file.
DEFAULT_LEAD_TIME_DAYS = 30.0

# Written into `source` so a later reader can tell an accepted suggestion from a typed number.
SOURCE_MANUAL = "manual"
SOURCE_ACCEPTED = "accepted_suggestion"
VALID_SOURCES = (SOURCE_MANUAL, SOURCE_ACCEPTED)

_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


# --- movement ---------------------------------------------------------------------------

def monthly_movement(db: Session, product_ids: list[str],
                     warehouse_ids: Optional[list[str]] = None,
                     *, months: int = DEFAULT_STUDY_MONTHS,
                     as_of: Optional[date] = None) -> dict[str, list[dict[str, Any]]]:
    """Quantity that left each product, by calendar month, newest month last.

    Keyed by product id. Months with no movement are present with 0 rather than absent, so
    "sold nothing in June" and "we have no June" cannot be confused on the way to a UI.
    """
    if not product_ids:
        return {}
    n = max(1, int(months or DEFAULT_STUDY_MONTHS))
    today = as_of or date.today()
    # Whole calendar months back from the start of the current one, so a run on the 2nd is
    # not comparing a 2-day month against three full ones.
    start_month = _add_months(date(today.year, today.month, 1), -n)

    where_wh = ""
    params: dict[str, Any] = {"pids": _texts(product_ids), "start": start_month,
                              "end": date(today.year, today.month, 1)}
    if warehouse_ids:
        where_wh = " AND c.warehouse_id = ANY(CAST(:whs AS uuid[]))"
        params["whs"] = _texts(warehouse_ids)

    rows = db.execute(text(f"""
        SELECT c.product_id::text AS product_id,
               date_trunc('month', c.day)::date AS month,
               COALESCE(sum(c.qty_out), 0) AS qty
          FROM scm.consumption_v c
         WHERE c.product_id = ANY(CAST(:pids AS uuid[]))
           AND c.day >= :start AND c.day < :end
           {where_wh}
         GROUP BY 1, 2
    """), params).mappings().all()

    buckets = [_add_months(start_month, i) for i in range(n)]
    out: dict[str, list[dict[str, Any]]] = {
        pid: [{"month": m.isoformat()[:7], "qty": 0.0} for m in buckets]
        for pid in _texts(product_ids)
    }
    index = {m: i for i, m in enumerate(buckets)}
    for r in rows:
        slot = index.get(r["month"])
        if slot is None:
            continue
        out.setdefault(r["product_id"], [{"month": m.isoformat()[:7], "qty": 0.0}
                                         for m in buckets])[slot]["qty"] = float(r["qty"] or 0)
    return out


def _texts(values: Optional[Iterable[Any]]) -> list[str]:
    """Ids as text. Callers hold UUID objects (a run's product_ids), and psycopg2 adapts a
    list of them as ``uuid[]`` - which has no operator against the ``::text`` cast these
    queries compare on, so the whole planning read dies with "text = uuid"."""
    return [str(v) for v in (values or [])]


def _add_months(d: date, delta: int) -> date:
    total = (d.year * 12 + (d.month - 1)) + delta
    return date(total // 12, total % 12 + 1, 1)


# --- suggestion -------------------------------------------------------------------------

def average_daily_usage(db: Session, product_ids: list[str], *,
                        window_days: int = LEVEL_WINDOW_DAYS,
                        as_of: Optional[date] = None) -> dict[str, dict[str, Any]]:
    """Delivery-order quantity per day over the window, EVERY warehouse, per product.

    The reorder level is a product fact (captain, 27 Aug: "our reorder is per product, so
    it doesn't matter your location"), so the usage behind it is read across the network
    rather than per bin. `scm.consumption_v` is the delivery-order book - `orders` /
    `order_lines`, cancelled orders excluded - which covers far more of the catalogue than
    the sales-order lines do.

    The window is the `window_days` days BEFORE `as_of` (`day >= as_of - n`, `day < as_of`):
    a part-day today would drag the average down for no reason anyone could explain.
    """
    if not product_ids:
        return {}
    n = max(1, int(window_days or LEVEL_WINDOW_DAYS))
    until = as_of or date.today()
    since = until - timedelta(days=n)
    rows = db.execute(text("""
        SELECT c.product_id::text AS product_id, COALESCE(sum(c.qty_out), 0) AS qty
          FROM scm.consumption_v c
         WHERE c.product_id = ANY(CAST(:pids AS uuid[]))
           AND c.day >= :since AND c.day < :until
         GROUP BY 1
    """), {"pids": _texts(product_ids), "since": since, "until": until}).mappings().all()

    moved = {r["product_id"]: float(r["qty"] or 0) for r in rows}
    return {
        pid: {
            "window_qty": round(moved.get(pid, 0.0), 4),
            "window_days": n,
            "adu": round(moved.get(pid, 0.0) / n, 6),
            "since": since.isoformat(),
            "until": until.isoformat(),
        }
        for pid in _texts(product_ids)
    }


def suggest_level_from_usage(*, adu: float, lead_time_days: Optional[float],
                             safety_days: float = LEVEL_SAFETY_DAYS,
                             window_days: int = LEVEL_WINDOW_DAYS,
                             window_qty: Optional[float] = None,
                             months: Optional[list[dict[str, Any]]] = None,
                             lead_time_source: Optional[str] = None) -> dict[str, Any]:
    """`ADU x lead_time + ADU x 14`, rounded up to a whole unit (captain, 27 Aug).

    Returns the level AND the arithmetic. A suggestion the buyer cannot argue with is a
    suggestion they will not trust, so every term that produced the number travels with it
    and the popover reads the three of them back.

    An unknown lead time is 30 days - a number the business can point at, rather than a
    zero that would quietly suggest holding nothing but safety stock.
    """
    rate = max(float(adu or 0.0), 0.0)
    lead = float(lead_time_days) if lead_time_days else DEFAULT_LEAD_TIME_DAYS
    if lead <= 0:
        lead = DEFAULT_LEAD_TIME_DAYS
    safety = float(safety_days if safety_days is not None else LEVEL_SAFETY_DAYS)
    safety_stock = rate * safety
    raw = rate * lead + safety_stock
    level = float(math.ceil(raw)) if raw > 0 else 0.0
    return {
        "level": round(level, 4),
        "basis": {
            "adu": round(rate, 6),
            "lead_time_days": round(lead, 4),
            "lead_time_source": lead_time_source or ("supplier" if lead_time_days else "default"),
            "safety_days": round(safety, 4),
            "safety_stock": round(safety_stock, 4),
            "window_days": int(window_days),
            "window_qty": round(float(window_qty), 4) if window_qty is not None else None,
            "raw_level": round(raw, 4),
            # The months behind the average, for the popover's bar chart. Evidence only:
            # the arithmetic above reads the 90-day window, never these buckets.
            "months": list(months or []),
            # Said explicitly so a 0 reads as "nothing moved", never as "not computed".
            "no_movement": rate <= 0,
        },
    }



# --- storage ----------------------------------------------------------------------------

def get_levels(db: Session, product_ids: list[str],
               warehouse_ids: Optional[list[str]] = None) -> dict[tuple[str, Optional[str]], dict]:
    """Stored levels keyed by (product_id, warehouse_id). The product-wide row keys on None."""
    if not product_ids:
        return {}
    # `shared=True`: a level with no company is a house default that every company reads,
    # the same convention attachments use. Levels are only ever written stamped, so a NULL
    # row comes from a scope-less system write - and silently hiding it would look like the
    # save failed rather than like a scoping decision.
    co, co_params = company_sql_predicate(db, "rl.company_id", param_prefix="rlv",
                                          shared=True)
    where_wh = ""
    params: dict[str, Any] = {"pids": _texts(product_ids), **co_params}
    if warehouse_ids:
        # The product-wide row is always in scope: it is the fallback for every location.
        where_wh = " AND (rl.warehouse_id IS NULL OR rl.warehouse_id = ANY(CAST(:whs AS uuid[])))"
        params["whs"] = _texts(warehouse_ids)
    # DISTINCT ON, not a bare SELECT: `(product_id, warehouse_id)` is not unique - a stray
    # scope-less write (see `_existing`) can leave a second row behind - and a query with no
    # ORDER BY handed the plan whichever duplicate Postgres happened to read last. Preferring
    # the row with a LEVEL SET, then the most recently touched one, means a level-NULL
    # engine-suggestion duplicate never shadows the row that actually carries the number.
    rows = db.execute(text(f"""
        SELECT DISTINCT ON (rl.product_id, rl.warehouse_id)
               rl.id::text AS id, rl.product_id::text AS product_id,
               rl.warehouse_id::text AS warehouse_id, rl.level, rl.source,
               rl.suggested_level, rl.suggested_at, rl.suggestion_basis,
               rl.amended_level, rl.amended_at, rl.amended_by, rl.notes
          FROM scm.reorder_level rl
         WHERE rl.product_id = ANY(CAST(:pids AS uuid[]))
           {where_wh}
           {("AND " + co) if co else ""}
         ORDER BY rl.product_id, rl.warehouse_id,
                  (rl.level IS NULL) ASC, rl.updated_at DESC NULLS LAST, rl.created_at DESC
    """), params).mappings().all()
    return {(r["product_id"], r["warehouse_id"]): dict(r) for r in rows}


def resolve_level(levels: dict[tuple[str, Optional[str]], dict], product_id: str,
                  warehouse_id: Optional[str]) -> Optional[dict]:
    """The per-location row wins, but only when it actually carries a level. None when
    neither exists, which is NOT the same as a level of 0 and must not be planned as one.

    A per-location row with `level IS NULL` is not a competing level - it is an engine
    suggestion row (see `store_suggestion`), which writes `suggested_level` without ever
    setting `level`. Letting that row win produced `needs_level` for an item that has a
    perfectly good product-wide (AutoCount) level sitting one row down. So the LEVEL falls
    through to the product-wide row when the location row has none of its own; the location
    row's own suggestion/amendment fields are kept, because those genuinely are per-location.
    """
    if warehouse_id is not None:
        hit = levels.get((product_id, warehouse_id))
        wide = levels.get((product_id, None))
        if hit is not None:
            if hit.get("level") is not None or wide is None:
                return hit
            merged = dict(hit)
            merged["level"] = wide.get("level")
            merged["source"] = wide.get("source")
            return merged
        return wide
    return levels.get((product_id, None))


def upsert_level(db: Session, *, product_id: str, warehouse_id: Optional[str],
                 level: Optional[float], source: str = SOURCE_MANUAL,
                 notes: Optional[str] = None,
                 company_id: Optional[str] = None) -> dict:
    """Set the level a buyer owns. Leaves the suggestion columns alone."""
    if source not in VALID_SOURCES:
        raise AppException(status_code=422,
                           message=f"source must be one of {', '.join(VALID_SOURCES)}.")
    if level is not None and float(level) < 0:
        raise AppException(status_code=422, message="A reorder level cannot be negative.")
    row = _existing(db, product_id, warehouse_id, company_id)
    now = datetime.utcnow()
    if row is None:
        new_id = str(uuid.uuid4())
        db.execute(text("""
            INSERT INTO scm.reorder_level
                (id, product_id, warehouse_id, level, source, notes, company_id, created_at)
            VALUES (:id, :pid, :wid, :level, :source, :notes, :co, :now)
        """), {"id": new_id, "pid": product_id, "wid": warehouse_id, "level": level,
               "source": source, "notes": notes, "co": company_id, "now": now})
    else:
        db.execute(text("""
            UPDATE scm.reorder_level
               SET level = :level, source = :source, notes = :notes, updated_at = :now
             WHERE id = :id
        """), {"id": row["id"], "level": level, "source": source, "notes": notes, "now": now})
    db.commit()
    return _existing(db, product_id, warehouse_id, company_id) or {}


def store_suggestion(db: Session, *, product_id: str, warehouse_id: Optional[str],
                     suggested_level: float, basis: dict,
                     company_id: Optional[str] = None) -> None:
    """Write the suggestion WITHOUT touching the stored level.

    This is the whole point of keeping two columns. A refresh that moved `level` would be the
    engine deciding for the buyer, which is the behaviour this basis exists to end.

    Matched loosely on company (`strict_company=False`): a suggestion is a system-computed
    row, not a buyer's owned figure, so the natural key is really `(product_id,
    warehouse_id)`. A prior refresh that ran scope-less left a `company_id IS NULL` row
    behind; matching strictly on the CURRENT call's company_id could never find it and kept
    inserting a fresh duplicate every refresh. Loose matching finds and UPDATES whichever row
    is already there (JOIN-based idempotent semantics - "set where mismatch", never "insert
    where absent", per the backfill lesson).
    """
    row = _existing(db, product_id, warehouse_id, company_id, strict_company=False)
    now = datetime.utcnow()
    payload = {"pid": product_id, "wid": warehouse_id, "sl": suggested_level,
               "basis": json.dumps(basis), "co": company_id, "now": now}
    if row is None:
        db.execute(text("""
            INSERT INTO scm.reorder_level
                (id, product_id, warehouse_id, suggested_level, suggested_at,
                 suggestion_basis, company_id, created_at)
            VALUES (:id, :pid, :wid, :sl, :now, CAST(:basis AS jsonb), :co, :now)
        """), {**payload, "id": str(uuid.uuid4())})
    else:
        # A fresh suggestion clears any amendment: the buyer amended THAT number, and
        # carrying their edit under a recomputed one would present a stale judgement as
        # current (S14).
        #
        # `company_id = COALESCE(company_id, :co)` heals a legacy scope-less row the moment
        # a scoped refresh touches it, instead of leaving it NULL-company forever - a row
        # this loose match keeps finding and re-updating every refresh. A row that already
        # carries a company keeps it; this never overwrites one company's row with another's.
        db.execute(text("""
            UPDATE scm.reorder_level
               SET suggested_level = :sl, suggested_at = :now,
                   suggestion_basis = CAST(:basis AS jsonb),
                   amended_level = NULL, amended_at = NULL, amended_by = NULL,
                   updated_at = :now,
                   company_id = COALESCE(company_id, :co)
             WHERE id = :id
        """), {**payload, "id": row["id"]})


def accept_suggestion(db: Session, *, product_id: str, warehouse_id: Optional[str],
                      company_id: Optional[str] = None) -> dict:
    """Copy the suggestion into the level the buyer owns, at the value it has right now."""
    row = _existing(db, product_id, warehouse_id, company_id)
    if row is None or row.get("suggested_level") is None:
        raise AppException(status_code=422,
                           message="There is no suggestion to accept for this item.")
    return upsert_level(db, product_id=product_id, warehouse_id=warehouse_id,
                        level=float(row["suggested_level"]), source=SOURCE_ACCEPTED,
                        notes=row.get("notes"), company_id=company_id)


def supplier_constraints(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """`{product_id: {moq, order_multiple, lead_time_days}}` from the cheapest linked supplier.

    The same rule the engine already uses to pick a supplier, so a suggested level and the
    order that fills it read the same lead time and round to the same pack.
    """
    if not product_ids:
        return {}
    rows = db.execute(text("""
        SELECT DISTINCT ON (ps.product_id)
               ps.product_id::text AS product_id,
               COALESCE(ps.moq, ps.min_order_quantity) AS moq,
               ps.order_multiple,
               ps.standard_lead_time_days AS lead_time_days
          FROM product_suppliers ps
         WHERE ps.product_id = ANY(CAST(:pids AS uuid[]))
         ORDER BY ps.product_id, ps.is_primary DESC NULLS LAST, ps.unit_cost ASC NULLS LAST
    """), {"pids": _texts(product_ids)}).mappings().all()
    return {r["product_id"]: {"moq": _f(r["moq"]),
                              "order_multiple": _f(r["order_multiple"]),
                              "lead_time_days": _f(r["lead_time_days"])}
            for r in rows}


def refresh_suggestions(db: Session, product_ids: list[str],
                        warehouse_ids: Optional[list[str]] = None, *,
                        study_months: int = DEFAULT_STUDY_MONTHS,
                        company_id: Optional[str] = None,
                        as_of: Optional[date] = None) -> int:
    """Recompute and store the suggestion for each (product, location) in scope.

    The number itself is a PRODUCT fact - one ADU across every warehouse - so a run that
    names several locations writes the same level against each of them rather than slicing
    the usage per bin. Never touches a stored level. Returns how many were written.
    """
    if not product_ids:
        return 0
    constraints = supplier_constraints(db, product_ids)
    usage = average_daily_usage(db, product_ids, as_of=as_of)
    movement = monthly_movement(db, product_ids, None, months=study_months, as_of=as_of)
    written = 0
    # A suggestion is per location when locations are named, and product-wide otherwise, so
    # a tenant who plans one warehouse is not forced to set up a level per bin.
    targets: list[Optional[str]] = list(warehouse_ids) if warehouse_ids else [None]
    for wid in targets:
        for pid in product_ids:
            c = constraints.get(pid, {})
            u = usage.get(pid, {})
            out = suggest_level_from_usage(
                adu=u.get("adu", 0.0), lead_time_days=c.get("lead_time_days"),
                window_days=u.get("window_days", LEVEL_WINDOW_DAYS),
                window_qty=u.get("window_qty"), months=movement.get(pid, []))
            store_suggestion(db, product_id=pid, warehouse_id=wid,
                             suggested_level=out["level"], basis=out["basis"],
                             company_id=company_id)
            written += 1
    db.commit()
    return written


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def _existing(db: Session, product_id: str, warehouse_id: Optional[str],
              company_id: Optional[str], *, strict_company: bool = True) -> Optional[dict]:
    """The row for this `(product, warehouse)`.

    `strict_company=True` (a buyer's own level - `upsert_level`/`accept_suggestion`) requires
    an exact company match, NULL included: two tenants never share a hand-set level.
    `strict_company=False` (`store_suggestion`) matches on `(product_id, warehouse_id)` alone
    and, when more than one row exists there, prefers the one whose company matches the
    current call before falling back to the most recently touched - so a scope-correct
    refresh still finds and updates a stray scope-less row instead of duplicating it.
    """
    if strict_company:
        row = db.execute(text("""
            SELECT id::text AS id, product_id::text AS product_id,
                   warehouse_id::text AS warehouse_id, level, source, suggested_level,
                   suggested_at, suggestion_basis, notes, company_id::text AS company_id
              FROM scm.reorder_level
             WHERE product_id = CAST(:pid AS uuid)
               AND COALESCE(warehouse_id::text, :zero) = COALESCE(CAST(:wid AS text), :zero)
               AND COALESCE(company_id::text, :zero) = COALESCE(CAST(:co AS text), :zero)
        """), {"pid": product_id, "wid": warehouse_id, "co": company_id,
               "zero": _ZERO_UUID}).mappings().first()
        return dict(row) if row else None

    row = db.execute(text("""
        SELECT id::text AS id, product_id::text AS product_id,
               warehouse_id::text AS warehouse_id, level, source, suggested_level,
               suggested_at, suggestion_basis, notes, company_id::text AS company_id
          FROM scm.reorder_level
         WHERE product_id = CAST(:pid AS uuid)
           AND COALESCE(warehouse_id::text, :zero) = COALESCE(CAST(:wid AS text), :zero)
         ORDER BY (COALESCE(company_id::text, :zero) = COALESCE(CAST(:co AS text), :zero)) DESC,
                  updated_at DESC NULLS LAST, created_at DESC
         LIMIT 1
    """), {"pid": product_id, "wid": warehouse_id, "co": company_id,
           "zero": _ZERO_UUID}).mappings().first()
    return dict(row) if row else None
