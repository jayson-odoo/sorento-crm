"""SCM M4 Slice B — human decision layer (Accept / Adjust / Reject) + the draft
PO it consolidates into.

The recommendation itself is NEVER mutated except for its ``status`` column
(proposed → accepted | adjusted | dismissed). Every qty / supplier override is
recorded APPEND-ONLY in ``scm.recommendation_override`` (M4-D7) — a second adjust
adds a second row, it never rewrites the first.

Accept/Adjust consolidate into ONE draft ``purchase_order`` per supplier (status
``draft_recommendation``, one line per SKU — M4-D4). A draft is deliberately OUTSIDE
``scm.on_order_v``'s status set so the next run never double-counts it as incoming
supply (M4-D5); confirming it (``purchase_order_service.bulk_confirm``) flips it to
``active`` and assigns the canonical ``PO-{year}/{month}-####`` number.

The rec → draft-PO-line link is carried on the line's ``source_ref`` (= rec id) so
the decision state (and its PO number) survives a confirm renumber without a schema
change. No UUIDs surface — suppliers/POs resolve to codes/numbers.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.scm import RecommendationOverride, ReorderRecommendation
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService

DRAFT_STATUS = "draft_recommendation"
_SRC = "scm_recommendation"


# ---------------------------------------------------------------------------
# lookups
# ---------------------------------------------------------------------------

def _get_buy_rec(db: Session, rec_id: str) -> ReorderRecommendation:
    rec = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.id == rec_id)
        .first()
    )
    if not rec:
        raise AppException(status_code=404, message="Recommendation not found.")
    if rec.rec_type != "buy":
        raise AppException(
            status_code=422,
            message="Only buy recommendations can be accepted, adjusted or rejected.",
        )
    return rec


def _supplier_id_for_code(db: Session, code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    sup = db.query(Supplier).filter(Supplier.supplier_code == code).first()
    return sup.id if sup else None


def _resolve_choice(
    db: Session, rec: ReorderRecommendation, override_supplier_code: Optional[str]
) -> dict:
    """Resolve the chosen supplier for a decision from the rec's FROZEN supplier +
    alternatives (the exact set the UI offered), falling back to a live
    ``product_suppliers`` lookup if an unknown code is passed.

    Returns ``{supplier_id, supplier_code, supplier_name, unit_cost, lead_time_days,
    switched}``. When no override code is given, the rec's proposed supplier stands.
    """
    inp = rec.inputs or {}
    proposed = inp.get("supplier") or {}

    if not override_supplier_code:
        return {
            "supplier_id": rec.supplier_id,
            "supplier_code": proposed.get("supplier_code"),
            "supplier_name": proposed.get("supplier_name"),
            "unit_cost": _f(rec.unit_cost) if rec.unit_cost is not None
            else _f(proposed.get("unit_cost")),
            "lead_time_days": proposed.get("lead_time_days"),
            "switched": False,
        }

    # frozen candidates (proposed + ranked alternatives) carry code/cost/lead
    candidates = [proposed] + list(inp.get("alternatives") or [])
    chosen = next(
        (c for c in candidates if c and c.get("supplier_code") == override_supplier_code),
        None,
    )
    supplier_id = _supplier_id_for_code(db, override_supplier_code)
    if chosen is None:
        # unknown to the frozen set — recompute cost/lead off product_suppliers
        chosen = _product_supplier_choice(db, rec.product_id, supplier_id) or {}
    switched = override_supplier_code != proposed.get("supplier_code")
    return {
        "supplier_id": supplier_id,
        "supplier_code": override_supplier_code,
        "supplier_name": chosen.get("supplier_name"),
        "unit_cost": _f(chosen.get("unit_cost")),
        "lead_time_days": chosen.get("lead_time_days"),
        "switched": switched,
    }


def _product_supplier_choice(
    db: Session, product_id: str, supplier_id: Optional[str]
) -> Optional[dict]:
    if not supplier_id:
        return None
    from sqlalchemy import text

    row = db.execute(
        text(
            """
            SELECT s.supplier_name, ps.unit_cost, ps.standard_lead_time_days AS lead
            FROM product_suppliers ps
            JOIN suppliers s ON s.id = ps.supplier_id
            WHERE ps.product_id = :p AND ps.supplier_id = :s
            LIMIT 1
            """
        ),
        {"p": product_id, "s": supplier_id},
    ).mappings().first()
    if not row:
        return None
    return {
        "supplier_name": row["supplier_name"],
        "unit_cost": _f(row["unit_cost"]),
        "lead_time_days": _f(row["lead"]),
    }


# ---------------------------------------------------------------------------
# draft-PO consolidation
# ---------------------------------------------------------------------------

def _draft_po_for_supplier(
    db: Session, supplier_id: Optional[str], currency: Optional[str]
) -> PurchaseOrder:
    """The open draft PO for a supplier, created on first accept (consolidation —
    M4-D4). One draft per supplier; a null supplier gets a single 'unassigned' draft."""
    q = db.query(PurchaseOrder).filter(
        PurchaseOrder.status == DRAFT_STATUS,
        PurchaseOrder.source_system == _SRC,
    )
    q = q.filter(PurchaseOrder.supplier_id == supplier_id) if supplier_id else \
        q.filter(PurchaseOrder.supplier_id.is_(None))
    po = q.first()
    if po:
        return po
    number = NumberingService(db).get_next_number(
        "purchase_order_draft", date.today(), commit_rule=False
    ) or f"PO-DRAFT-{uuid.uuid4().hex[:8]}"
    po = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=number,
        supplier_id=supplier_id,
        issue_date=date.today(),
        status=DRAFT_STATUS,
        currency=currency,
        source_system=_SRC,
        source_ref="scm",
    )
    db.add(po)
    db.flush()
    return po


def _remove_rec_line(db: Session, rec_id: str) -> None:
    """Drop a rec's line from whatever DRAFT PO it currently sits in (a prior
    accept/adjust that is being redirected or rejected). Deletes the draft if it
    empties. Only draft POs are touched — a confirmed (active) PO is never mutated."""
    line = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrderLine.source_ref == rec_id,
            PurchaseOrderLine.source_system == _SRC,
            PurchaseOrder.status == DRAFT_STATUS,
        )
        .first()
    )
    if not line:
        return
    po_id = line.purchase_order_id
    db.delete(line)
    db.flush()
    remaining = (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.purchase_order_id == po_id)
        .count()
    )
    if remaining == 0:
        po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
        if po is not None:
            db.delete(po)
            db.flush()


def _upsert_line(
    db: Session,
    po: PurchaseOrder,
    rec: ReorderRecommendation,
    qty: float,
    unit_cost: Optional[float],
    lead_days: Optional[float],
) -> None:
    expected = (
        date.today() + timedelta(days=int(lead_days))
        if lead_days is not None else None
    )
    line = (
        db.query(PurchaseOrderLine)
        .filter(
            PurchaseOrderLine.purchase_order_id == po.id,
            PurchaseOrderLine.source_ref == rec.id,
        )
        .first()
    )
    if line:
        line.qty_ordered = qty
        line.unit_cost = unit_cost
        line.expected_date = expected
    else:
        db.add(
            PurchaseOrderLine(
                id=str(uuid.uuid4()),
                purchase_order_id=po.id,
                product_id=rec.product_id,
                warehouse_id=rec.warehouse_id,
                qty_ordered=qty,
                qty_received=0,
                unit_cost=unit_cost,
                currency=po.currency,
                expected_date=expected,
                line_status="open",
                source_system=_SRC,
                source_ref=rec.id,
            )
        )
    db.flush()


def _result(po: PurchaseOrder, supplier_name: Optional[str]) -> dict:
    return {
        "draft_po_number": po.po_number,
        "draft_po_id": po.id,
        "supplier_name": supplier_name or "",
    }


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------

def accept_recommendation(db: Session, rec_id: str, actor: Optional[str]) -> dict:
    """Accept as proposed → consolidated draft PO for the rec's supplier (M4-D4)."""
    rec = _get_buy_rec(db, rec_id)
    choice = _resolve_choice(db, rec, None)
    _remove_rec_line(db, rec.id)
    po = _draft_po_for_supplier(db, choice["supplier_id"], rec.currency)
    _upsert_line(db, po, rec, float(rec.rounded_qty or 0),
                 choice["unit_cost"], choice["lead_time_days"])
    rec.status = "accepted"
    db.flush()
    return _result(po, choice["supplier_name"])


def adjust_recommendation(
    db: Session,
    rec_id: str,
    override_qty: float,
    override_supplier_code: Optional[str],
    reason_text: str,
    actor: Optional[str],
) -> dict:
    """Adjust qty and/or switch supplier (M4-D7). Writes an APPEND-ONLY override row,
    recomputes cost/lead off the chosen supplier, and redirects the draft PO line."""
    rec = _get_buy_rec(db, rec_id)
    if override_qty is None or float(override_qty) <= 0:
        raise AppException(status_code=422, message="Override quantity must be greater than zero.")
    if not (reason_text or "").strip():
        raise AppException(status_code=422, message="A reason is required to adjust a recommendation.")

    choice = _resolve_choice(db, rec, override_supplier_code)
    _remove_rec_line(db, rec.id)
    po = _draft_po_for_supplier(db, choice["supplier_id"], rec.currency)
    _upsert_line(db, po, rec, float(override_qty),
                 choice["unit_cost"], choice["lead_time_days"])

    db.add(
        RecommendationOverride(
            id=str(uuid.uuid4()),
            recommendation_id=rec.id,
            original_qty=rec.rounded_qty,
            override_qty=override_qty,
            override_supplier_id=choice["supplier_id"] if choice["switched"] else None,
            reason_text=reason_text.strip(),
            action_applied=False,
            overridden_by=actor,
            overridden_at=datetime.utcnow(),
            source_system="scm",
            source_ref="scm",
        )
    )
    rec.status = "adjusted"
    db.flush()
    return _result(po, choice["supplier_name"])


def reject_recommendation(
    db: Session, rec_id: str, reason_text: str, actor: Optional[str]
) -> dict:
    """Reject (M4-D8) → rec dismissed, reason stored (feedback trigger). Any draft PO
    line the rec previously landed in is pulled back out."""
    rec = _get_buy_rec(db, rec_id)
    if not (reason_text or "").strip():
        raise AppException(status_code=422, message="A reason is required to reject a recommendation.")
    _remove_rec_line(db, rec.id)
    db.add(
        RecommendationOverride(
            id=str(uuid.uuid4()),
            recommendation_id=rec.id,
            original_qty=rec.rounded_qty,
            override_qty=None,
            override_supplier_id=None,
            reason_text=reason_text.strip(),
            action_applied=False,
            overridden_by=actor,
            overridden_at=datetime.utcnow(),
            source_system="scm",
            source_ref="scm",
        )
    )
    rec.status = "dismissed"
    db.flush()
    return {}


def bulk_accept(db: Session, run_id: str, ids: list[str], actor: Optional[str]) -> dict:
    """Bulk Accept funded recs (M4-D9) — consolidates per supplier and reports how many
    distinct draft POs were touched."""
    recs = _run_recs(db, run_id, ids)
    touched: set[str] = set()
    for rec in recs:
        res = accept_recommendation(db, rec.id, actor)
        touched.add(res["draft_po_id"])
    return {"accepted_count": len(recs), "po_count": len(touched)}


def bulk_reject(
    db: Session, run_id: str, ids: list[str], reason_text: str, actor: Optional[str]
) -> dict:
    """Bulk Reject recs with one shared reason (M4-D9)."""
    recs = _run_recs(db, run_id, ids)
    for rec in recs:
        reject_recommendation(db, rec.id, reason_text, actor)
    return {"rejected_count": len(recs)}


def _run_recs(db: Session, run_id: str, ids: list[str]) -> list[ReorderRecommendation]:
    if not ids:
        return []
    return (
        db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.id.in_(ids),
            ReorderRecommendation.rec_type == "buy",
        )
        .all()
    )


# ---------------------------------------------------------------------------
# decision state for the results grid (status badges + PO hyperlink)
# ---------------------------------------------------------------------------

def list_decisions(db: Session, run_id: str) -> list[dict]:
    """Per-rec decision state for a run (status + linked draft/active PO + override
    detail). Drives the results-grid badges + the '→ PO' hyperlink. Only decided recs
    (status ≠ proposed) are returned."""
    recs = (
        db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.status.in_(("accepted", "adjusted", "dismissed")),
        )
        .all()
    )
    out: list[dict] = []
    for rec in recs:
        po = _po_for_rec(db, rec.id)
        override = (
            db.query(RecommendationOverride)
            .filter(RecommendationOverride.recommendation_id == rec.id)
            .order_by(RecommendationOverride.created_at.desc())
            .first()
        )
        sup_code = sup_name = None
        if override is not None and override.override_supplier_id is not None:
            sup = (
                db.query(Supplier)
                .filter(Supplier.id == override.override_supplier_id)
                .first()
            )
            if sup is not None:
                sup_code, sup_name = sup.supplier_code, sup.supplier_name
        out.append(
            {
                "recommendation_id": rec.id,
                "status": rec.status,
                "override_qty": _f(override.override_qty) if override else None,
                "override_supplier_code": sup_code,
                "override_supplier_name": sup_name,
                "reason_text": (override.reason_text if override else None),
                "draft_po_number": po.po_number if po else None,
                "draft_po_id": po.id if po else None,
            }
        )
    return out


def _po_for_rec(db: Session, rec_id: str) -> Optional[PurchaseOrder]:
    """The (draft or now-active) PO a rec's line lives in — resolved via the line's
    ``source_ref`` (= rec id), which survives a confirm renumber."""
    line = (
        db.query(PurchaseOrderLine)
        .options(joinedload(PurchaseOrderLine.purchase_order))
        .filter(
            PurchaseOrderLine.source_ref == rec_id,
            PurchaseOrderLine.source_system == _SRC,
        )
        .order_by(PurchaseOrderLine.created_at.desc())
        .first()
    )
    return line.purchase_order if line else None


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None
