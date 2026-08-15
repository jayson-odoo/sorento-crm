"""Which purchase-order line a shipment draws down, and where it lands.

Ms Tee's fifth step is one decision per line: accept or reallocate. So the system has to arrive
with an answer, not a form. For each shipment line this proposes a Supply PO line and a
warehouse, ranked by the SAME Fulfilment Priority policy the Loading Plan uses (AC-H5, which is
why `scm/priority.py` exists), and shows the alternatives beside it so accepting is a decision
rather than a shrug.

**Approving is what makes the stock real.** Since the 6 August decision, supply IS the SPO
allocation rather than the purchase order (migration 337). Approving therefore does two things
in one action: the allocation makes `scm.on_order_v` rise, and advancing the PO line's received
quantity makes `scm.po_ordered_v` fall. On screen the quantity moves from Ordered to Incoming,
and the Coverage Timeline gains a dated arrival. An allocation left UNLINKED (`po_line_id IS
NULL`, which is every historical row) leaves the ordered figure overstated by what it shipped
against - the stated cost of that decision, and visible rather than hidden (AC-G6a).

**A split must sum to what shipped** (AC-G7). Not "must not exceed": a line split across two
purchase orders and two locations that adds up to less than the container held is a quantity
that has silently disappeared, and nothing downstream would ever report it.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.procurement import InboundShipment, InboundShipmentLine, PurchaseOrderLine
from app.services.error_handler import AppException
from app.services.scm import priority
from app.services.scm.cash_ranking import rank_score

#: Why a candidate won. Named rather than implied: "ranked first" is not a reason a person can
#: check, and this screen exists to be checked.
REASON_ONLY = "only_open_order"
REASON_RANKED = "highest_priority"
REASON_NONE = "no_open_order"


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def _shipment_or_404(db: Session, shipment_id: str) -> InboundShipment:
    row = (
        db.query(InboundShipment).filter(InboundShipment.id == shipment_id).one_or_none()
    )
    if row is None:
        raise AppException(404, "Inbound shipment not found")
    return row


def _candidates(db: Session, product_ids: set[str], supplier_id: Optional[str]) -> list[dict]:
    """Open purchase-order lines that could be what this container is shipping against.

    Restricted to the shipment's supplier when it has one. A container from one supplier
    drawing down another supplier's order is not a ranking mistake to be corrected further
    down; it is not a candidate at all.
    """
    if not product_ids:
        return []
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "pol.company_id", param_prefix="c")
    supplier_clause = "AND po.supplier_id = :sup" if supplier_id else ""
    rows = db.execute(
        text(
            f"""
            SELECT pol.id            AS po_line_id,
                   pol.product_id,
                   pol.warehouse_id,
                   pol.qty_ordered,
                   pol.qty_received,
                   pol.expected_date,
                   po.po_number,
                   po.issue_date     AS po_date,
                   po.supplier_id
              FROM purchase_order_lines pol
              JOIN purchase_orders po ON po.id = pol.purchase_order_id
             WHERE pol.product_id = ANY(CAST(:pids AS uuid[]))
               AND COALESCE(pol.qty_ordered, 0) - COALESCE(pol.qty_received, 0) > 0
               {supplier_clause}
               AND {predicate or 'true'}
             ORDER BY po.issue_date NULLS LAST, po.po_number
            """
        ),
        {"pids": list(product_ids), "sup": supplier_id, **params},
    ).mappings().all()
    return [dict(r) for r in rows]


def _warehouse_names(db: Session, ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "w.company_id", param_prefix="c")
    rows = db.execute(
        text(
            "SELECT w.id, w.warehouse_code FROM warehouses w "
            " WHERE w.id = ANY(CAST(:ids AS uuid[])) "
            f"   AND {predicate or 'true'}"
        ),
        {"ids": list(ids), **params},
    ).mappings().all()
    return {str(r["id"]): r["warehouse_code"] for r in rows}


def _default_warehouse(db: Session) -> Optional[dict]:
    """Where a line lands when no purchase order says. The one that counts as available.

    A shipment allocated to a location whose stock is not available to sell is invisible to
    exactly the people AC-G8 exists for, so the fallback is deliberately the sellable one.
    """
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "w.company_id", param_prefix="c")
    row = db.execute(
        text(
            "SELECT w.id, w.warehouse_code FROM warehouses w "
            " WHERE w.is_active IS TRUE AND w.counts_as_available IS TRUE "
            f"   AND {predicate or 'true'} "
            " ORDER BY w.warehouse_code LIMIT 1"
        ),
        params,
    ).mappings().first()
    return dict(row) if row else None


def suggest(db: Session, shipment_id: str) -> dict:
    """A ranked (PO line, warehouse) per shipment line, with its reason and alternatives."""
    shipment = _shipment_or_404(db, shipment_id)
    lines = (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == shipment.id)
        .all()
    )
    product_ids = {str(ln.product_id) for ln in lines if ln.product_id}
    candidates = _candidates(db, product_ids, str(shipment.supplier_id) if shipment.supplier_id else None)

    factors = priority.factors_for_candidates(db, candidates)
    scored: dict[str, list[dict]] = {}
    for c in candidates:
        line_id = str(c["po_line_id"])
        f = factors.get(line_id, [])
        scored.setdefault(str(c["product_id"]), []).append(
            {
                "po_line_id": line_id,
                "po_number": c["po_number"],
                "warehouse_id": str(c["warehouse_id"]) if c["warehouse_id"] else None,
                "outstanding": float(c["qty_ordered"] or 0) - float(c["qty_received"] or 0),
                "expected_date": c["expected_date"].isoformat() if c["expected_date"] else None,
                "score": rank_score(f),
                "factors": [x.as_dict() for x in f],
            }
        )

    fallback = _default_warehouse(db)
    names = _warehouse_names(
        db,
        {c["warehouse_id"] for opts in scored.values() for c in opts if c["warehouse_id"]}
        | ({str(fallback["id"])} if fallback else set()),
    )

    out_lines: list[dict] = []
    for ln in lines:
        options = sorted(
            scored.get(str(ln.product_id), []),
            key=lambda o: (-o["score"], o["po_number"] or "", o["po_line_id"]),
        )
        shipped = float(ln.quantity_shipped or 0)
        allocated = float(ln.spo_allocated_quantity or 0)

        for o in options:
            wid = o["warehouse_id"] or (str(fallback["id"]) if fallback else None)
            o["warehouse_id"] = wid
            o["warehouse_code"] = names.get(wid or "")

        chosen = options[0] if options else None
        if chosen is None:
            reason = REASON_NONE
        elif len(options) == 1:
            reason = REASON_ONLY
        else:
            reason = REASON_RANKED

        out_lines.append(
            {
                "shipment_line_id": str(ln.id),
                "product_id": str(ln.product_id),
                "quantity_shipped": shipped,
                "quantity_allocated": allocated,
                # What is left to decide. The suggestion covers this, never the whole line
                # again, so re-opening the screen after a partial allocation does not propose
                # allocating the same units twice.
                "quantity_to_allocate": max(shipped - allocated, 0.0),
                "reason": reason,
                "suggestion": (
                    {
                        **chosen,
                        # Capped at what the order still has outstanding: proposing more than a
                        # purchase order asked for is how a receipt goes over.
                        "qty": min(max(shipped - allocated, 0.0), chosen["outstanding"]),
                    }
                    if chosen
                    else None
                ),
                "alternatives": options[1:],
            }
        )

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "container_no": shipment.shipping_container_number,
        "supplier_id": str(shipment.supplier_id) if shipment.supplier_id else None,
        "lines": out_lines,
    }


# --------------------------------------------------------------------------- approve


def _round(value: float) -> float:
    """Quantities are compared to 4 decimals because that is what the columns hold."""
    return round(float(value), 4)


def approve(db: Session, shipment_id: str, decisions: list[dict], *,
            actor_id: Optional[str] = None) -> dict:
    """Write the allocations and advance the purchase orders, in one action.

    `decisions` is `[{shipment_line_id, splits: [{po_line_id, warehouse_id, qty}]}]`. A split
    must sum to the line's outstanding quantity: allocating less is a quantity that has
    silently disappeared, and allocating more is stock we never received.
    """
    shipment = _shipment_or_404(db, shipment_id)
    lines = {
        str(ln.id): ln
        for ln in db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == shipment.id)
        .all()
    }
    if not decisions:
        raise AppException(422, "Nothing was allocated.")

    from app.schemas.procurement import SPOAllocationCreate
    # Imported here, not at module level: `grn_spo_matching` imports
    # `procurement_service` at load time, so a top-level import would be a cycle.
    from app.services.grn_spo_matching import forward_match_grn_lines_for_spo_best_effort
    from app.services.procurement_service import SPOAllocationService

    service = SPOAllocationService(db)
    written = 0
    advanced: dict[str, float] = {}
    # (spo_number, company_id) pairs to forward match ONCE, when every allocation
    # this decision writes exists. One approval writes one allocation PER SPLIT -
    # several warehouses under one SPO number - so a hook fired per allocation row
    # runs while the rest of the decision does not exist yet, and places a waiting
    # GRN line against whichever allocation happened to be written first instead of
    # the one covering its warehouse (AC-FM-19). The SPO Excel import sweeps the
    # same way, for the same reason.
    forward_match_targets: set[tuple[str, Optional[str]]] = set()

    for decision in decisions:
        line = lines.get(str(decision.get("shipment_line_id") or ""))
        if line is None:
            raise AppException(
                422, "A line in this decision does not belong to this shipment."
            )
        splits = decision.get("splits") or []
        if not splits:
            raise AppException(422, "A line was submitted with no allocation on it.")

        outstanding = _round(
            float(line.quantity_shipped or 0) - float(line.spo_allocated_quantity or 0)
        )
        total = _round(sum(float(s.get("qty") or 0) for s in splits))
        if total != outstanding:
            raise AppException(
                422,
                "A split has to add up to what shipped.",
                detail=(
                    f"{total:g} allocated against {outstanding:g} shipped on this line."
                ),
            )

        for s in splits:
            qty = float(s.get("qty") or 0)
            if qty <= 0:
                raise AppException(422, "An allocation of nothing is not an allocation.")
            po_line_id = s.get("po_line_id") or None
            warehouse_id = s.get("warehouse_id")
            if not warehouse_id:
                raise AppException(422, "Every allocation needs a location to land in.")

            if po_line_id:
                po_line = (
                    db.query(PurchaseOrderLine)
                    .filter(PurchaseOrderLine.id == po_line_id)
                    .one_or_none()
                )
                if po_line is None:
                    raise AppException(422, "That purchase-order line no longer exists.")
                remaining = _round(
                    float(po_line.qty_ordered or 0) - float(po_line.qty_received or 0)
                )
                if _round(qty) > remaining:
                    raise AppException(
                        422,
                        "More was allocated to a purchase order than it still has outstanding.",
                        detail=f"{qty:g} against {remaining:g} outstanding.",
                    )
                # AC-G6: the quantity moves from Ordered to Incoming in ONE action. The
                # allocation raises `scm.on_order_v`; this makes `scm.po_ordered_v` fall.
                po_line.qty_received = float(po_line.qty_received or 0) + qty
                advanced[str(po_line.id)] = advanced.get(str(po_line.id), 0.0) + qty

            allocation = service.create_allocation(
                SPOAllocationCreate(
                    spo_number=shipment.shipment_number,
                    inbound_shipment_id=str(shipment.id),
                    product_id=str(line.product_id),
                    warehouse_id=str(warehouse_id),
                    allocated_quantity=qty,
                    po_line_id=str(po_line_id) if po_line_id else None,
                ),
                # `spo_allocations.created_by` is a UUID column holding a USER ID, not the
                # person's name as the SCM tables use it. An empty string is not a uuid.
                created_by=actor_id,
                # Not per row - see `forward_match_targets` above.
                forward_match=False,
            )
            target_spo = (
                str(allocation.spo_number) if allocation.spo_number is not None else ""
            )
            if target_spo:
                forward_match_targets.add(
                    (
                        target_spo,
                        str(allocation.company_id)
                        if allocation.company_id is not None
                        else None,
                    )
                )
            written += 1

    db.flush()

    # Every allocation this decision writes now exists, so a GRN line that stated
    # this SPO and could not be placed when it was imported is placeable - against
    # the allocation that actually covers its warehouse. Post-commit and
    # best-effort: a side effect must not fail an approval already written.
    for target_spo, target_company in forward_match_targets:
        forward_match_grn_lines_for_spo_best_effort(
            db, target_spo, company_id=target_company
        )

    return {
        "shipment_id": str(shipment.id),
        "allocations_written": written,
        "purchase_order_lines_advanced": len(advanced),
        "quantity_advanced": _round(sum(advanced.values())),
    }
