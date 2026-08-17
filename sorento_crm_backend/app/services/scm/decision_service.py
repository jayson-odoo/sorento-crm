"""SCM M4 Slice B — human decision layer (Accept / Adjust / Reject) + the draft
PO the decisions consolidate into at CONFIRM time.

Decisions are STAGED, not immediately materialised: Accept / Adjust / Reject only
set the recommendation's ``status`` (proposed → accepted | adjusted | dismissed)
and, for adjust/reject, append a ``scm.recommendation_override`` row (M4-D7 — a
second adjust adds a second row, never rewrites the first). NO purchase order is
created until the human explicitly runs **Confirm decisions** (``confirm_decisions``)
— that is the point where accepted + adjusted recs are consolidated into ONE draft
``purchase_order`` per supplier (status ``draft_recommendation``, one line per SKU).
This gives the planner an editable overview before any PO exists.

A draft is deliberately OUTSIDE ``scm.on_order_v``'s status set so the next run
never double-counts it as incoming supply (M4-D5); confirming the DRAFT
(``purchase_order_service.bulk_confirm``) flips it to ``active`` and assigns the
canonical ``PO-{year}/{month}-####`` number.

The rec → draft-PO-line link is carried on the line's ``source_ref`` (= rec id) so
the decision state (and its PO number) survives a confirm renumber without a schema
change. ``confirm_decisions`` is idempotent — re-running it reconciles every line
to the rec's CURRENT decision (re-adjusted qty updated, rejected rec's line pulled).
No UUIDs surface — suppliers/POs resolve to codes/numbers.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.scm import RecommendationOverride, ReorderRecommendation, ReorderRun
from app.services.error_handler import AppException
from app.services.scm import plan_grain
from app.services.numbering_service import NumberingService

DRAFT_STATUS = "draft_recommendation"
_SRC = "scm_recommendation"


# ---------------------------------------------------------------------------
# lookups
# ---------------------------------------------------------------------------

def _assert_location_grain(db: Session, run_id: str) -> None:
    """A location decision may only be written on a run stamped at location grain.

    Product-grain runs decide through `summary_order_service.record_decision`, and a
    pre-contract run decides nowhere at all (plan 5.4, AC-F09). Shared with that service
    through `plan_grain.assert_decision_grain`, so the two refusals cannot drift.
    """
    run = db.query(ReorderRun).filter(ReorderRun.id == run_id).first()
    if run is None:
        raise AppException(status_code=404, message="Reorder run not found.")
    plan_grain.assert_decision_grain(run, plan_grain.LOCATION_GRAIN)


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


def _staged_result(supplier_name: Optional[str]) -> dict:
    """A decision is STAGED, not materialised — no PO exists yet (created only at
    Confirm decisions). The chosen supplier name drives the toast."""
    return {
        "draft_po_number": None,
        "draft_po_id": None,
        "supplier_name": supplier_name or "",
    }


def _line_inputs(
    db: Session, rec: ReorderRecommendation
) -> tuple[Optional[str], float, Optional[float], Optional[float], Optional[str]]:
    """Resolve (supplier_id, qty, unit_cost, lead_days, supplier_name) for a rec's
    draft-PO line at CONFIRM time, honouring the latest adjust override (qty +
    optional supplier switch); an accepted rec uses its proposed supplier + rounded qty."""
    if rec.status == "adjusted":
        ov = (
            db.query(RecommendationOverride)
            .filter(RecommendationOverride.recommendation_id == rec.id)
            # overridden_at is stamped explicitly (µs precision) so it's a
            # deterministic "latest" — created_at's DB default can tie within a txn.
            .order_by(RecommendationOverride.overridden_at.desc())
            .first()
        )
        qty = float(ov.override_qty) if ov and ov.override_qty is not None else float(rec.rounded_qty or 0)
        if ov is not None and ov.override_supplier_id:
            ps = _product_supplier_choice(db, rec.product_id, ov.override_supplier_id) or {}
            return (
                ov.override_supplier_id,
                qty,
                ps.get("unit_cost") if ps.get("unit_cost") is not None else _f(rec.unit_cost),
                ps.get("lead_time_days"),
                ps.get("supplier_name"),
            )
        choice = _resolve_choice(db, rec, None)
        return choice["supplier_id"], qty, choice["unit_cost"], choice["lead_time_days"], choice["supplier_name"]
    # accepted — proposed supplier, rounded qty as-is
    choice = _resolve_choice(db, rec, None)
    return (
        choice["supplier_id"],
        float(rec.rounded_qty or 0),
        choice["unit_cost"],
        choice["lead_time_days"],
        choice["supplier_name"],
    )


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------

def accept_recommendation(db: Session, rec_id: str, actor: Optional[str]) -> dict:
    """Stage an Accept (M4-D4) — sets status only, NO PO. The draft PO is created
    later at Confirm decisions, so the planner keeps an editable overview first."""
    rec = _get_buy_rec(db, rec_id)
    _assert_location_grain(db, str(rec.run_id))
    choice = _resolve_choice(db, rec, None)
    rec.status = "accepted"
    db.flush()
    return _staged_result(choice["supplier_name"])


def adjust_recommendation(
    db: Session,
    rec_id: str,
    override_qty: float,
    override_supplier_code: Optional[str],
    reason_text: str,
    actor: Optional[str],
) -> dict:
    """Stage an Adjust (M4-D7) — writes an APPEND-ONLY override row (qty + optional
    supplier switch) and sets status; NO PO. Confirm decisions consolidates the
    latest override into the draft PO line."""
    rec = _get_buy_rec(db, rec_id)
    _assert_location_grain(db, str(rec.run_id))
    if override_qty is None or float(override_qty) <= 0:
        raise AppException(status_code=422, message="Override quantity must be greater than zero.")
    if not (reason_text or "").strip():
        raise AppException(status_code=422, message="A reason is required to adjust a recommendation.")

    choice = _resolve_choice(db, rec, override_supplier_code)

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
    return _staged_result(choice["supplier_name"])


def reject_recommendation(
    db: Session, rec_id: str, reason_text: str, actor: Optional[str]
) -> dict:
    """Reject (M4-D8) → rec dismissed, reason stored (feedback trigger). Any draft PO
    line the rec previously landed in is pulled back out."""
    rec = _get_buy_rec(db, rec_id)
    _assert_location_grain(db, str(rec.run_id))
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
    """Bulk Accept funded recs (M4-D9) — STAGES each as accepted; no PO yet
    (materialised at Confirm decisions). ``po_count`` stays 0 for the staged step."""
    _assert_location_grain(db, run_id)
    recs = _run_recs(db, run_id, ids)
    for rec in recs:
        accept_recommendation(db, rec.id, actor)
    return {"accepted_count": len(recs), "po_count": 0}


def confirm_decisions(
    db: Session, run_id: str, ids: Optional[list[str]], actor: Optional[str]
) -> dict:
    """Materialise the staged decisions of a run into consolidated draft POs (M4-D4).

    Idempotent reconciler: for every decided rec (optionally narrowed to ``ids``)
    — accepted/adjusted → upsert its line into the supplier's draft PO (latest
    override qty/supplier honoured); dismissed → pull its line back out. Re-running
    after a re-adjust just updates the line. Returns how many decisions were
    confirmed and how many distinct draft POs were touched."""
    q = db.query(ReorderRecommendation).filter(
        ReorderRecommendation.run_id == run_id,
        ReorderRecommendation.status.in_(("accepted", "adjusted", "dismissed")),
        ReorderRecommendation.rec_type == "buy",
    )
    if ids:
        q = q.filter(ReorderRecommendation.id.in_(ids))
    recs = q.all()

    touched: set[str] = set()
    confirmed = 0
    for rec in recs:
        if rec.status == "dismissed":
            _remove_rec_line(db, rec.id)
            continue
        supplier_id, qty, unit_cost, lead, _name = _line_inputs(db, rec)
        # Clear any stale draft line first (e.g. a prior confirm under a since-switched
        # supplier), then consolidate into the current supplier's draft.
        _remove_rec_line(db, rec.id)
        po = _draft_po_for_supplier(db, supplier_id, rec.currency)
        _upsert_line(db, po, rec, qty, unit_cost, lead)
        touched.add(po.id)
        confirmed += 1
    db.flush()
    return {"confirmed_count": confirmed, "po_count": len(touched)}


def reset_run_decisions(db: Session, run_id: str, actor: Optional[str]) -> dict:
    """DEMO / ADMIN reset — return a run to its freshly-generated state so the
    accept / reject / adjust / confirm flow can be demonstrated again from scratch.

    For every buy rec on the run: pull its line out of any DRAFT PO (emptied drafts are
    deleted with it), drop its append-only override rows, and reset its status back to
    'proposed'. Only DRAFT (``draft_recommendation``) POs are touched — a confirmed
    (active) PO is a real order and is never rolled back. Idempotent: running it on an
    already-clean run is a no-op. Returns what was cleared for the toast."""
    recs = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.run_id == run_id)
        .all()
    )
    if not recs:
        raise AppException(status_code=404, message="Reorder run not found.")
    rec_ids = [r.id for r in recs]

    decisions_cleared = sum(
        1 for r in recs if r.status in ("accepted", "adjusted", "dismissed")
    )
    # 1) Detach every rec's draft-PO line (deletes drafts that empty out).
    for rec in recs:
        _remove_rec_line(db, rec.id)
    # 2) Drop the override overlay (adjust/reject reason rows).
    overrides_cleared = (
        db.query(RecommendationOverride)
        .filter(RecommendationOverride.recommendation_id.in_(rec_ids))
        .delete(synchronize_session=False)
    )
    # 3) Reset decision status to the as-generated value.
    for rec in recs:
        rec.status = "proposed"
    db.flush()
    return {
        "run_id": run_id,
        "decisions_cleared": decisions_cleared,
        "overrides_cleared": int(overrides_cleared or 0),
    }


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
            .order_by(RecommendationOverride.overridden_at.desc())
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


# ===========================================================================
# covered-by-stock decisions
# ===========================================================================

def decide_covered(db: Session, rec_id: str, choice: str,
                   actor: Optional[str] = None) -> dict:
    """Record the planner's answer on a covered-by-stock row, reversibly.

    > "after i click buy anyway, the line just disappeared ... it should stay on covered by
    >  stock table, not jumped anywhere, so I still can regret my decision"

    So the row NEVER changes ``rec_type`` and never leaves the list. The decision is a
    ``status`` on it, and either choice can be taken again or swapped: a decision the
    planner cannot see and cannot revisit is worse than no decision, because they cannot
    tell whether the click landed.

    ``pending`` clears it back to undecided.
    """
    rec = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.id == rec_id)
        .first()
    )
    if not rec:
        raise AppException(status_code=404, message="Recommendation not found.")
    if rec.rec_type != "covered":
        raise AppException(
            status_code=422,
            message="Only a covered-by-stock row can be decided this way.",
        )
    if choice not in ("use_stock", "buy", "pending"):
        raise AppException(
            status_code=422, message="Choice must be use_stock, buy or pending.")

    rec.status = "proposed" if choice == "pending" else choice
    db.flush()
    return {"choice": choice, "rec_type": rec.rec_type, "status": rec.status}
