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

Movement is read from `scm.consumption_v` (delivered sales lines), not from open orders.
Three months of what actually left the building is the business's own rule for setting a
level; open orders are demand, and demand is netted elsewhere.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException

# The business's rule: "study 3 months movement to set reorder level". Overridable per policy
# scope; these are only the fallbacks for a policy row that has not set them.
DEFAULT_STUDY_MONTHS = 3
DEFAULT_COVER_MONTHS = 2.0

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
        where_wh = " AND c.warehouse_id::text = ANY(:whs)"
        params["whs"] = _texts(warehouse_ids)

    rows = db.execute(text(f"""
        SELECT c.product_id::text AS product_id,
               date_trunc('month', c.day)::date AS month,
               COALESCE(sum(c.qty_out), 0) AS qty
          FROM scm.consumption_v c
         WHERE c.product_id::text = ANY(:pids)
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

def suggest_level(movement: list[dict[str, Any]], *, cover_months: float = DEFAULT_COVER_MONTHS,
                  moq: Optional[float] = None,
                  order_multiple: Optional[float] = None,
                  trend: Optional[str] = None) -> dict[str, Any]:
    """`avg monthly movement x cover months`, rounded up to what the supplier will sell.

    Returns the level AND the arithmetic. A suggestion the buyer cannot argue with is a
    suggestion they will not trust, so every input that produced the number travels with it.

    `trend` (S13f) shapes only the ROUNDING, never the arithmetic: a rising book rounds up
    to the next whole unit, a falling or quiet one rounds down. None = exact, as before.
    """
    months = list(movement or [])
    total = sum(float(m.get("qty") or 0) for m in months)
    avg = (total / len(months)) if months else 0.0
    cover = float(cover_months if cover_months is not None else DEFAULT_COVER_MONTHS)
    raw = avg * cover
    level = raw
    if trend == "rising":
        level = float(math.ceil(level))
    elif trend in ("falling", "quiet"):
        level = float(math.floor(level))
    if moq is not None and level > 0 and level < float(moq):
        level = float(moq)
    if order_multiple and float(order_multiple) > 0 and level > 0:
        m = float(order_multiple)
        level = math.ceil(level / m) * m
    return {
        "level": round(level, 4),
        "basis": {
            "months": months,
            "months_studied": len(months),
            "total_qty": round(total, 4),
            "avg_monthly": round(avg, 4),
            "cover_months": cover,
            "raw_level": round(raw, 4),
            "moq": moq,
            "order_multiple": order_multiple,
            # The verdict that shaped the rounding, or None when none was consulted.
            "trend": trend,
            # Said explicitly so a 0 reads as "nothing moved", never as "not computed".
            "no_movement": total <= 0,
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
        where_wh = " AND (rl.warehouse_id IS NULL OR rl.warehouse_id::text = ANY(:whs))"
        params["whs"] = _texts(warehouse_ids)
    rows = db.execute(text(f"""
        SELECT rl.id::text AS id, rl.product_id::text AS product_id,
               rl.warehouse_id::text AS warehouse_id, rl.level, rl.source,
               rl.suggested_level, rl.suggested_at, rl.suggestion_basis,
               rl.amended_level, rl.amended_at, rl.amended_by, rl.notes
          FROM scm.reorder_level rl
         WHERE rl.product_id::text = ANY(:pids)
           {where_wh}
           {("AND " + co) if co else ""}
    """), params).mappings().all()
    return {(r["product_id"], r["warehouse_id"]): dict(r) for r in rows}


def resolve_level(levels: dict[tuple[str, Optional[str]], dict], product_id: str,
                  warehouse_id: Optional[str]) -> Optional[dict]:
    """The per-location row wins; the product-wide row is the fallback. None when neither
    exists, which is NOT the same as a level of 0 and must not be planned as one."""
    if warehouse_id is not None:
        hit = levels.get((product_id, warehouse_id))
        if hit is not None:
            return hit
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
    """
    row = _existing(db, product_id, warehouse_id, company_id)
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
        db.execute(text("""
            UPDATE scm.reorder_level
               SET suggested_level = :sl, suggested_at = :now,
                   suggestion_basis = CAST(:basis AS jsonb),
                   amended_level = NULL, amended_at = NULL, amended_by = NULL,
                   updated_at = :now
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
    """`{product_id: {moq, order_multiple}}` from the cheapest linked supplier.

    The same rule the engine already uses to pick a supplier, so a suggested level and the
    order that fills it round to the same pack.
    """
    if not product_ids:
        return {}
    rows = db.execute(text("""
        SELECT DISTINCT ON (ps.product_id)
               ps.product_id::text AS product_id,
               COALESCE(ps.moq, ps.min_order_quantity) AS moq,
               ps.order_multiple
          FROM product_suppliers ps
         WHERE ps.product_id::text = ANY(:pids)
         ORDER BY ps.product_id, ps.is_primary DESC NULLS LAST, ps.unit_cost ASC NULLS LAST
    """), {"pids": _texts(product_ids)}).mappings().all()
    return {r["product_id"]: {"moq": _f(r["moq"]), "order_multiple": _f(r["order_multiple"])}
            for r in rows}


def refresh_suggestions(db: Session, product_ids: list[str],
                        warehouse_ids: Optional[list[str]] = None, *,
                        study_months: int = DEFAULT_STUDY_MONTHS,
                        cover_months: float = DEFAULT_COVER_MONTHS,
                        company_id: Optional[str] = None,
                        as_of: Optional[date] = None) -> int:
    """Recompute and store the suggestion for each (product, location) in scope.

    Never touches a stored level. Returns how many suggestions were written.
    """
    if not product_ids:
        return 0
    constraints = supplier_constraints(db, product_ids)
    written = 0
    # A suggestion is per location when locations are named, and product-wide otherwise, so
    # a tenant who plans one warehouse is not forced to set up a level per bin.
    targets: list[Optional[str]] = list(warehouse_ids) if warehouse_ids else [None]
    for wid in targets:
        movement = monthly_movement(db, product_ids, [wid] if wid else None,
                                    months=study_months, as_of=as_of)
        for pid in product_ids:
            c = constraints.get(pid, {})
            out = suggest_level(movement.get(pid, []), cover_months=cover_months,
                                moq=c.get("moq"), order_multiple=c.get("order_multiple"))
            store_suggestion(db, product_id=pid, warehouse_id=wid,
                             suggested_level=out["level"], basis=out["basis"],
                             company_id=company_id)
            written += 1
    db.commit()
    return written


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def _existing(db: Session, product_id: str, warehouse_id: Optional[str],
              company_id: Optional[str]) -> Optional[dict]:
    row = db.execute(text("""
        SELECT id::text AS id, product_id::text AS product_id,
               warehouse_id::text AS warehouse_id, level, source, suggested_level,
               suggested_at, suggestion_basis, notes, company_id::text AS company_id
          FROM scm.reorder_level
         WHERE product_id::text = :pid
           AND COALESCE(warehouse_id::text, :zero) = COALESCE(CAST(:wid AS text), :zero)
           AND COALESCE(company_id::text, :zero) = COALESCE(CAST(:co AS text), :zero)
    """), {"pid": product_id, "wid": warehouse_id, "co": company_id,
           "zero": _ZERO_UUID}).mappings().first()
    return dict(row) if row else None
