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

from app.models.inventory import Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.scm import (
    PlanRowDecision,
    RecommendationOverride,
    ReorderRecommendation,
    ReorderRun,
)
from app.services.error_handler import AppException
from app.services.scm import plan_grain
from app.services.numbering_service import NumberingService

DRAFT_STATUS = "draft_recommendation"
_SRC = "scm_recommendation"


# ---------------------------------------------------------------------------
# lookups
# ---------------------------------------------------------------------------

def _run_or_404(db: Session, run_id: str) -> ReorderRun:
    run = db.query(ReorderRun).filter(ReorderRun.id == run_id).first()
    if run is None:
        raise AppException(status_code=404, message="Reorder run not found.")
    return run


def _assert_location_grain(db: Session, run_id: str) -> None:
    """A location decision may only be written on a run stamped at location grain.

    Product-grain runs decide through `summary_order_service.record_decision`, and a
    pre-contract run decides nowhere at all (plan 5.4, AC-F09). Shared with that service
    through `plan_grain.assert_decision_grain`, so the two refusals cannot drift.
    """
    plan_grain.assert_decision_grain(_run_or_404(db, run_id), plan_grain.LOCATION_GRAIN)


def _assert_not_legacy(db: Session, run_id: str) -> None:
    """A write that belongs to NEITHER grain still may not touch a legacy run (AC-F10).

    Clearing a run's decisions is not a decision, so it is not refused for being the other
    grain - a product-grain run's location recommendations are read-only and resetting
    them to as-generated changes nothing anybody decided. A legacy run is different: its
    history is closed, and rewriting the statuses on it would be an edit to a plan that is
    supposed to be immutable.
    """
    plan_grain.assert_not_legacy(_run_or_404(db, run_id))


def _get_buy_rec(db: Session, rec_id: str) -> ReorderRecommendation:
    """Accept / Adjust / Reject stay buy-only, on purpose — they materialise DIRECTLY
    into a draft PO line the moment they are decided, and a covered/needs_level row has
    no supplier commitment yet to raise a line against. `record_plan_row_decision`
    below is the RELAXED path (S16, captain 21 Aug): it records the decision on any
    decidable row and only reaches a PO at Confirm decisions, so it never needed this
    restriction — see `_get_decidable_rec`."""
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
    confirmed and how many distinct draft POs were touched.

    Guarded like the decisions it materialises (AC-F09): confirming is the step that turns
    staged location decisions into draft purchase orders, so a run that may not hold those
    decisions may not have them materialised either - otherwise the grain guard on Accept /
    Adjust / Reject is bypassed by whatever staged status a run happens to carry. Unchanged
    by S16 (the row decision, below): a product-grain run never drafts an internal
    ``purchase_orders`` row at all - it hands Joey a worklist to key in AutoCount instead -
    so ``plan_row_decision``'s buy portion only ever reaches a draft PO here, on a run
    already proven to be location-grain.

    S16 (captain 21 Aug): a rec that carries a ``plan_row_decision`` is reconciled from
    THAT record instead of the legacy accepted/adjusted/dismissed status - it is the
    newer, row-level decision and takes priority so the two mechanisms can never draft
    two different lines for the same rec. Only the buy portion of a mixture drafts;
    use_stock / use_po / skip portions never do (a mixture's other parts are recorded,
    not ordered)."""
    _assert_location_grain(db, run_id)

    plan_row_q = (
        db.query(ReorderRecommendation, PlanRowDecision)
        .join(PlanRowDecision, PlanRowDecision.recommendation_id == ReorderRecommendation.id)
        .filter(ReorderRecommendation.run_id == run_id)
    )
    if ids:
        plan_row_q = plan_row_q.filter(ReorderRecommendation.id.in_(ids))
    plan_row_pairs = plan_row_q.all()
    plan_row_rec_ids = {rec.id for rec, _ in plan_row_pairs}

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
        if rec.id in plan_row_rec_ids:
            continue  # the row decision below is authoritative for this rec
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

    for rec, decision in plan_row_pairs:
        buy_qty = float(decision.buy_qty or 0)
        # Clear any stale line first, same as the legacy loop above.
        _remove_rec_line(db, rec.id)
        if buy_qty <= 0:
            continue  # use_stock / use_po / skip / an all-non-buy mixture — nothing to draft
        choice = _resolve_choice(db, rec, None)
        po = _draft_po_for_supplier(db, choice["supplier_id"], rec.currency)
        _upsert_line(db, po, rec, buy_qty, choice["unit_cost"], choice["lead_time_days"])
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
    already-clean run is a no-op. Returns what was cleared for the toast.

    Refused on a legacy run (AC-F10): its decisions are history, and a demo reset that
    rewrote them would edit a plan nothing else may touch. S16: also drops every
    ``plan_row_decision`` on the run, so the header's decided count goes back to zero
    along with everything else this clears."""
    _assert_not_legacy(db, run_id)
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
    plan_row_decisions_cleared = (
        db.query(PlanRowDecision)
        .filter(PlanRowDecision.recommendation_id.in_(rec_ids))
        .count()
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
    # 2b) Drop the row decisions (S16).
    db.query(PlanRowDecision).filter(
        PlanRowDecision.recommendation_id.in_(rec_ids)
    ).delete(synchronize_session=False)
    # 3) Reset decision status to the as-generated value.
    for rec in recs:
        rec.status = "proposed"
    db.flush()
    return {
        "run_id": run_id,
        "decisions_cleared": decisions_cleared,
        "overrides_cleared": int(overrides_cleared or 0),
        "plan_row_decisions_cleared": int(plan_row_decisions_cleared or 0),
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
    # A covered-by-stock answer IS a location decision - it is what turns a location's
    # stock into either cover or a purchase - so it is guarded exactly like Accept /
    # Adjust / Reject, and in the same order as them: what the row is, then what the run
    # may hold (AC-F09, AC-F10).
    _assert_location_grain(db, str(rec.run_id))
    if choice not in ("use_stock", "buy", "pending"):
        raise AppException(
            status_code=422, message="Choice must be use_stock, buy or pending.")

    rec.status = "proposed" if choice == "pending" else choice
    db.flush()
    return {"choice": choice, "rec_type": rec.rec_type, "status": rec.status}


# ===========================================================================
# S16 — the row decision: buy / use stock / use PO / skip, or a mixture
# (captain, 21 Aug, 3rd time requested: "I want the decision made here").
#
# use_stock records the buyer's INTENTION only. It never writes a stock hold/reserve -
# that would collide with the project-sales ladder's own reservations against the same
# stock. The buy portion of a decision is the only part that ever reaches a PO, and only
# at Confirm decisions (`confirm_decisions`, above) — recording a decision here never
# drafts anything by itself, same staged-not-materialised doctrine as Accept/Adjust.
# ===========================================================================

#: Every value the `kind` field may carry. `mixture` is the captain's 4th option — more
#: than one of buy/stock/po at once — distinct from picking exactly one of the first
#: three; `skip` is deliberately doing nothing this round.
_PLAN_ROW_KINDS = {"buy", "use_stock", "use_po", "skip", "mixture"}

#: Every rec_type this decision may be recorded on. Wider than `_get_buy_rec`'s buy-only
#: gate on purpose (S16 gap #2) — a needs_level or covered row the buyer overrides with
#: use_stock/use_po/skip is a real decision. `exception` is excluded: it never reaches
#: the results grid (`usePlanLines` fetches buy/covered/needs_level/disposition only)
#: and carries no qty a decision could size against.
_PLAN_ROW_DECIDABLE_TYPES = {"buy", "covered", "needs_level", "disposition"}


def _get_decidable_rec(db: Session, rec_id: str) -> ReorderRecommendation:
    rec = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.id == rec_id)
        .first()
    )
    if not rec:
        raise AppException(status_code=404, message="Recommendation not found.")
    if rec.rec_type not in _PLAN_ROW_DECIDABLE_TYPES:
        raise AppException(
            status_code=422,
            message="This row cannot carry a buy / use-stock / use-PO decision.",
        )
    return rec


def _resolve_stock_takes(db: Session, stock_takes: Optional[list[dict]]) -> list[dict]:
    """Resolve each named bin's warehouse CODE to a display name, dropping zero/blank
    entries. Stored and returned by code, never a UUID (mirrors override_supplier_code)."""
    out: list[dict] = []
    for s in stock_takes or []:
        qty = float((s or {}).get("qty") or 0)
        code = (s or {}).get("location")
        if qty <= 0 or not code:
            continue
        wh = db.query(Warehouse).filter(Warehouse.warehouse_code == code).first()
        out.append({"location": code, "location_name": wh.warehouse_name if wh else None, "qty": qty})
    return out


def _validate_plan_row_decision(
    kind: str, buy_qty: float, stock_qty_total: float, po_qty: float
) -> None:
    if kind not in _PLAN_ROW_KINDS:
        raise AppException(
            status_code=422,
            message="Kind must be buy, use_stock, use_po, skip or mixture.",
        )
    n_positive = sum(1 for q in (buy_qty, stock_qty_total, po_qty) if q > 0)
    if kind == "skip":
        if n_positive:
            raise AppException(
                status_code=422,
                message="Skip cannot also carry a buy, stock or PO quantity.",
            )
        return
    if n_positive == 0:
        raise AppException(
            status_code=422,
            message="A decision needs at least one quantity, or Skip.",
        )
    if kind == "mixture" and n_positive < 2:
        raise AppException(
            status_code=422, message="A mixture needs more than one part.",
        )
    single = {"buy": buy_qty, "use_stock": stock_qty_total, "use_po": po_qty}
    if kind in single and n_positive > 1:
        raise AppException(
            status_code=422,
            message=f"A {kind} decision cannot also carry another part's quantity — use mixture.",
        )


def record_plan_row_decision(
    db: Session,
    rec_id: str,
    kind: str,
    buy_qty: Optional[float],
    stock_takes: Optional[list[dict]],
    po_qty: Optional[float],
    po_refs: Optional[list[str]],
    reason_text: Optional[str],
    actor: Optional[str],
) -> dict:
    """Record (replacing, if one already exists) the buyer's decision on ONE row.

    Staged only — this never touches a purchase order. The buy portion reaches a draft
    PO line only once ``confirm_decisions`` runs, same doctrine as Accept/Adjust. Does
    NOT touch ``rec.status`` — that column stays the legacy accept/adjust/reject/covered
    vocabulary for whatever screen still reads it; this is a parallel, row-scoped record
    that ``confirm_decisions`` treats as authoritative for a rec the moment it exists
    (see that function's docstring)."""
    rec = _get_decidable_rec(db, rec_id)
    _assert_not_legacy(db, str(rec.run_id))

    buy_qty_f = float(buy_qty or 0)
    resolved_takes = _resolve_stock_takes(db, stock_takes)
    stock_total = sum(t["qty"] for t in resolved_takes)
    po_qty_f = float(po_qty or 0)
    _validate_plan_row_decision(kind, buy_qty_f, stock_total, po_qty_f)

    existing = (
        db.query(PlanRowDecision)
        .filter(PlanRowDecision.recommendation_id == rec.id)
        .first()
    )
    if existing is None:
        existing = PlanRowDecision(id=str(uuid.uuid4()), recommendation_id=rec.id)
        db.add(existing)
    existing.kind = kind
    existing.buy_qty = buy_qty_f or None
    existing.stock_takes = resolved_takes or None
    existing.po_qty = po_qty_f or None
    existing.po_refs = [r for r in (po_refs or []) if r] or None
    existing.reason_text = (reason_text or "").strip() or None
    existing.decided_by = actor
    existing.decided_at = datetime.utcnow()
    db.flush()
    return _plan_row_decision_dict(existing, _po_for_rec(db, rec.id))


def clear_plan_row_decision(db: Session, rec_id: str, actor: Optional[str]) -> dict:
    """Withdraw a row decision back to undecided. Idempotent — clearing an already-
    undecided row is a no-op. Also retracts any draft-PO line a prior Confirm decisions
    raised off it immediately, rather than waiting for the next confirm to notice."""
    rec = _get_decidable_rec(db, rec_id)
    _assert_not_legacy(db, str(rec.run_id))
    deleted = (
        db.query(PlanRowDecision)
        .filter(PlanRowDecision.recommendation_id == rec.id)
        .delete(synchronize_session=False)
    )
    _remove_rec_line(db, rec.id)
    db.flush()
    return {"cleared": bool(deleted)}


def list_plan_row_decisions(db: Session, run_id: str) -> dict:
    """Every persisted row decision on a run, across every decidable rec_type, plus the
    counts the results-grid header ("N of Total made") counts against — computed off
    what is actually persisted, never off a client's own session state."""
    total = (
        db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.rec_type.in_(_PLAN_ROW_DECIDABLE_TYPES),
        )
        .count()
    )
    pairs = (
        db.query(PlanRowDecision, ReorderRecommendation.id)
        .join(ReorderRecommendation, ReorderRecommendation.id == PlanRowDecision.recommendation_id)
        .filter(ReorderRecommendation.run_id == run_id)
        .all()
    )
    data = [
        _plan_row_decision_dict(decision, _po_for_rec(db, rec_id))
        for decision, rec_id in pairs
    ]
    return {"data": data, "decided_count": len(data), "total_count": total}


def _plan_row_decision_dict(decision: PlanRowDecision, po: Optional[PurchaseOrder]) -> dict:
    return {
        "recommendation_id": decision.recommendation_id,
        "kind": decision.kind,
        "buy_qty": _f(decision.buy_qty),
        "stock_takes": decision.stock_takes or [],
        "po_qty": _f(decision.po_qty),
        "po_refs": decision.po_refs or [],
        "reason_text": decision.reason_text,
        "draft_po_number": po.po_number if po else None,
        "draft_po_id": po.id if po else None,
    }
