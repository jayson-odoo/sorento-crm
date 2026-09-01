"""SCM M4 Slice B - human decision layer (Accept / Adjust / Reject) + the draft
PO the decisions consolidate into at CONFIRM time.

Decisions are STAGED, not immediately materialised: Accept / Adjust / Reject only
set the recommendation's ``status`` (proposed → accepted | adjusted | dismissed)
and, for adjust/reject, append a ``scm.recommendation_override`` row (M4-D7 - a
second adjust adds a second row, never rewrites the first). NO purchase order is
created until the human explicitly runs **Confirm decisions** (``confirm_decisions``)
 - that is the point where accepted + adjusted recs are consolidated into ONE draft
``purchase_order`` per supplier (status ``draft_recommendation``, one line per SKU).
This gives the planner an editable overview before any PO exists.

A draft is deliberately OUTSIDE ``scm.on_order_v``'s status set so the next run
never double-counts it as incoming supply (M4-D5); confirming the DRAFT
(``purchase_order_service.bulk_confirm``) flips it to ``active`` and assigns the
canonical ``PO-{year}/{month}-####`` number.

The rec → draft-PO-line link is carried on the line's ``source_ref`` (= rec id) so
the decision state (and its PO number) survives a confirm renumber without a schema
change. ``confirm_decisions`` is idempotent - re-running it reconciles every line
to the rec's CURRENT decision (re-adjusted qty updated, rejected rec's line pulled).
No UUIDs surface - suppliers/POs resolve to codes/numbers.

**Both plan grains reach a draft PO here now** (captain, 21 Aug - reverses the
original doctrine that a product-grain run never drafted an internal
``purchase_orders`` row and only ever produced the AutoCount keying worklist).
``confirm_decisions`` dispatches on the run's own stamped grain: a LOCATION run
reconciles recommendation-level decisions (accept/adjust/reject, or the newer S16
``plan_row_decision``) via ``_confirm_location_grain``; a PRODUCT run reconciles via
``_confirm_product_grain``, which itself has TWO decision surfaces and a strict
precedence between them - the results grid's Decision pills (``PlanRowDecision`` on
the run's member recs, S16, the captain's actual screen: "I need the confirm decision
to be in reorder planning, not in another page called order summary") are
AUTHORITATIVE; the Summary Order Report's own ``OrderSummaryRow.chosen_qty`` /
``chosen_supplier_id`` (``summary_order_service.record_decision``) is the fallback for
a product the grid has no decision for. See that function's own docstring for why
(the fan-out shape, the consolidation-per-product, the precedence). Confirming that
draft (``purchase_order_service.bulk_confirm``) then triggers the order-inquiry
auto-place cascade the same way a project-supply decision confirm does - placement
never waits on a person clicking a separate button. The po_worklist AutoCount path is
unchanged and unaffected either way.
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
from app.services.scm.reorder_engine import allocate as eng_allocate
from app.services.numbering_service import NumberingService

DRAFT_STATUS = "draft_recommendation"
_SRC = "scm_recommendation"
#: The draft-PO-line stamp for a PRODUCT-grain decision (`OrderSummaryRow.chosen_qty`,
#: captain 21 Aug - reverses the old "product grain never drafts a PO" doctrine below).
#: Kept distinct from `_SRC` so a location-grain rec id and a product-grain row id can
#: never collide inside the same lookup, even though both are UUIDs.
_SRC_PRODUCT = "scm_order_summary_row"


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
    """Accept / Adjust / Reject stay buy-only, on purpose - they materialise DIRECTLY
    into a draft PO line the moment they are decided, and a covered/needs_level row has
    no supplier commitment yet to raise a line against. `record_plan_row_decision`
    below is the RELAXED path (S16, captain 21 Aug): it records the decision on any
    decidable row and only reaches a PO at Confirm decisions, so it never needed this
    restriction - see `_get_decidable_rec`."""
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


def _supplier_code_for_id(db: Session, supplier_id: Optional[str]) -> Optional[str]:
    """The CODE a stored supplier id names. `_resolve_choice` is keyed by code (the frozen
    candidates carry codes, never ids), and the decision stores an id because that is what
    a foreign key can hold - so a decided supplier round-trips through here."""
    if not supplier_id:
        return None
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    return sup.supplier_code if sup else None


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
        # unknown to the frozen set - recompute cost/lead off product_suppliers
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
    """The open draft PO for a supplier, created on first accept (consolidation - 
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


def _remove_source_line(db: Session, source_ref: str, source_system: str = _SRC) -> None:
    """Drop a `(source_system, source_ref)` line from whatever DRAFT PO it currently
    sits in (a prior decision being redirected, cleared, or rejected). Deletes the
    draft if it empties. Only draft POs are touched - a confirmed (active) PO is never
    mutated. Shared by both grains - `_remove_rec_line` is the location-grain (rec id)
    alias every existing caller uses. A product-grain caller drafts more than one line
    per product (B2, `_remove_product_lines` below), so it does not call this directly."""
    line = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrderLine.source_ref == source_ref,
            PurchaseOrderLine.source_system == source_system,
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


def _remove_rec_line(db: Session, rec_id: str) -> None:
    """Location-grain alias of `_remove_source_line` - every existing (rec-id-keyed)
    call site is unchanged."""
    _remove_source_line(db, rec_id, _SRC)


def _upsert_line(
    db: Session,
    po: PurchaseOrder,
    *,
    product_id: str,
    warehouse_id: Optional[str],
    source_ref: str,
    qty: float,
    unit_cost: Optional[float],
    lead_days: Optional[float],
    source_system: str = _SRC,
) -> None:
    """Upsert ONE draft-PO line keyed by `(source_system, source_ref)`.

    Shared by both grains: a location-grain caller passes a recommendation's own id
    under `_SRC` (one line per warehouse rec, or None for a network-wide buy that names
    no single location). A product-grain caller (`_SRC_PRODUCT`) always passes a REAL
    `warehouse_id` too (B2, code review 21 Aug) - either the deciding member
    recommendation's own one (grid path) or a persisted location allocation's one
    (Summary Order Report fallback) - never None: `scm.po_ordered_v` and
    `CoverageService` both filter/join on `warehouse_id`, so a NULL one is invisible to
    the next run's supply and gets re-suggested. Either grain re-confirms onto the SAME
    line rather than duplicating one, as long as the caller passes the SAME
    `source_ref` it used last time.
    """
    expected = (
        date.today() + timedelta(days=int(lead_days))
        if lead_days is not None else None
    )
    line = (
        db.query(PurchaseOrderLine)
        .filter(
            PurchaseOrderLine.purchase_order_id == po.id,
            PurchaseOrderLine.source_ref == source_ref,
            PurchaseOrderLine.source_system == source_system,
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
                product_id=product_id,
                warehouse_id=warehouse_id,
                qty_ordered=qty,
                qty_received=0,
                unit_cost=unit_cost,
                currency=po.currency,
                expected_date=expected,
                line_status="open",
                source_system=source_system,
                source_ref=source_ref,
            )
        )
    db.flush()


def _staged_result(supplier_name: Optional[str]) -> dict:
    """A decision is STAGED, not materialised - no PO exists yet (created only at
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
            # deterministic "latest" - created_at's DB default can tie within a txn.
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
    # accepted - proposed supplier, rounded qty as-is
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
    """Stage an Accept (M4-D4) - sets status only, NO PO. The draft PO is created
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
    """Stage an Adjust (M4-D7) - writes an APPEND-ONLY override row (qty + optional
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
    """Bulk Accept funded recs (M4-D9) - STAGES each as accepted; no PO yet
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

    Dispatches on the run's own stamped grain (AC-F09): a legacy run holds no
    actionable decision at all and is refused outright; a LOCATION run reconciles its
    recommendation-level decisions (``_confirm_location_grain``, unchanged since M4);
    a PRODUCT run reconciles via ``_confirm_product_grain``, which is itself decided
    from the results grid's Decision pills first and the Summary Order Report's own
    quantity-sheet decision only as a fallback (see that function's docstring).
    Reversed doctrine (captain, 21 Aug): a product-grain run used to hand Joey a
    worklist to key in AutoCount and NOTHING ELSE - now "decide buy on the row" also
    drafts an internal PO the same way a location decision does, so confirming it can
    in turn trigger the order-inquiry auto-place cascade
    (``purchase_order_service.bulk_confirm``). The worklist is untouched either way -
    it is a read of the same decisions, not the only route to a PO any more."""
    run = _run_or_404(db, run_id)
    plan_grain.assert_not_legacy(run)
    if plan_grain.decision_grain_of(run) == plan_grain.PRODUCT_GRAIN:
        return _confirm_product_grain(db, run_id, ids, actor)
    return _confirm_location_grain(db, run_id, ids, actor)


def _confirm_location_grain(
    db: Session, run_id: str, ids: Optional[list[str]], actor: Optional[str]
) -> dict:
    """The LOCATION-grain half of ``confirm_decisions`` (M4-D4).

    Idempotent reconciler: for every decided rec (optionally narrowed to ``ids``)
  - accepted/adjusted → upsert its line into the supplier's draft PO (latest
    override qty/supplier honoured); dismissed → pull its line back out. Re-running
    after a re-adjust just updates the line. Returns how many decisions were
    confirmed and how many distinct draft POs were touched.

    Guarded like the decisions it materialises (AC-F09): confirming is the step that
    turns staged location decisions into draft purchase orders, so a run that may not
    hold those decisions may not have them materialised either - otherwise the grain
    guard on Accept / Adjust / Reject is bypassed by whatever staged status a run
    happens to carry.

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
        _upsert_line(
            db, po, product_id=rec.product_id, warehouse_id=rec.warehouse_id,
            source_ref=rec.id, qty=qty, unit_cost=unit_cost, lead_days=lead,
        )
        touched.add(po.id)
        confirmed += 1

    for rec, decision in plan_row_pairs:
        buy_qty = float(decision.buy_qty or 0)
        # Clear any stale line first, same as the legacy loop above.
        _remove_rec_line(db, rec.id)
        if buy_qty <= 0:
            continue  # use_stock / use_po / skip / an all-non-buy mixture - nothing to draft
        supplier_id, unit_cost, lead_days = _decision_line_inputs(db, rec, decision)
        po = _draft_po_for_supplier(db, supplier_id, rec.currency)
        _upsert_line(
            db, po, product_id=rec.product_id, warehouse_id=rec.warehouse_id,
            source_ref=rec.id, qty=buy_qty, unit_cost=unit_cost,
            lead_days=lead_days,
        )
        touched.add(po.id)
        confirmed += 1

    # The rows NOBODY touched (R3), which carries no grain qualifier: "Confirm covers
    # untouched rows as the engine suggestion". A location run's buyer who leaves a row
    # alone expects the same "make this plan" behaviour a product run gives them, and
    # before this an untouched rec matched neither loop above (status still `proposed`,
    # no `PlanRowDecision`) and was silently left out. Only a BUY the engine sized counts,
    # and a skipped or otherwise decided row has a decision already, so it never reaches
    # here.
    decided_ids = plan_row_rec_ids | {rec.id for rec in recs}
    untouched_q = db.query(ReorderRecommendation).filter(
        ReorderRecommendation.run_id == run_id,
        ReorderRecommendation.rec_type == "buy",
    )
    if ids:
        untouched_q = untouched_q.filter(ReorderRecommendation.id.in_(ids))
    for rec in untouched_q.all():
        if rec.id in decided_ids:
            continue
        qty = float(rec.rounded_qty or 0)
        if qty <= 0:
            continue  # the engine saying "do not buy this", not an absent decision
        # The rec's own proposed supplier and frozen price - the same resolution the
        # product-grain untouched branch uses, since nobody chose anything else.
        choice = _resolve_choice(db, rec, None)
        _remove_rec_line(db, rec.id)
        po = _draft_po_for_supplier(db, choice["supplier_id"], rec.currency)
        _upsert_line(
            db, po, product_id=rec.product_id, warehouse_id=rec.warehouse_id,
            source_ref=rec.id, qty=qty, unit_cost=choice["unit_cost"],
            lead_days=choice["lead_time_days"],
        )
        touched.add(po.id)
        # Recorded like any other decision, so the pill reads Confirmed and the counts
        # catch up with the purchase order that was just drafted (same as product grain).
        _record_confirmed_suggestion(db, [rec], qty, actor)
        confirmed += 1

    db.flush()
    return {"confirmed_count": confirmed, "po_count": len(touched)}


def _remove_product_lines(db: Session, product_id: str) -> None:
    """Drop EVERY product-grain draft line for this product, from whatever draft PO(s)
    they sit in (code review, 21 Aug, B2: a product-grain draft is now split across its
    real member warehouses, so a product can hold more than one line - reconciling it
    means clearing the whole set before redrafting, not one key). Deletes a draft PO
    that empties out. Only draft POs are touched."""
    lines = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrderLine.product_id == product_id,
            PurchaseOrderLine.source_system == _SRC_PRODUCT,
            PurchaseOrder.status == DRAFT_STATUS,
        )
        .all()
    )
    if not lines:
        return
    po_ids = {line.purchase_order_id for line in lines}
    for line in lines:
        db.delete(line)
    db.flush()
    for po_id in po_ids:
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


def _grid_member_split(
    members: list[ReorderRecommendation], qty: float
) -> dict[str, float]:
    """Apportion ONE product-grain decided quantity across its REAL member warehouses
    (code review, 21 Aug, B2). ``usePlanLines.decide`` fans the SAME ``buy_qty`` onto
    every member of a grouped product row rather than splitting it, so drafting each
    member's own value as-is would order the total once per member instead of once for
    the product. This apportions it instead - the SAME weighting
    (``summary_order_service._persist_location_split``) uses for the Summary Order
    Report's own ``chosen_qty`` (each member's frozen deficit as the weight) - so every
    drafted line names a REAL warehouse. A NULL one is invisible to the views the next
    run's shortfall is computed from (``scm.po_ordered_v`` groups by
    ``(product_id, warehouse_id)``; ``CoverageService._supply_events_many`` filters
    ``PurchaseOrderLine.warehouse_id.in_(wh_ids)``, and a NULL warehouse matches
    neither) - so a NULL-warehouse line would leave the buy invisible to the next
    run's supply and get re-suggested, the double-order both of those already guard
    against for a genuine warehouse.
    """
    inputs = []
    for rec in members:
        deficit = float(rec.rounded_qty or 0)
        if deficit <= 0:
            net_position = float(rec.net_position) if rec.net_position is not None else 0.0
            deficit = max(-net_position, 0.0)
        inputs.append({
            "warehouse_id": str(rec.warehouse_id),
            "deficit": deficit,
            "demand_rate": float(rec.forecast_daily_demand or 0.0),
        })
    return eng_allocate(qty, inputs, decimal_places=0)


def _record_confirmed_suggestion(
    db: Session, members: list[ReorderRecommendation], qty: float, actor: Optional[str]
) -> None:
    """Write the decision an UNTOUCHED row was just confirmed at (R3).

    Confirm is the buyer saying "make this plan", so a product nobody touched is bought at
    exactly what the engine sized - and that IS a decision, which has to be recorded like
    any other or the screen keeps saying nobody made one: the pill stayed on Suggested,
    the tiles and the list's Decided column stayed short, and Confirm (N) stayed live over
    rows that had already been drafted into a purchase order.

    ``buy_qty`` is the PRODUCT's whole quantity on every member, never that member's share
    of the split. That is the same shape ``usePlanLines.decide`` writes when a person
    decides a grouped row (the SAME decision fanned onto every member, consolidated back
    to one on confirm - see ``_confirm_product_grain``), so a re-confirm reads this back
    through the grid path and drafts exactly the lines this one did.

    Nothing else is stored: no supplier (the rec's proposed one stands, which is what
    ``_resolve_choice(rec, None)`` answered above) and no unit cost (``use_last`` re-reads
    the same frozen figure). A row that already carries a decision never reaches here.
    """
    now = datetime.utcnow()
    for member in members:
        db.add(PlanRowDecision(
            id=str(uuid.uuid4()),
            recommendation_id=member.id,
            kind="buy",
            buy_qty=qty,
            price_mode=DEFAULT_PRICE_MODE,
            decided_by=actor,
            decided_at=now,
        ))
    db.flush()


def _confirm_product_grain(
    db: Session, run_id: str, ids: Optional[list[str]], actor: Optional[str]
) -> dict:
    """The PRODUCT-grain half of ``confirm_decisions`` (captain, 21 Aug; corrected the
    same day once the captain named the actual screen: "I need the confirm decision to
    be in reorder planning, not in another page called order summary").

    A product-grain run carries the SAME decision on TWO surfaces, and this reconciles
    them with a strict precedence:

    1. **The results grid's Decision pills** (``PlanRowDecision``, S16) - the
       AUTHORITATIVE source. The grid decides on the run's per-warehouse member
       recommendations, grouped into one row per product (``planLineGrouping.ts``):
       ``usePlanLines.decide`` fans the SAME decision out to EVERY member rec of that
       group (mirrors ``updateMoq``'s own fan-out) - it does NOT split the quantity
       across members, so a product with three warehouse members gets the identical
       ``buy_qty`` written three times, once per member. Consolidating this therefore
       means picking ONE representative member for the QUANTITY and SUPPLIER (not
       summing, which would triple-count a 3-location product), then splitting that
       one quantity back across the group's real member warehouses
       (``_grid_member_split``, B2) so every drafted line names a real one. The
       representative is the most-recently-decided member (ties broken by rec id for a
       deterministic pick), which only matters when a partial fan-out failure left
       members disagreeing - the ordinary case has every member identical by
       construction. Only the BUY portion of a mixture drafts, exactly like the
       location-grain plan-row loop above: use_stock / use_po / skip portions never do.
    2. **The Summary Order Report's Set-quantity sheet** (``OrderSummaryRow.
       chosen_qty`` / ``chosen_supplier_id``, ``summary_order_service.record_decision``)
     - the FALLBACK, read only for a product the grid has no decision for. This
       mirrors S16's own doctrine that a row decision is authoritative over the older
       mechanism it supersedes (see ``confirm_decisions``' docstring on
       ``PlanRowDecision`` vs. legacy rec status) - here it is the grid decision that
       is the newer, row-level mechanism, and the Summary Order Report's own decision
       predates it. Its own location split is already persisted
       (``OrderSummaryLocationAllocation``, written by ``record_decision`` ->
       ``_persist_location_split``) so this reads it rather than re-deriving one.

    Both surfaces draft into the SAME set of lines for a product - one draft PO per
    chosen supplier, one line per REAL warehouse the quantity actually lands in. A
    product can therefore hold more than one line; reconciling it clears the whole set
    first (``_remove_product_lines``) rather than one key, so a re-decision (or a
    precedence flip between the two surfaces) never leaves an orphaned line from the
    other shape. Line identity is the deciding recommendation/allocation, never the
    product alone: the grid path keys each line by its OWN member recommendation id
    (stable across re-decisions of that member, the same shape the location-grain loop
    above uses); the fallback path keys each line by ``"{row_id}:{warehouse_id}"``
    (stable across a re-split, which always replaces ``OrderSummaryLocationAllocation``
    wholesale and would hand out fresh row ids of its own otherwise). ``ids``
    (optional) narrows to specific product, ``OrderSummaryRow``, or
    member-recommendation ids; empty confirms every decided product.

    Price and lead time are read exactly the way the PO worklist already resolves them
    per (product, supplier) (``summary_order_service.lead_times_for_pairs``) rather
    than a second lookup, so the drafted lines and the worklist a buyer already saw can
    never disagree.
    """
    from app.models.scm import OrderSummaryLocationAllocation, OrderSummaryRow
    from app.services.scm.summary_order_service import lead_times_for_pairs

    # 1) the grid's own decisions - every (rec, decision) pair for this run's member
    # recs, grouped by product. Every member with a decision stays in the group (used
    # both to pick the representative below and as the split's own weights).
    plan_row_pairs = (
        db.query(ReorderRecommendation, PlanRowDecision)
        .join(PlanRowDecision, PlanRowDecision.recommendation_id == ReorderRecommendation.id)
        .filter(ReorderRecommendation.run_id == run_id)
        .all()
    )
    by_product: dict[str, list] = {}
    for rec, decision in plan_row_pairs:
        by_product.setdefault(str(rec.product_id), []).append((rec, decision))
    grid_repr_for_product: dict[str, tuple] = {}
    for pid, entries in by_product.items():
        entries_sorted = sorted(
            entries, key=lambda e: (e[1].decided_at or datetime.min, str(e[0].id)),
            reverse=True,
        )
        grid_repr_for_product[pid] = entries_sorted[0]

    # 2) the Summary Order Report's own decisions - fallback only, for a product the
    # grid never decided.
    summary_rows = {
        str(r.product_id): r
        for r in db.query(OrderSummaryRow).filter(
            OrderSummaryRow.run_id == run_id, OrderSummaryRow.chosen_qty.isnot(None),
        ).all()
    }

    # 3) the products NOBODY touched (R3, revamp plan 4.5). Confirm is the buyer saying
    # "make this plan", so a product they left alone is bought at exactly what the engine
    # sized - before this they had to open and re-record every row they already agreed
    # with in order to buy any of it. Only a BUY the engine sized counts: a `covered` row
    # is the engine saying the stock is already there, and a rounded quantity of zero is it
    # saying do not buy this, so neither becomes a purchase for want of a decision. A
    # SKIPPED product is excluded by construction - it HAS a decision, which is the grid
    # path above, and that path drafts nothing for it.
    untouched: dict[str, list] = {}
    for rec in (
        db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.rec_type == "buy",
        )
        .all()
    ):
        pid = str(rec.product_id)
        if pid in grid_repr_for_product or pid in summary_rows:
            continue
        if float(rec.rounded_qty or 0) <= 0:
            continue
        untouched.setdefault(pid, []).append(rec)

    product_ids = set(grid_repr_for_product) | set(summary_rows) | set(untouched)
    if ids:
        wanted = set(ids)

        def _matches(pid: str) -> bool:
            if pid in wanted:
                return True
            row = summary_rows.get(pid)
            if row is not None and row.id in wanted:
                return True
            gd = grid_repr_for_product.get(pid)
            if gd is not None and gd[0].id in wanted:
                return True
            return any(rec.id in wanted for rec in untouched.get(pid, []))

        product_ids = {pid for pid in product_ids if _matches(pid)}

    leads = lead_times_for_pairs(
        db,
        [
            (pid, str(row.chosen_supplier_id))
            for pid, row in summary_rows.items()
            if pid in product_ids and pid not in grid_repr_for_product
            and row.chosen_supplier_id
        ],
    )

    touched: set[str] = set()
    confirmed = 0
    for pid in product_ids:
        # Clear the WHOLE stale line set first (e.g. a prior confirm under a
        # since-switched supplier, a re-decided qty, or a precedence flip between the
        # grid and the summary sheet), same shape as location grain.
        _remove_product_lines(db, pid)

        grid = grid_repr_for_product.get(pid)
        if grid is not None:
            rec, decision = grid
            qty = float(decision.buy_qty or 0)
            if qty <= 0:
                continue  # use_stock / use_po / skip / a non-buy mixture - nothing to draft
            supplier_id, unit_cost, lead_days = _decision_line_inputs(db, rec, decision)
            po = _draft_po_for_supplier(db, supplier_id, rec.currency)
            members = [r for r, _d in by_product[pid]]
            split = _grid_member_split(members, qty)
            members_by_wh = {str(r.warehouse_id): r for r in members}
            for wid, share_qty in split.items():
                if share_qty <= 0:
                    continue
                member_rec = members_by_wh.get(wid)
                if member_rec is None:
                    continue  # defensive - every split key comes from `members` itself
                _upsert_line(
                    db, po, product_id=member_rec.product_id,
                    warehouse_id=member_rec.warehouse_id, source_ref=member_rec.id,
                    qty=share_qty, unit_cost=unit_cost,
                    lead_days=lead_days, source_system=_SRC_PRODUCT,
                )
                touched.add(po.id)
            confirmed += 1
            continue

        members = untouched.get(pid)
        if members:
            # The engine's own suggestion, drafted the SAME way a decided product is: one
            # draft PO per chosen supplier, the quantity split back across the group's real
            # member warehouses so every line names one.
            qty = float(sum(float(m.rounded_qty or 0) for m in members))
            if qty <= 0:
                continue
            anchor = members[0]
            choice = _resolve_choice(db, anchor, None)
            po = _draft_po_for_supplier(db, choice["supplier_id"], anchor.currency)
            split = _grid_member_split(members, qty)
            members_by_wh = {str(m.warehouse_id): m for m in members}
            for wid, share_qty in split.items():
                if share_qty <= 0:
                    continue
                member_rec = members_by_wh.get(wid)
                if member_rec is None:
                    continue  # defensive - every split key comes from `members` itself
                _upsert_line(
                    db, po, product_id=member_rec.product_id,
                    warehouse_id=member_rec.warehouse_id, source_ref=member_rec.id,
                    qty=share_qty, unit_cost=choice["unit_cost"],
                    lead_days=choice["lead_time_days"], source_system=_SRC_PRODUCT,
                )
                touched.add(po.id)
            _record_confirmed_suggestion(db, members, qty, actor)
            confirmed += 1
            continue

        row = summary_rows[pid]  # ids narrowing guarantees this exists when grid is None
        qty = float(row.chosen_qty or 0)
        if qty <= 0:
            continue  # "use the pool" - nothing to draft
        allocations = (
            db.query(OrderSummaryLocationAllocation)
            .filter(OrderSummaryLocationAllocation.order_summary_row_id == row.id)
            .all()
        )
        if not allocations:
            continue  # no real location to name - nothing safe to draft (AC-F08 gap)
        key = (pid, str(row.chosen_supplier_id or ""))
        unit_cost = leads.get(("cost",) + key)
        lead_days = leads.get(key)
        currency = leads.get(("ccy",) + key)
        po = _draft_po_for_supplier(db, row.chosen_supplier_id, currency)
        for alloc in allocations:
            alloc_qty = float(alloc.allocated_qty or 0)
            if alloc_qty <= 0:
                continue
            _upsert_line(
                db, po, product_id=row.product_id, warehouse_id=alloc.warehouse_id,
                source_ref=f"{row.id}:{alloc.warehouse_id}", qty=alloc_qty,
                unit_cost=unit_cost, lead_days=lead_days, source_system=_SRC_PRODUCT,
            )
            touched.add(po.id)
        confirmed += 1

    db.flush()
    return {"confirmed_count": confirmed, "po_count": len(touched)}


def reset_run_decisions(db: Session, run_id: str, actor: Optional[str]) -> dict:
    """DEMO / ADMIN reset - return a run to its freshly-generated state so the
    accept / reject / adjust / confirm flow can be demonstrated again from scratch.

    For every buy rec on the run: pull its line out of any DRAFT PO (emptied drafts are
    deleted with it), drop its append-only override rows, and reset its status back to
    'proposed'. Only DRAFT (``draft_recommendation``) POs are touched - a confirmed
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
    # 1) Detach every rec's draft-PO line (deletes drafts that empty out). BOTH stamps:
    # a location-grain confirm keys its line by the rec id under `scm_recommendation`, and
    # a product-grain confirm keys ITS line by the same rec id under
    # `scm_order_summary_row` (`_confirm_product_grain`). Clearing only the first left
    # every product-grain draft line behind, so a reset run still read as Confirmed on the
    # plans list (`_product_counts` counts a product with a line in a draft PO) and the
    # pill on the row stayed Confirmed with it.
    for rec in recs:
        _remove_rec_line(db, rec.id)
        _remove_source_line(db, rec.id, _SRC_PRODUCT)
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
    """The (draft or now-active) PO a rec's line lives in - resolved via the line's
    ``source_ref`` (= rec id), which survives a confirm renumber.

    BOTH source systems, not just the location-grain one. `_confirm_product_grain` keys its
    lines by the SAME member recommendation id but stamps `scm_order_summary_row`, so a
    `_SRC`-only lookup answered "no PO" for every product-grain run - and the Decision pill,
    which reads Confirmed off exactly this field, stayed on Saved after a confirm that had
    plainly drafted the purchase order. Verified on the plan screen, 28 Aug 2026.
    """
    line = (
        db.query(PurchaseOrderLine)
        .options(joinedload(PurchaseOrderLine.purchase_order))
        .filter(
            PurchaseOrderLine.source_ref == rec_id,
            PurchaseOrderLine.source_system.in_((_SRC, _SRC_PRODUCT)),
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
# S16 - the row decision: buy / use stock / use PO / skip, or a mixture
# (captain, 21 Aug, 3rd time requested: "I want the decision made here").
#
# use_stock records the buyer's INTENTION only. It never writes a stock hold/reserve -
# that would collide with the project-sales ladder's own reservations against the same
# stock. The buy portion of a decision is the only part that ever reaches a PO, and only
# at Confirm decisions (`confirm_decisions`, above) - recording a decision here never
# drafts anything by itself, same staged-not-materialised doctrine as Accept/Adjust.
# ===========================================================================

#: Every value the `kind` field may carry. `mixture` is the captain's 4th option - more
#: than one of buy/stock/po at once - distinct from picking exactly one of the first
#: three; `skip` is deliberately doing nothing this round.
_PLAN_ROW_KINDS = {"buy", "use_stock", "use_po", "skip", "mixture"}

#: The price the row is costed at (AC-R13). `use_last` = what we last paid this supplier;
#: `ask_new` = the price is still a question, so the drafted line carries none rather than
#: a stale figure dressed up as a quote.
PRICE_MODE_USE_LAST = "use_last"
PRICE_MODE_ASK_NEW = "ask_new"
_PRICE_MODES = (PRICE_MODE_USE_LAST, PRICE_MODE_ASK_NEW)
DEFAULT_PRICE_MODE = PRICE_MODE_USE_LAST

#: Every rec_type this decision may be recorded on. Wider than `_get_buy_rec`'s buy-only
#: gate on purpose (S16 gap #2) - a needs_level or covered row the buyer overrides with
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
            message=f"A {kind} decision cannot also carry another part's quantity - use mixture.",
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
    *,
    price_mode: Optional[str] = None,
    supplier_code: Optional[str] = None,
    unit_cost: Optional[float] = None,
) -> dict:
    """Record (replacing, if one already exists) the buyer's decision on ONE row.

    Staged only - this never touches a purchase order. The buy portion reaches a draft
    PO line only once ``confirm_decisions`` runs, same doctrine as Accept/Adjust. Does
    NOT touch ``rec.status`` - that column stays the legacy accept/adjust/reject/covered
    vocabulary for whatever screen still reads it; this is a parallel, row-scoped record
    that ``confirm_decisions`` treats as authoritative for a rec the moment it exists
    (see that function's docstring).

    The PRICE and the SUPPLIER are the buyer's too (AC-R13 / AC-R14). `supplier_code`
    (never an id - no UUID crosses the wire, same as a stock take's warehouse code)
    switches the row onto another of the product's suppliers and RE-READS that supplier's
    last price and lead time off the recommendation's frozen candidates. `price_mode`
    decides whether the row is costed at all: `use_last` stores the price, `ask_new`
    stores none, and the drafted PO line follows."""
    rec = _get_decidable_rec(db, rec_id)
    _assert_not_legacy(db, str(rec.run_id))

    buy_qty_f = float(buy_qty or 0)
    resolved_takes = _resolve_stock_takes(db, stock_takes)
    stock_total = sum(t["qty"] for t in resolved_takes)
    po_qty_f = float(po_qty or 0)
    _validate_plan_row_decision(kind, buy_qty_f, stock_total, po_qty_f)

    mode = (price_mode or DEFAULT_PRICE_MODE).strip()
    if mode not in _PRICE_MODES:
        raise AppException(
            status_code=422,
            message="Price must be either the last price or a new one to ask for.",
        )
    if unit_cost is not None and float(unit_cost) < 0:
        raise AppException(status_code=422, message="A price cannot be negative.")
    choice = _resolve_choice(db, rec, supplier_code)
    if supplier_code and choice["supplier_id"] is None:
        raise AppException(status_code=422,
                           message="That supplier is not on file for this product.")
    # `ask_new` is the absence of a price, not a price of zero: the drafted line goes out
    # unpriced and the buyer fills it in when the quote comes back.
    resolved_cost = (
        None if mode == PRICE_MODE_ASK_NEW
        else (float(unit_cost) if unit_cost is not None else choice["unit_cost"])
    )

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
    existing.price_mode = mode
    # Only a buyer's OWN switch is stored. Left NULL, the rec's proposed supplier stands,
    # which is what `_resolve_choice(rec, None)` already answers everywhere else.
    existing.supplier_id = choice["supplier_id"] if supplier_code else None
    existing.unit_cost = resolved_cost
    existing.decided_by = actor
    existing.decided_at = datetime.utcnow()
    db.flush()
    return _plan_row_decision_dict(db, existing, _po_for_rec(db, rec.id))


def clear_plan_row_decision(db: Session, rec_id: str, actor: Optional[str]) -> dict:
    """Withdraw a row decision back to undecided. Idempotent - clearing an already-
    undecided row is a no-op. Also retracts any draft-PO line(s) a prior Confirm
    decisions raised off it immediately, rather than waiting for the next confirm to
    notice - on BOTH the location-grain line this rec's own id might key (``_SRC``)
    and the WHOLE product-grain line set this rec's PRODUCT might key
    (``_SRC_PRODUCT``, ``_confirm_product_grain`` - possibly more than one line, split
    across the group's real member warehouses, B2). A product-grain group's clear fans
    out one call per member (``usePlanLines.clear``, same shape as ``decide``), so
    every member is a valid place to notice the group's draft should go - removing it
    here is harmless even before every member has been cleared, since the next confirm
    reconciles against whichever members are still decided."""
    rec = _get_decidable_rec(db, rec_id)
    _assert_not_legacy(db, str(rec.run_id))
    deleted = (
        db.query(PlanRowDecision)
        .filter(PlanRowDecision.recommendation_id == rec.id)
        .delete(synchronize_session=False)
    )
    _remove_rec_line(db, rec.id)
    _remove_product_lines(db, str(rec.product_id))
    db.flush()
    return {"cleared": bool(deleted)}


def list_plan_row_decisions(db: Session, run_id: str) -> dict:
    """Every persisted row decision on a run, across every decidable rec_type, plus the
    counts the header ("N of Total made") counts against - computed off what is actually
    persisted, never off a client's own session state.

    **The counts are by DISTINCT PRODUCT (R14), the rows are per recommendation.** The
    plan decides one product at a time: a product-grain row is several recommendations
    underneath and the screen fans the SAME decision onto every one of them, so counting
    recommendations read a product held in three bins as three decisions out of three rows
    when the buyer had made one (plan fact F2 - `decided_count = len(data)`). The rows
    stay per recommendation because that is what each pill reads.
    """
    total = (
        db.query(ReorderRecommendation.product_id)
        .filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.rec_type.in_(_PLAN_ROW_DECIDABLE_TYPES),
        )
        .distinct()
        .count()
    )
    triples = (
        db.query(PlanRowDecision, ReorderRecommendation.id,
                 ReorderRecommendation.product_id)
        .join(ReorderRecommendation, ReorderRecommendation.id == PlanRowDecision.recommendation_id)
        .filter(ReorderRecommendation.run_id == run_id)
        .all()
    )
    data = [
        _plan_row_decision_dict(db, decision, _po_for_rec(db, rec_id))
        for decision, rec_id, _pid in triples
    ]
    decided = {str(pid) for _d, _rid, pid in triples}
    return {"data": data, "decided_count": len(decided), "total_count": total}


def carry_replan_decisions(db: Session, old_run_id: str, new_run_id: str) -> dict:
    """Re-plan (plan 5.1, G8): move each decided row from the OLD run to its matching row
    on the NEW run, when the suggestion is unchanged. Matched by
    (product_id, warehouse_id, rec_type) - NOT (product_id, warehouse_id) alone (review
    B1): a single location can hold more than one decidable rec_type in one run (a `buy`
    and a `needs_level` row measured side by side on real data), and product-grain runs
    can even carry two `buy` recs at the same key - either way a two-part key collapsed
    two distinct old decisions onto one new recommendation, and the second INSERT then hit
    `uq_scm_plan_row_decision_recommendation_id`.

    A product/location/type:
    - present in both runs with an UNCHANGED suggestion (same rec_type + same order qty):
      the decision is COPIED onto the new recommendation as a fresh `PlanRowDecision` row -
      the old one is untouched, runs stay immutable.
    - present in both but the suggestion CHANGED: arrives undecided, flagged
      `needs_recheck` in the new rec's frozen `inputs` (AC-5.3's "visible flag" - `inputs`
      already carries display extras alongside the frozen engine facts, so this needs no
      new column).
    - present only in the OLD run (left scope): not carried - there is no new rec to
      attach the decision to, so this is a silent drop rather than a code path of its own.
    - present only in the NEW run (entered scope): arrives undecided already, by default.

    Only OLD rows that carry an actual decision are examined - an undecided old row has
    nothing to carry and nothing to flag.

    Two more guards (review B1/S2), because the match key can still collide (a genuine
    duplicate pair on either side, or the buyer deciding the new row directly in the race
    window between this run completing and this carry running):
    - a target rec that ALREADY carries a decision - the buyer's own, or an earlier pair
      in this same batch - is left alone. A carried decision must never overwrite a real
      one.
    - each insert runs in its own SAVEPOINT, so a pair that still collides (the unique
      constraint is the backstop, not just the guard above) is skipped rather than
      aborting every decision after it in the batch.
    """
    old_rows = (
        db.query(
            ReorderRecommendation.product_id,
            ReorderRecommendation.warehouse_id,
            ReorderRecommendation.rec_type,
            ReorderRecommendation.rounded_qty,
            PlanRowDecision,
        )
        .join(PlanRowDecision, PlanRowDecision.recommendation_id == ReorderRecommendation.id)
        .filter(
            ReorderRecommendation.run_id == old_run_id,
            ReorderRecommendation.rec_type.in_(_PLAN_ROW_DECIDABLE_TYPES),
        )
        .all()
    )
    if not old_rows:
        return {"carried": 0, "recheck": 0, "dropped": 0, "skipped": 0}

    new_recs = (
        db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == new_run_id,
            ReorderRecommendation.rec_type.in_(_PLAN_ROW_DECIDABLE_TYPES),
        )
        .all()
    )
    new_by_key: dict[tuple[str, Optional[str], str], ReorderRecommendation] = {
        (str(r.product_id), str(r.warehouse_id) if r.warehouse_id else None, r.rec_type): r
        for r in new_recs
    }
    # New recs that already carry a decision (the buyer's own, made after this run
    # completed but before this carry ran) - never overwritten.
    already_decided: set[str] = {
        str(rec_id) for (rec_id,) in
        db.query(PlanRowDecision.recommendation_id)
        .join(ReorderRecommendation, ReorderRecommendation.id == PlanRowDecision.recommendation_id)
        .filter(ReorderRecommendation.run_id == new_run_id)
        .all()
    }

    carried = recheck = dropped = skipped = 0
    now = datetime.utcnow()
    for product_id, warehouse_id, rec_type, rounded_qty, old_decision in old_rows:
        key = (str(product_id), str(warehouse_id) if warehouse_id else None, rec_type)
        new_rec = new_by_key.get(key)
        if new_rec is None:
            dropped += 1
            continue
        unchanged = _qty_eq(new_rec.rounded_qty, rounded_qty)
        if not unchanged:
            recheck += 1
            new_rec.inputs = {**(new_rec.inputs or {}), "needs_recheck": True}
            db.add(new_rec)
            continue
        if str(new_rec.id) in already_decided:
            skipped += 1
            continue
        sp = db.begin_nested()
        try:
            db.add(PlanRowDecision(
                id=str(uuid.uuid4()),
                recommendation_id=new_rec.id,
                kind=old_decision.kind,
                buy_qty=old_decision.buy_qty,
                stock_takes=old_decision.stock_takes,
                po_qty=old_decision.po_qty,
                po_refs=old_decision.po_refs,
                reason_text=old_decision.reason_text,
                price_mode=old_decision.price_mode,
                supplier_id=old_decision.supplier_id,
                unit_cost=old_decision.unit_cost,
                decided_by=old_decision.decided_by,
                decided_at=now,
            ))
            db.flush()
        except Exception:  # noqa: BLE001 - a colliding pair must not lose the rest
            sp.rollback()
            skipped += 1
            log.exception(
                "carry_replan_decisions: could not carry a decision onto rec %s (product %s)",
                new_rec.id, product_id,
            )
            continue
        sp.commit()
        already_decided.add(str(new_rec.id))
        carried += 1

    # S3 (#491, merging around the same time as this PR) denormalises planned/decided/
    # confirmed counts onto scm.reorder_run, kept current by _refresh_run_counts on every
    # decision write - this function inserts PlanRowDecision rows directly, bypassing that,
    # so a re-planned run carrying N carried decisions would show decided_count = 0 on the
    # plans list until someone touched a row by hand. Guarded (module-attribute check, not
    # an import) so this branch stays green BOTH before and after #491 merges: the name
    # only exists in this module once that PR lands.
    refresh_counts = globals().get("_refresh_run_counts")
    if refresh_counts is not None:
        refresh_counts(db, new_run_id)

    return {"carried": carried, "recheck": recheck, "dropped": dropped, "skipped": skipped}


def has_confirmed_or_keyed_decisions(db: Session, run_id: str) -> bool:
    """S4 ruling (conservative, flagged for captain confirm - see the PLAN doc's S5
    section): whether ANY product/location on this run has already been confirmed into a
    draft purchase order, or keyed into AutoCount - the two states a re-plan would corrupt.

    Location grain: a decided rec whose `keyed_status` moved off `not_keyed`, or a draft
    (or since-confirmed) `purchase_order_lines` row still pointing at one of this run's
    rec ids (`confirm_decisions`'s own `_SRC` stamp).

    Product grain: an `OrderSummaryRow` with `chosen_qty` set (confirmed) or a
    `keyed_status` off `not_keyed`.

    A re-plan would hand `confirm_decisions` a run whose recs/rows carry NEW ids, so its
    source_ref-keyed reconciliation orphans the existing draft line instead of updating it,
    and a re-key off the new plan risks double-keying the same purchase into AutoCount.
    """
    rec_ids = [
        str(r.id) for r in
        db.query(ReorderRecommendation.id).filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.rec_type.in_(_PLAN_ROW_DECIDABLE_TYPES),
        ).all()
    ]
    if rec_ids:
        keyed = (
            db.query(ReorderRecommendation.id)
            .filter(ReorderRecommendation.id.in_(rec_ids),
                    ReorderRecommendation.keyed_status != "not_keyed")
            .first()
        )
        if keyed is not None:
            return True
        confirmed_loc = (
            db.query(PurchaseOrderLine.id)
            .filter(PurchaseOrderLine.source_system == _SRC,
                    PurchaseOrderLine.source_ref.in_(rec_ids))
            .first()
        )
        if confirmed_loc is not None:
            return True

    from app.models.scm import OrderSummaryRow
    osr_confirmed = (
        db.query(OrderSummaryRow.id)
        .filter(
            OrderSummaryRow.run_id == run_id,
            (OrderSummaryRow.chosen_qty.isnot(None))
            | (OrderSummaryRow.keyed_status != "not_keyed"),
        )
        .first()
    )
    return osr_confirmed is not None


def _qty_eq(a, b) -> bool:
    """Decimal-safe equality for two possibly-None recommendation quantities."""
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < 1e-6


def _plan_row_decision_dict(
    db: Session, decision: PlanRowDecision, po: Optional[PurchaseOrder]
) -> dict:
    supplier = (
        db.query(Supplier).filter(Supplier.id == decision.supplier_id).first()
        if decision.supplier_id else None
    )
    lead = None
    if supplier is not None:
        ps = _product_supplier_choice(
            db, decision.recommendation.product_id, decision.supplier_id
        ) or {}
        lead = ps.get("lead_time_days")
        if lead is None:
            # The frozen candidate the UI offered carries the lead time when
            # `product_suppliers` has none of its own.
            inp = (decision.recommendation.inputs or {})
            for cand in [inp.get("supplier") or {}] + list(inp.get("alternatives") or []):
                if cand and cand.get("supplier_code") == supplier.supplier_code:
                    lead = cand.get("lead_time_days")
                    break
    return {
        "recommendation_id": decision.recommendation_id,
        "kind": decision.kind,
        "buy_qty": _f(decision.buy_qty),
        "stock_takes": decision.stock_takes or [],
        "po_qty": _f(decision.po_qty),
        "po_refs": decision.po_refs or [],
        "reason_text": decision.reason_text,
        # The buyer's price + supplier calls (AC-R13 / AC-R14). No UUID on the wire: the
        # supplier travels as its code, the way a stock take travels as a warehouse code.
        "price_mode": decision.price_mode or DEFAULT_PRICE_MODE,
        "supplier_code": supplier.supplier_code if supplier else None,
        "supplier_name": supplier.supplier_name if supplier else None,
        "unit_cost": _f(decision.unit_cost),
        "lead_time_days": _f(lead),
        "draft_po_number": po.po_number if po else None,
        "draft_po_id": po.id if po else None,
    }


def _decision_line_inputs(
    db: Session, rec: ReorderRecommendation, decision: PlanRowDecision
) -> tuple[Optional[str], Optional[float], Optional[float]]:
    """`(supplier_id, unit_cost, lead_days)` a decided row's draft-PO line is raised with.

    The buyer's supplier wins over the engine's; `ask_new` leaves the line unpriced so the
    quote that comes back is what fills it, never a figure the plan invented."""
    code = _supplier_code_for_id(db, decision.supplier_id)
    choice = _resolve_choice(db, rec, code)
    if (decision.price_mode or DEFAULT_PRICE_MODE) == PRICE_MODE_ASK_NEW:
        return choice["supplier_id"], None, choice["lead_time_days"]
    cost = _f(decision.unit_cost) if decision.unit_cost is not None else choice["unit_cost"]
    return choice["supplier_id"], cost, choice["lead_time_days"]
