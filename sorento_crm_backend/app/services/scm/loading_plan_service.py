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


def _supplier_row(db: Session, supplier_id: str) -> Optional[dict]:
    """The plan's supplier: name and address, company-scoped and uuid-guarded (B1).

    Both halves were bare `SELECT ... FROM suppliers WHERE id = :i`, which read straight
    across the company boundary - a caller in company A could start a plan against company B's
    supplier, and every screen from there on named and addressed that supplier - and handed a
    non-uuid id to the UUID column, which is a 500 rather than "no such supplier". Same shape
    as `supplier_notice_service._supplier`, which carries the reasoning in full; it returns
    None rather than raising because the serializer's callers show a plan with no supplier
    name, and only `create_record` turns that into a refusal.

    The address is the one the send dialog opens with in its To field (AC-C2). It rides on the
    plan rather than being fetched by the dialog: the record page already holds the plan, and
    a second round trip to learn one column of a supplier it has just been handed is a round
    trip for data that was already on the wire.
    """
    from app.services.company_scope_sql import company_sql_predicate
    from app.services.scm.supplier_scope import is_uuid

    if not is_uuid(supplier_id):
        return None
    predicate, params = company_sql_predicate(db, "company_id", param_prefix="lps")
    row = (
        db.execute(
            text(
                "SELECT supplier_name, email FROM suppliers "
                f"WHERE id = :i AND {predicate or 'true'}"
            ),
            {"i": str(supplier_id), **params},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def serialize(db: Session, plan: LoadingPlan, *, with_lines: bool = True) -> dict[str, Any]:
    """The stage-2 CBM fit, with the record fields alongside it.

    Spreads `record_dict` rather than re-listing its keys: one table, one row, so a lifecycle
    column added below must not reach the FE through one builder and not the other.
    """
    out: dict[str, Any] = {
        **record_dict(db, plan),
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


# =========================================================================== #
# The plan as a RECORD (part 4, R1-R6)
#
# Everything above this line is the stage-2 CBM fit. Everything below is the plan a buyer
# actually works on: started, edited, sent or cancelled. They share a table because they are
# the same thing at two stages (R1), and `supplier_notices.loading_plan_id` already points at
# it - a second "container plan" table would have been this row under a second name.
# =========================================================================== #

#: What a plan can be. `opened` is deliberately absent: an open is an event that repeats, and
#: a status that flipped back and forth would lie about the decision.
PLAN_STATUSES = ("planning", "sent", "cancelled")

#: The chip the list opens on. A cancelled plan is a decision already made, and a list that
#: opens on it hides the work in front of somebody.
ACTIVE_STATUSES = ("planning", "sent")

DOCUMENT_KINDS = ("stock_list", "proforma", "none")

#: What the list may sort by, mapped to the column that answers it. A caller-supplied name
#: that is not here falls back to the default order rather than reaching the SQL.
_SORTABLE = {
    "started_at": "created_at",
    "supplier_name": "supplier_name",
    "plan_horizon_date": "plan_horizon_date",
    "to_request_qty": "to_request_qty",
    "sent_at": "sent_at",
    "status": "status",
}


def _latest_notice_channels(db: Session, plan_ids: list[str]) -> dict[str, dict]:
    """The newest notice per plan: which channel it went on, when, and the opens (AC-C8).

    One query for the whole page rather than one per row - the list prints this in two
    columns, and a per-row lookup is what turns a 25-row page into 25 round trips. The reader
    itself is `supplier_notice_service.latest_notice_for_plans` (S3), so the Sent and Opened
    columns and the Requests sent card cannot come to disagree about which send is current.
    """
    from app.services.scm import supplier_notice_service

    return supplier_notice_service.latest_notice_for_plans(db, plan_ids)


def _proforma_numbers(db: Session, supplier_ids: list[str]) -> dict[str, str]:
    """The newest un-converted proforma per supplier, for the Document label.

    Read at display time rather than pinned on the plan: unlike the stock list (whose own
    snapshot date IS pinned, on `inventory_as_of`), a proforma stand-in has no column of its
    own here, and the drift it can show is the same one R2 already states in the open - the
    supplier's current statement is what a plan reads.
    """
    if not supplier_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (pi.supplier_id)
                   pi.supplier_id::text AS supplier_id, pi.pi_number
              FROM scm.proforma_invoice pi
             WHERE pi.supplier_id = ANY(CAST(:ids AS uuid[]))
               AND COALESCE(pi.status, 'current') = 'current'
             ORDER BY pi.supplier_id, pi.invoice_date DESC NULLS LAST,
                      pi.created_at DESC, pi.id DESC
            """
        ),
        {"ids": supplier_ids},
    ).mappings().all()
    return {r["supplier_id"]: r["pi_number"] for r in rows}


def _document_label(plan: LoadingPlan, pi_number: Optional[str]) -> str:
    """Ready to print. "No file" is a real answer, not a missing one."""
    if plan.document_kind == "stock_list":
        when = plan.inventory_as_of.strftime("%d/%m/%Y") if plan.inventory_as_of else None
        return f"Stock list {when}" if when else "Stock list"
    if plan.document_kind == "proforma":
        return f"Proforma invoice {pi_number}" if pi_number else "Proforma invoice"
    return "No file"


#: "the caller did not look this up", which is not the same as "the caller looked and found
#: nothing". `None` cannot tell those apart, and the difference is a query per row.
_UNSET: Any = object()


def record_dict(
    db: Session,
    plan: LoadingPlan,
    *,
    supplier_name: Optional[str] = None,
    supplier_email: Optional[str] = None,
    notice: Optional[dict] = None,
    pi_number: Any = _UNSET,
) -> dict[str, Any]:
    """One plan, in the shape the list and the record page both read.

    ONE builder for both, so a column cannot reach the grid and be missing from the record
    behind it. `supplier_name` / `supplier_email` / `notice` / `pi_number` are passed in when a
    caller has already fetched them for a whole page; a single-row caller lets them be looked
    up here. The name and the address travel together (one row, one join), so a caller that
    named the supplier has already answered both.

    `pi_number` defaults to `_UNSET` rather than to None because the list DOES pass None - it
    is what "this supplier has no un-converted proforma" looks like - and reading that as "not
    provided" ran the batch query again for every such row on the page.
    """
    if supplier_name is None:
        row = _supplier_row(db, str(plan.supplier_id)) or {}
        supplier_name = row.get("supplier_name")
        supplier_email = row.get("email")
    if notice is None:
        notice = _latest_notice_channels(db, [str(plan.id)]).get(str(plan.id))
    if pi_number is _UNSET:
        pi_number = (
            _proforma_numbers(db, [str(plan.supplier_id)]).get(str(plan.supplier_id))
            if plan.document_kind == "proforma"
            else None
        )
    return {
        "id": str(plan.id),
        "supplier_id": str(plan.supplier_id),
        "supplier_name": supplier_name,
        # The plan is named by supplier + start time, exactly as a reorder run is. There is
        # no plan number to mint and nothing for a person to memorise.
        "started_at": plan.created_at.isoformat() if plan.created_at else None,
        "plan_horizon_date": (
            plan.plan_horizon_date.isoformat() if plan.plan_horizon_date else None
        ),
        "document_kind": plan.document_kind,
        "document_label": _document_label(plan, pi_number),
        "source_attachment_id": (
            str(plan.source_attachment_id) if plan.source_attachment_id else None
        ),
        "status": plan.status,
        "supplier_email": supplier_email,
        "sent_channel": (notice or {}).get("channel"),
        "sent_at": plan.sent_at.isoformat() if plan.sent_at else None,
        # The opens, off the plan's LATEST notice (AC-C8): a resent plan must never report the
        # opens of a link nobody can open any more. `opened_at` is the first one and never
        # moves; the column prints the last one and how many there have been.
        "opened_at": (notice or {}).get("opened_at"),
        "last_opened_at": (notice or {}).get("last_opened_at"),
        "open_count": (notice or {}).get("open_count") or 0,
        "cancelled_at": plan.cancelled_at.isoformat() if plan.cancelled_at else None,
        "cancelled_by": plan.cancelled_by,
        "line_edits": plan.line_edits or {},
        "to_request_qty": _f(plan.to_request_qty),
        "to_request_cbm": _f(plan.to_request_cbm),
    }


def list_records(
    db: Session,
    *,
    page: int = 1,
    limit: int = 25,
    sort: Optional[str] = None,
    direction: str = "desc",
    query: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """The plans list (R3): server-paged, server-sorted, searched by supplier name."""
    from app.models.procurement import Supplier

    q = db.query(LoadingPlan, Supplier.supplier_name, Supplier.email).join(
        Supplier, Supplier.id == LoadingPlan.supplier_id
    )
    if status in (None, "", "active"):
        q = q.filter(LoadingPlan.status.in_(ACTIVE_STATUSES))
    elif status in PLAN_STATUSES:
        q = q.filter(LoadingPlan.status == status)
    if query and query.strip():
        q = q.filter(Supplier.supplier_name.ilike(f"%{query.strip()}%"))

    total = q.count()
    column = _SORTABLE.get(sort or "", "created_at")
    order = (
        Supplier.supplier_name
        if column == "supplier_name"
        else getattr(LoadingPlan, column)
    )
    order = order.desc() if direction == "desc" else order.asc()
    # Ended with the id, because two plans started in the same transaction share `created_at`
    # and a non-total order pages differently on every request.
    rows = (
        q.order_by(order, LoadingPlan.id)
        .offset(max(page - 1, 0) * limit)
        .limit(limit)
        .all()
    )

    plans = [p for p, _name, _email in rows]
    notices = _latest_notice_channels(db, [str(p.id) for p in plans])
    numbers = _proforma_numbers(
        db, sorted({str(p.supplier_id) for p in plans if p.document_kind == "proforma"})
    )
    return {
        "data": [
            record_dict(
                db,
                p,
                supplier_name=name,
                supplier_email=email,
                notice=notices.get(str(p.id)) or {},
                pi_number=numbers.get(str(p.supplier_id)),
            )
            for p, name, email in rows
        ],
        "total": total,
    }


def create_record(
    db: Session,
    *,
    supplier_id: str,
    plan_horizon_date: Optional[date],
    document_kind: str,
    source_attachment_id: Optional[str],
    actor: Optional[str] = None,
) -> LoadingPlan:
    """Start a plan. Raises `ValueError` when the supplier is not one this caller can see.

    `inventory_as_of` is stamped from the supplier's CURRENT stock-list snapshot, which is
    what pins the Document label: a newer list uploaded later changes the plan's numbers (R2,
    stated in the open) but must not rewrite which file this plan was started from.
    """
    if _supplier_row(db, supplier_id) is None:
        raise ValueError("Supplier not found")
    as_of = None
    if document_kind == "stock_list":
        as_of = db.execute(
            text(
                "SELECT max(as_of) FROM scm.supplier_inventory WHERE supplier_id = CAST(:s AS uuid)"
            ),
            {"s": supplier_id},
        ).scalar()
    plan = LoadingPlan(
        id=str(uuid.uuid4()),
        supplier_id=supplier_id,
        status="planning",
        plan_horizon_date=plan_horizon_date,
        document_kind=document_kind,
        source_attachment_id=source_attachment_id,
        inventory_as_of=as_of,
        line_edits={},
        created_by=actor,
    )
    db.add(plan)
    db.flush()
    return plan


def has_notices(db: Session, plan_id: str) -> bool:
    """Did anything for this plan actually leave the building (Q5)?

    Not "is there a notice row": a refused send writes one too, and a plan whose only notice
    is `failed` was never sent, so refusing to delete it would leave a row that can be neither
    sent nor removed. The FK is `ON DELETE SET NULL`, so the failed row survives the delete as
    the record of the attempt.
    """
    from app.services.scm import supplier_notice_service

    return bool(
        db.execute(
            text(
                "SELECT 1 FROM supplier_notices WHERE loading_plan_id = CAST(:p AS uuid) "
                "AND status = ANY(:s) LIMIT 1"
            ),
            {"p": plan_id, "s": list(supplier_notice_service.WENT_OUT_STATUSES)},
        ).first()
    )


def delete_record(db: Session, plan_id: str) -> None:
    """Hard delete, with its lines - unless something for it already left the building.

    Q5: a notice is the record of what left, so deleting the plan under it would leave that
    record pointing at nothing; a sent plan is cancelled instead. Two callers need this whole
    rule, `DELETE /loading-plans/{id}` and the deferred `loading_plan.delete` record action,
    so it lives here rather than in the route where only one of them could reach it.
    """
    from fastapi import HTTPException

    plan = db.query(LoadingPlan).filter(LoadingPlan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Loading plan not found")
    if has_notices(db, plan_id):
        # The shape the route has always answered with, kept verbatim: the frontend
        # service and `test_loading_plan_record` both read `detail.code`.
        raise HTTPException(
            status_code=409,
            detail={"code": "plan_sent", "message": "Sent plans are cancelled, not deleted."},
        )
    db.delete(plan)
    db.commit()


def cancel_record(db: Session, plan: LoadingPlan, *, actor: Optional[str] = None) -> LoadingPlan:
    """Cancel, and retire the link THIS PLAN's supplier still holds for it (Q4, R3/R11).

    Both halves, always: a cancelled plan whose link still answers is a supplier packing an
    ask nobody is going to place. Scoped to the plan, because the same supplier's other plans
    are still open and their links are still the current ask for them.
    """
    from app.services.scm import supplier_notice_service

    plan.status = "cancelled"
    plan.cancelled_at = datetime.utcnow()
    plan.cancelled_by = actor
    supplier_notice_service._retire_public_tokens(
        db, str(plan.supplier_id), loading_plan_id=str(plan.id)
    )
    db.flush()
    return plan


def save_edits(db: Session, plan: LoadingPlan, edits: dict[str, float]) -> LoadingPlan:
    """Replace the typed quantities WHOLE (R6). Not a patch: what is not in the map is not an
    edit any more, so a cleared cell cannot survive as a stale override."""
    plan.line_edits = {str(k): float(v) for k, v in (edits or {}).items()}
    db.flush()
    return plan


def stamp_request_totals(
    db: Session, plan: LoadingPlan, *, qty: float, cbm: Optional[float]
) -> None:
    """What the last build of this plan asked for, cached for the list's "To request" column.

    Written by the build rather than re-derived per listed row: the suggestion is many queries
    over the supplier's whole stock list, and a 25-row page would be 25 of them.
    """
    plan.to_request_qty = qty
    plan.to_request_cbm = cbm
    db.flush()
