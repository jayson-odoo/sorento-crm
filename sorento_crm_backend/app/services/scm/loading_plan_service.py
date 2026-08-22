"""Fill a container at one supplier: what goes on it, what does not, and why.

The scarce thing is volume, so this is the same greedy-by-rank allocation the cash stage
already does, with cubic metres in place of ringgit (`cash_ranking.allocate_capacity`, which
S0 generalised for exactly this). Reusing it is not tidiness: a second implementation would
drift, and the two would answer "why was this line cut" differently.

Three rules the shape of this module rests on:

* **Only packed stock can be loaded.** Unfinished bodies are a request to the supplier's
  production line, never freight. A line whose supplier has nothing packed is deferred with
  that reason rather than quietly dropped.
* **A missing volume is unmeasured, never zero.** An item nobody measured must not look like
  an item that takes no space and load ahead of everything real. The allocator has a bucket
  for this; the plan reports it as a count so it can be chased.
* **Every candidate is written, including the losers.** "Why is this not on the container" is
  the question the screen exists to answer, and a plan holding only winners cannot answer it.

Ranking runs through the tenant's Fulfilment Priority policy (`scm.priority_policy`), whose
seeded weights put outstanding customer demand ahead of purchase-order document sequence
(`priority.SEEDED_WEIGHTS`): a line owed to a customer loads before one owed to nobody, and
document sequence orders the lines inside each demand band. A factor weighted zero drops out of
the average rather than dragging it, so changing the rule is a weight change and not a code
change - and each line stores its own factor vector, because a rank a planner cannot decompose
is one they stop trusting the first time it disagrees with them (AC-E7).
"""
from __future__ import annotations

import math
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.scm import ContainerSize, LoadingPlan, LoadingPlanLine, PriorityPolicy
from app.services.scm.cash_ranking import (
    ALLOCATED,
    DEFERRED,
    PARTIAL,
    UNMEASURED,
    CapacityItem,
    Factor,
    allocate_capacity,
    rank_score,
)
from app.services.scm import priority

#: Millimetres cubed in a cubic metre - product dimensions are held in mm.
_MM3_PER_M3 = 1_000_000_000.0

#: Why a line is not on the container. Stored, not rendered: the wording belongs to the UI.
NO_PACKED_STOCK = "no_packed_stock"
NOT_IN_STOCK_LIST = "not_in_stock_list"
NO_VOLUME = "no_volume_on_file"
OVER_CAPACITY = "over_capacity"

#: Where a line's per-unit volume came from. Shown beside the figure, because "the supplier
#: says 0.21" and "our catalogue implies 0.21" are worth different amounts of trust.
BASIS_SUPPLIER = "supplier"
BASIS_CATALOGUE = "catalogue"


def _uuid() -> str:
    return str(uuid.uuid4())


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #


def container_sizes(db: Session) -> list[dict]:
    rows = (
        db.query(ContainerSize)
        .filter(ContainerSize.is_active.is_(True))
        .order_by(ContainerSize.cbm)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "code": r.code,
            "label": r.label,
            "cbm": float(r.cbm),
            "is_default": bool(r.is_default),
        }
        for r in rows
    ]


def _resolve_container(
    db: Session, container_type: Optional[str], container_cbm: Optional[float]
) -> tuple[Optional[str], float]:
    """The volume one container holds. An explicit figure wins over the named size.

    A named size the tenant has not configured is an error rather than a default, because
    silently planning a 40HQ as a 20GP loses half a container and looks like the engine
    under-filling.
    """
    if container_cbm is not None:
        if float(container_cbm) <= 0:
            raise ValueError("container volume must be greater than zero")
        return (container_type, float(container_cbm))

    sizes = {s["code"].upper(): s for s in container_sizes(db)}
    if container_type:
        row = sizes.get(container_type.upper())
        if not row:
            raise ValueError(f"no container size configured for {container_type}")
        return (row["code"], row["cbm"])

    default = next((s for s in sizes.values() if s["is_default"]), None)
    if not default:
        raise ValueError("no default container size is configured")
    return (default["code"], default["cbm"])


def _open_po_lines(db: Session, supplier_id: str) -> list[dict]:
    """Outstanding lines on PLACED purchase orders at this supplier, oldest document first.

    A draft or draft_recommendation the supplier has never seen is not a candidate.

    Raw SQL because company isolation applies on ORM execution only, so the predicate is
    added explicitly below - the same rule the rest of this module follows.
    """
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "po.company_id", param_prefix="c")
    # An empty fragment means "every company", so it has to disappear rather than land as
    # `AND ` in the SQL.
    scope = f"AND {predicate}" if predicate else ""
    sql = f"""
        SELECT pol.id            AS po_line_id,
               po.id             AS po_id,
               po.po_number      AS po_number,
               po.issue_date     AS po_date,
               pol.product_id    AS product_id,
               p.product_code    AS item_code,
               p.dimensions_length AS dim_l,
               p.dimensions_width  AS dim_w,
               p.dimensions_height AS dim_h,
               pol.qty_ordered   AS qty_ordered,
               pol.qty_received  AS qty_received,
               pol.expected_date AS expected_date
          FROM purchase_order_lines pol
          JOIN purchase_orders po ON po.id = pol.purchase_order_id
          LEFT JOIN products p ON p.id = pol.product_id
         WHERE po.supplier_id = :supplier_id
           AND pol.line_status = 'open'
           -- Placed, not drafted. `draft_recommendation` is a plan the engine staged and
           -- nobody has sent, so there is nothing at the supplier to load against it.
           AND po.status NOT IN ('draft', 'draft_recommendation')
           AND COALESCE(pol.qty_ordered, 0) > COALESCE(pol.qty_received, 0)
           {scope}
         ORDER BY po.issue_date NULLS LAST, po.po_number, pol.id
    """
    rows = db.execute(text(sql), {"supplier_id": supplier_id, **params}).mappings().all()
    return [dict(r) for r in rows]


def _supplier_stock(db: Session, supplier_id: str) -> dict[str, dict]:
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "si.company_id", param_prefix="c")
    rows = db.execute(
        text(
            f"""
            SELECT si.item_code, si.product_id, si.qty_packed, si.qty_unfinished,
                   si.cbm_per_unit, si.as_of
              FROM scm.supplier_inventory si
             WHERE si.supplier_id = :s AND {predicate or 'true'}
            """
        ),
        {"s": supplier_id, **params},
    ).mappings().all()
    out: dict[str, dict] = {}
    for r in rows:
        rec = dict(r)
        out[str(r["item_code"])] = rec
        if r["product_id"]:
            # Keyed by product id as well, because the purchase order knows the product and
            # the supplier's own model number may be spelled differently.
            out[f"pid:{r['product_id']}"] = rec
    return out


# Ranking is the Fulfilment Priority policy, and it lives in `scm/priority.py` because the SPO
# allocation suggestion ranks the same purchase-order lines by the same policy (AC-H5). These
# names are kept as thin aliases so the code below still reads in the plan's own vocabulary.
_active_policy = priority.active_policy
_demand_class_by_po = priority.demand_class_by_po
_demand_value = priority.demand_value
_sequence_values = priority.sequence_values
_date_values = priority.date_values
_factors_for = priority.factors_for


# --------------------------------------------------------------------------- #
# the plan
# --------------------------------------------------------------------------- #


def _catalogue_cbm(row: dict) -> Optional[float]:
    l, w, h = row.get("dim_l"), row.get("dim_w"), row.get("dim_h")
    if l is None or w is None or h is None:
        return None
    return round(float(l) * float(w) * float(h) / _MM3_PER_M3, 6)


def _compute(db: Session, supplier_id: str, capacity: float) -> dict:
    """Everything the plan needs, computed and ranked, before a row is written."""
    candidates = _open_po_lines(db, supplier_id)
    stock = _supplier_stock(db, supplier_id)
    policy = _active_policy(db)
    weights = dict(policy.factors or {}) if policy else {"po_document_sequence": 1.0}
    class_weights = dict(policy.demand_class_weights or {}) if policy else {}
    classes = _demand_class_by_po(db, {str(c["po_number"]) for c in candidates if c["po_number"]})

    sequence = _sequence_values(candidates)
    need_by = _date_values(candidates, "expected_date")
    ages = _date_values(candidates, "po_date")

    prepared: list[dict] = []
    for c in candidates:
        line_id = str(c["po_line_id"])
        outstanding = float(c["qty_ordered"] or 0) - float(c["qty_received"] or 0)
        rec = stock.get(str(c["item_code"] or "")) or stock.get(f"pid:{c['product_id']}")
        packed = float(rec["qty_packed"] or 0) if rec else None

        per_unit = _f(rec["cbm_per_unit"]) if rec and rec["cbm_per_unit"] is not None else None
        basis = BASIS_SUPPLIER if per_unit is not None else None
        if per_unit is None:
            per_unit = _catalogue_cbm(c)
            basis = BASIS_CATALOGUE if per_unit is not None else None

        loadable = min(outstanding, packed) if packed is not None else 0.0
        reason: Optional[str] = None
        if rec is None:
            reason = NOT_IN_STOCK_LIST
        elif loadable <= 0:
            reason = NO_PACKED_STOCK
        elif per_unit is None:
            reason = NO_VOLUME

        # `document_age` is the mirror of `need_by`: older document, higher priority. The
        # date helper returns "sooner is higher", which for an issue date IS older-is-higher.
        prepared.append(
            {
                "row": c,
                "po_line_id": line_id,
                "outstanding": outstanding,
                "packed": packed,
                "loadable": loadable if reason in (None, NO_VOLUME) else 0.0,
                "cbm_per_unit": per_unit,
                "volume_basis": basis,
                "reason": reason,
                "factors": _factors_for(
                    weights,
                    sequence=sequence.get(str(c["po_number"] or "")),
                    demand_weight=_demand_value(
                        classes, class_weights, str(c["po_number"] or "")
                    ),
                    need_by=need_by.get(line_id),
                    age=ages.get(line_id),
                ),
            }
        )

    for p in prepared:
        p["score"] = rank_score(p["factors"])
    # Rank by score, then by the document order the buyer already reads, so equal scores come
    # out in an order a person can predict.
    prepared.sort(key=lambda p: (-p["score"], str(p["row"]["po_number"] or ""), p["po_line_id"]))
    for i, p in enumerate(prepared, start=1):
        p["rank"] = i

    items = [
        CapacityItem(
            id=p["po_line_id"],
            rank=p["rank"],
            # Unmeasured for the allocator when there is no volume; nothing to load when the
            # supplier has none packed, which is a deferral rather than a competition.
            demand=(p["loadable"] * p["cbm_per_unit"]) if p["cbm_per_unit"] is not None else None,
            divisible=True,
        )
        for p in prepared
        if p["loadable"] > 0
    ]
    result = allocate_capacity(items, capacity)

    for p in prepared:
        pid = p["po_line_id"]
        status = result.status_by_id.get(pid)
        if status is None:
            p["status"] = DEFERRED
            p["qty_planned"] = 0.0
            p["cbm_planned"] = 0.0
            p["deferral_reason"] = p["reason"] or OVER_CAPACITY
            continue
        if status == UNMEASURED:
            p["status"] = UNMEASURED
            p["qty_planned"] = 0.0
            p["cbm_planned"] = 0.0
            p["deferral_reason"] = NO_VOLUME
            continue
        granted = result.granted_by_id.get(pid, 0.0)
        per_unit = p["cbm_per_unit"] or 0.0
        # Whole units only. A container is loaded with boxes, and 3.7 of a toilet is not a
        # thing anybody can pick.
        qty = math.floor(granted / per_unit) if per_unit > 0 else 0.0
        qty = min(qty, p["loadable"])
        p["qty_planned"] = float(qty)
        p["cbm_planned"] = round(qty * per_unit, 4)
        if qty <= 0:
            p["status"] = DEFERRED
            p["deferral_reason"] = OVER_CAPACITY
        elif qty < p["outstanding"]:
            p["status"] = PARTIAL
            # Partial because the container filled, or because the supplier has only some of
            # it packed. Naming the right one is the whole point of AC-E5.
            p["deferral_reason"] = (
                NO_PACKED_STOCK if qty >= p["loadable"] and p["loadable"] < p["outstanding"]
                else OVER_CAPACITY
            )
        else:
            p["status"] = ALLOCATED
            p["deferral_reason"] = None

    return {"prepared": prepared, "policy": policy}


def build(
    db: Session,
    *,
    supplier_id: str,
    container_count: int = 1,
    container_type: Optional[str] = None,
    container_cbm: Optional[float] = None,
    actor: Optional[str] = None,
    plan: Optional[LoadingPlan] = None,
) -> LoadingPlan:
    """Compute a plan and persist it. Pass `plan` to re-run an existing one in place.

    Re-running in place is AC-E6: changing the container count must not need the stock list
    uploaded again, and it must not leave a second plan behind for the same decision.
    """
    if int(container_count) <= 0:
        raise ValueError("a plan needs at least one container")
    code, cbm = _resolve_container(db, container_type, container_cbm)
    capacity = float(cbm) * int(container_count)

    out = _compute(db, supplier_id, capacity)
    prepared = out["prepared"]
    policy = out["policy"]

    as_of = db.execute(
        text("SELECT max(as_of) FROM scm.supplier_inventory WHERE supplier_id = :s"),
        {"s": supplier_id},
    ).scalar()

    if plan is None:
        plan = LoadingPlan(id=_uuid(), supplier_id=supplier_id, created_by=actor)
        db.add(plan)
    else:
        db.query(LoadingPlanLine).filter(LoadingPlanLine.plan_id == plan.id).delete(
            synchronize_session=False
        )
        db.flush()

    plan.container_type = code
    plan.container_count = int(container_count)
    plan.container_cbm = cbm
    plan.capacity_cbm = capacity
    plan.policy_id = str(policy.id) if policy else None
    plan.inventory_as_of = as_of
    plan.computed_at = datetime.now()
    plan.planned_cbm = round(sum(p["cbm_planned"] for p in prepared), 4)
    plan.line_count = len(prepared)
    plan.deferred_count = sum(1 for p in prepared if p["status"] == DEFERRED)
    plan.unmeasured_count = sum(1 for p in prepared if p["status"] == UNMEASURED)
    db.flush()

    for p in prepared:
        row = p["row"]
        db.add(
            LoadingPlanLine(
                id=_uuid(),
                plan_id=plan.id,
                po_line_id=p["po_line_id"],
                product_id=row["product_id"],
                po_number=row["po_number"],
                item_code=row["item_code"],
                qty_outstanding=p["outstanding"],
                qty_packed_available=p["packed"],
                qty_planned=p["qty_planned"],
                cbm_per_unit=p["cbm_per_unit"],
                cbm_planned=p["cbm_planned"],
                volume_basis=p["volume_basis"],
                rank=p["rank"],
                rank_score=p["score"],
                factors_json=[f.as_dict() for f in p["factors"]],
                status=p["status"],
                deferral_reason=p["deferral_reason"],
            )
        )
    db.flush()
    return plan


# --------------------------------------------------------------------------- #
# serialization
# --------------------------------------------------------------------------- #


def _supplier_name(db: Session, supplier_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT supplier_name FROM suppliers WHERE id = :i"), {"i": supplier_id}
    ).first()
    return row[0] if row else None


def serialize(db: Session, plan: LoadingPlan, *, with_lines: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(plan.id),
        "supplier_id": str(plan.supplier_id),
        "supplier_name": _supplier_name(db, str(plan.supplier_id)),
        "container_type": plan.container_type,
        "container_count": plan.container_count,
        "container_cbm": _f(plan.container_cbm),
        "capacity_cbm": _f(plan.capacity_cbm),
        "planned_cbm": _f(plan.planned_cbm),
        "fill_rate": (
            round(float(plan.planned_cbm) / float(plan.capacity_cbm), 4)
            if plan.capacity_cbm and float(plan.capacity_cbm) > 0
            else None
        ),
        "line_count": plan.line_count,
        "deferred_count": plan.deferred_count,
        "unmeasured_count": plan.unmeasured_count,
        "inventory_as_of": plan.inventory_as_of.isoformat() if plan.inventory_as_of else None,
        "computed_at": plan.computed_at.isoformat() if plan.computed_at else None,
        "created_by": plan.created_by,
    }
    if with_lines:
        lines = (
            db.query(LoadingPlanLine)
            .filter(LoadingPlanLine.plan_id == plan.id)
            .order_by(LoadingPlanLine.rank)
            .all()
        )
        out["lines"] = [
            {
                "id": str(ln.id),
                "po_line_id": str(ln.po_line_id),
                "po_number": ln.po_number,
                "item_code": ln.item_code,
                "qty_outstanding": _f(ln.qty_outstanding),
                "qty_packed_available": _f(ln.qty_packed_available),
                "qty_planned": _f(ln.qty_planned),
                "cbm_per_unit": _f(ln.cbm_per_unit),
                "cbm_planned": _f(ln.cbm_planned),
                "volume_basis": ln.volume_basis,
                "rank": ln.rank,
                "rank_score": _f(ln.rank_score),
                "factors": ln.factors_json or [],
                "status": ln.status,
                "deferral_reason": ln.deferral_reason,
            }
            for ln in lines
        ]
    return out


def unfinished_at_supplier(db: Session, supplier_id: str) -> list[dict]:
    """Stock the supplier holds unfinished, so Ms Tee can ask for it (AC-E2).

    Listed separately rather than mixed into the plan: it is not freight this week, it is a
    production request, and putting it in the same table is how somebody loads a container
    with things that do not exist.
    """
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "si.company_id", param_prefix="c")
    rows = db.execute(
        text(
            f"""
            SELECT si.item_code, si.product_name, si.qty_unfinished, si.qty_packed, si.as_of
              FROM scm.supplier_inventory si
             WHERE si.supplier_id = :s AND COALESCE(si.qty_unfinished, 0) > 0
               AND {predicate or 'true'}
             ORDER BY si.qty_unfinished DESC
            """
        ),
        {"s": supplier_id, **params},
    ).mappings().all()
    return [
        {
            "item_code": r["item_code"],
            "product_name": r["product_name"],
            "qty_unfinished": _f(r["qty_unfinished"]),
            "qty_packed": _f(r["qty_packed"]),
            "as_of": r["as_of"].isoformat() if r["as_of"] else None,
        }
        for r in rows
    ]
