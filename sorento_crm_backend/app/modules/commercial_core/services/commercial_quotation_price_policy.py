"""Quotation pricing: tolerance vs product list_price, valid_until, approval routing."""
from __future__ import annotations

import copy
import html
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy.orm import Session

from app.modules.commercial_core.models import CommercialMasterQuotation, CommercialProject, CommercialQuotationRevision, CommercialTender
from app.modules.commercial_core.models_process_config import CommercialProcessSettings
from app.models.workflow_stage import WORKFLOW_DOMAIN_QUOTATION, WorkflowStage
from app.modules.commercial_core.services.commercial_hierarchy_service import ToleranceAdvanceConfirmationRequired
from app.models.product import Product


def _dec(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def snapshot_order_items(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = snap.get("order_items") if isinstance(snap, dict) else None
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def snapshot_quotation_meta(snap: Dict[str, Any]) -> Dict[str, Any]:
    meta = snap.get("quotation_meta") if isinstance(snap, dict) else None
    return dict(meta) if isinstance(meta, dict) else {}


def _snapshot_num(v: Any) -> float:
    """Mirror JS Number(x) used in quotation-revisions lineNetAmount (empty → 0)."""
    if v is None:
        return 0.0
    if isinstance(v, str) and not v.strip():
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute_snapshot_line_net(line: Dict[str, Any]) -> Decimal:
    """Net line amount after pct-then-amt discounts (matches frontend quotation-revisions/page.tsx)."""
    q_raw = line.get("qty") if line.get("qty") is not None else line.get("quantity")
    if q_raw is None:
        q_raw = "1"
    q = _snapshot_num(q_raw)
    up = _snapshot_num(line.get("unit_price"))
    line_amt = q * up
    dp_raw = line.get("discount_pct")
    if dp_raw is None or dp_raw == "":
        dp_raw = line.get("discount_percent")
    dp = _snapshot_num(dp_raw)
    if dp > 0:
        line_amt *= 1.0 - dp / 100.0
    da_raw = line.get("discount_amt")
    if da_raw is None or da_raw == "":
        da_raw = line.get("discount_amount")
    da = _snapshot_num(da_raw)
    if da > 0:
        line_amt -= da
    if line_amt < 0:
        line_amt = 0.0
    return Decimal(str(line_amt)).quantize(Decimal("0.01"))


def compute_snapshot_subtotal(snap: Dict[str, Any]) -> Decimal:
    total = Decimal("0")
    for line in snapshot_order_items(snap):
        total += compute_snapshot_line_net(line)
    return total.quantize(Decimal("0.01"))


def tolerance_band(
    list_price: Decimal,
    tol_type: Optional[str],
    tol_val: Optional[Decimal],
) -> Tuple[Decimal, Decimal]:
    if not tol_type or tol_val is None or tol_val < 0:
        return list_price, list_price
    if tol_type == "percent":
        delta = (list_price * (tol_val / Decimal("100"))).quantize(Decimal("0.01"))
        return list_price - delta, list_price + delta
    if tol_type == "amount":
        return list_price - tol_val, list_price + tol_val
    return list_price, list_price


def line_within_tolerance(
    unit_price: Decimal,
    list_price: Decimal,
    tol_type: Optional[str],
    tol_val: Optional[Decimal],
) -> bool:
    lo, hi = tolerance_band(list_price, tol_type, tol_val)
    return lo <= unit_price <= hi


def pricing_line_hints_for_snapshot(db: Session, snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per order line: unit cost, list/tolerance band, whether unit price breaches product tolerance (for UI)."""
    hints: List[Dict[str, Any]] = []
    for i, line in enumerate(snapshot_order_items(snap)):
        pid = line.get("product_id")
        unit = _dec(line.get("unit_price"))
        base: Dict[str, Any] = {
            "line_index": i,
            "product_id": None,
            "unit_cost": None,
            "list_price": None,
            "sales_tolerance_type": None,
            "sales_tolerance_value": None,
            "min_unit_price": None,
            "max_unit_price": None,
            "unit_price_out_of_tolerance": False,
        }
        if not pid:
            hints.append(base)
            continue
        prod = db.query(Product).filter(Product.id == str(pid)).first()
        if not prod:
            hints.append(base)
            continue
        lp = prod.list_price if prod.list_price is not None else Decimal("0")
        lo, hi = tolerance_band(lp, prod.sales_tolerance_type, prod.sales_tolerance_value)
        loq = lo.quantize(Decimal("0.01"))
        hiq = hi.quantize(Decimal("0.01"))
        uc = prod.cost_price
        tol_t = prod.sales_tolerance_type
        tol_v = prod.sales_tolerance_value
        out = False
        if unit is not None and tol_t and tol_v is not None:
            out = not line_within_tolerance(unit, lp, tol_t, tol_v)
        hints.append(
            {
                "line_index": i,
                "product_id": str(pid),
                "unit_cost": str(uc.quantize(Decimal("0.01"))) if uc is not None else None,
                "list_price": str(lp.quantize(Decimal("0.01"))),
                "sales_tolerance_type": tol_t,
                "sales_tolerance_value": str(tol_v) if tol_v is not None else None,
                "min_unit_price": str(loq),
                "max_unit_price": str(hiq),
                "unit_price_out_of_tolerance": out,
            }
        )
    return hints


def collect_tolerance_breaches(db: Session, snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    breaches: List[Dict[str, Any]] = []
    for i, line in enumerate(snapshot_order_items(snap)):
        pid = line.get("product_id")
        if not pid:
            continue
        unit = _dec(line.get("unit_price"))
        prod = db.query(Product).filter(Product.id == str(pid)).first()
        if not prod or unit is None:
            continue
        lp = prod.list_price if prod.list_price is not None else Decimal("0")
        if prod.sales_tolerance_type and prod.sales_tolerance_value is not None:
            if not line_within_tolerance(unit, lp, prod.sales_tolerance_type, prod.sales_tolerance_value):
                breaches.append(
                    {
                        "line_index": i,
                        "product_id": str(pid),
                        "product_code": prod.product_code,
                        "unit_price": str(unit),
                        "list_price": str(lp),
                        "tolerance_type": prod.sales_tolerance_type,
                        "tolerance_value": str(prod.sales_tolerance_value),
                    }
                )
    return breaches


def ordered_active_quotation_stages(db: Session) -> List[WorkflowStage]:
    return (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
            WorkflowStage.is_active.is_(True),
        )
        .order_by(WorkflowStage.sort_order.asc(), WorkflowStage.code.asc())
        .all()
    )


def default_pricing_approval_terminal_stage_code(db: Session, controls: Dict[str, Any]) -> str:
    explicit = str(controls.get("mq_pricing_approval_terminal_stage_code") or "").strip()
    if explicit:
        return explicit
    row = (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
            WorkflowStage.is_active.is_(True),
            WorkflowStage.is_terminal.is_(True),
        )
        .order_by(WorkflowStage.sort_order.asc(), WorkflowStage.code.asc())
        .first()
    )
    if row:
        return cast(str, row.code)
    return "selected"


def get_process_pricing_controls(db: Session) -> Dict[str, Any]:
    row = db.query(CommercialProcessSettings).filter(CommercialProcessSettings.id == "default").first()
    if not row or row.pricing_controls is None:
        return {}
    return dict(row.pricing_controls) if isinstance(row.pricing_controls, dict) else {}


def compute_valid_until_from_snapshot(snap: Dict[str, Any]) -> Optional[date]:
    meta = snapshot_quotation_meta(snap)
    issued = meta.get("issued_on") or meta.get("issue_date")
    if isinstance(issued, str) and issued.strip():
        try:
            base = date.fromisoformat(issued.strip()[:10])
        except ValueError:
            base = date.today()
    else:
        base = date.today()
    days_tpl = meta.get("quotation_validity_days")
    override = meta.get("validity_days_override")
    try:
        d_tpl = int(days_tpl) if days_tpl is not None else 0
    except (TypeError, ValueError):
        d_tpl = 0
    try:
        d_ov = int(override) if override is not None else None
    except (TypeError, ValueError):
        d_ov = None
    eff = d_ov if d_ov is not None and d_ov > 0 else d_tpl
    if eff <= 0:
        return None
    return base + timedelta(days=eff)


def normalize_project_owner_ids(owner_user_id: str, owner_ids: Any) -> List[str]:
    """Return unique project owner user ids, ensuring legacy owner_user_id is included."""
    ids: List[str] = []
    if isinstance(owner_ids, list):
        for x in owner_ids:
            if x is not None and str(x).strip():
                ids.append(str(x).strip())
    ou = (owner_user_id or "").strip()
    if ou and ou not in ids:
        ids.insert(0, ou)
    seen: set[str] = set()
    out: List[str] = []
    for u in ids:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def user_may_access_project_quotations(db: Session, project_id: str, user_id: str) -> bool:
    p = db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
    if not p:
        return False
    owners = normalize_project_owner_ids(p.owner_user_id, p.project_owner_user_ids)
    return (user_id or "").strip() in owners


def other_terminal_master_quotation_same_project(
    db: Session, project_id: str, exclude_master_id: str
) -> Optional[CommercialMasterQuotation]:
    return (
        db.query(CommercialMasterQuotation)
        .join(CommercialTender, CommercialTender.id == CommercialMasterQuotation.tender_id)
        .join(
            WorkflowStage,
            WorkflowStage.id == CommercialMasterQuotation.quotation_stage_id,
        )
        .filter(
            CommercialTender.project_id == project_id,
            CommercialMasterQuotation.id != exclude_master_id,
            WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
            WorkflowStage.is_terminal.is_(True),
        )
        .first()
    )


def sync_master_from_working_revision(db: Session, mq: CommercialMasterQuotation) -> None:
    wid = mq.current_working_revision_id
    if not wid:
        return
    rev = db.query(CommercialQuotationRevision).filter(CommercialQuotationRevision.id == wid).first()
    if not rev:
        return
    snap = dict(rev.pricing_snapshot or {})
    mq.valid_until = compute_valid_until_from_snapshot(snap)
    meta = snapshot_quotation_meta(snap)
    appr = meta.get("pricing_approver_user_id") or meta.get("approver_user_id")
    if appr:
        mq.pricing_approver_user_id = str(appr).strip() or None
    mq.quoted_amount = compute_snapshot_subtotal(snap)
    if not mq.quoted_currency:
        mq.quoted_currency = "MYR"


def _emit_mq_stage_system_message_if_changed(
    db: Session,
    mq: CommercialMasterQuotation,
    prev_stage_id: str,
    applied_stage_code: str,
    actor_user_id: Optional[str] = None,
) -> None:
    cur = str(mq.quotation_stage_id) if mq.quotation_stage_id else ""
    if cur == (prev_stage_id or ""):
        return
    from app.models.order import Customer
    from app.models.user import User
    from app.modules.commercial_core.services.entity_conversation_service import ENTITY_MASTER_QUOTATION, ENTITY_PROJECT, append_system_message

    st_row = db.query(WorkflowStage).filter(WorkflowStage.id == mq.quotation_stage_id).first()
    label = (st_row.label or "").strip() if st_row else applied_stage_code
    qcode = (mq.quotation_code or "").strip() or str(mq.id)

    actor_name = ""
    if actor_user_id:
        actor = db.query(User).filter(User.id == actor_user_id).first()
        if actor:
            actor_name = (actor.name or "").strip() or actor.email or ""

    cust = db.query(Customer).filter(Customer.id == mq.customer_id).first() if mq.customer_id else None
    client_name = (cust.customer_name or "").strip() if cust else ""
    details = mq.commercial_details if isinstance(mq.commercial_details, dict) else {}
    pic_name = (details.get("customer_pic_name") or "").strip() if isinstance(details.get("customer_pic_name"), str) else ""

    by_part = f" by {html.escape(actor_name)}" if actor_name else ""
    append_system_message(
        db,
        entity_type=ENTITY_MASTER_QUOTATION,
        entity_id=str(mq.id),
        body_html=f"<p>{html.escape(qcode)} moved to {html.escape(label)}{by_part}.</p>",
    )
    if mq.tender and mq.tender.project_id:
        bits = [f"Quotation {html.escape(qcode)} moved to {html.escape(label)}"]
        if actor_name:
            bits.append(f"by {html.escape(actor_name)}")
        if client_name:
            bits.append(f"for {html.escape(client_name)}")
        if pic_name:
            bits.append(f"(PIC: {html.escape(pic_name)})")
        append_system_message(
            db,
            entity_type=ENTITY_PROJECT,
            entity_id=str(mq.tender.project_id),
            body_html=f"<p>{' '.join(bits)}.</p>",
        )


def apply_master_quotation_stage_change(
    db: Session,
    mq: CommercialMasterQuotation,
    execution_state: str,
    actor_user_id: str,
    *,
    confirm_tolerance_breach: bool = False,
) -> Dict[str, Any]:
    """
    Apply MQ stage transition with tolerance + single-terminal + membership rules.
    Returns { applied_stage_code, rerouted_for_approval }.
    """
    prev_qsid = str(mq.quotation_stage_id) if mq.quotation_stage_id else ""
    t = mq.tender
    if not t:
        raise ValueError("Tender not loaded for master quotation.")
    project_id = str(t.project_id)
    if not user_may_access_project_quotations(db, project_id, actor_user_id):
        raise ValueError("Only project owners may change quotation execution stage.")

    ap_st = (mq.pricing_approval_status or "").strip().lower()
    if ap_st == "pending":
        raise ValueError("This quotation is awaiting pricing approval and cannot change stage.")

    st = (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
            WorkflowStage.code == execution_state,
            WorkflowStage.is_active.is_(True),
        )
        .first()
    )
    if not st:
        raise ValueError("Quotation stage not found.")

    wid = mq.current_working_revision_id
    if not wid:
        if st.is_terminal:
            raise ValueError("Set a current working revision before moving to a terminal stage.")
        details = copy.deepcopy(dict(mq.commercial_details or {}))
        details.pop("pricing_intended_execution_state", None)
        mq.commercial_details = details
        mq.quotation_stage_id = st.id
        mq.stage_updated_at = datetime.utcnow()
        _emit_mq_stage_system_message_if_changed(db, mq, prev_qsid, execution_state, actor_user_id)
        return {"applied_stage_code": execution_state, "rerouted_for_approval": False}
    rev = db.query(CommercialQuotationRevision).filter(CommercialQuotationRevision.id == wid).first()
    if not rev:
        raise ValueError("Working revision not found.")

    snap = dict(rev.pricing_snapshot or {})
    breaches = collect_tolerance_breaches(db, snap)
    controls = get_process_pricing_controls(db)
    pending_code = (controls.get("mq_pending_approval_stage_code") or "review").strip()

    stages = ordered_active_quotation_stages(db)
    cur_idx = next((i for i, s in enumerate(stages) if str(s.id) == str(mq.quotation_stage_id)), -1)
    tgt_idx = next((i for i, s in enumerate(stages) if str(s.id) == str(st.id)), -1)
    forward_one = cur_idx >= 0 and tgt_idx >= 0 and tgt_idx == cur_idx + 1

    if (
        breaches
        and cur_idx >= 1
        and forward_one
        and not st.is_terminal
    ):
        if not confirm_tolerance_breach:
            raise ToleranceAdvanceConfirmationRequired(breaches)
        pst = (
            db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
                WorkflowStage.code == pending_code,
                WorkflowStage.is_active.is_(True),
            )
            .first()
        )
        if not pst:
            raise ValueError(
                f"Tolerance breach: configure a valid mq_pending_approval_stage_code (missing {pending_code!r})."
            )
        intended_terminal = default_pricing_approval_terminal_stage_code(db, controls)
        details = copy.deepcopy(dict(mq.commercial_details or {}))
        details["pricing_intended_execution_state"] = intended_terminal
        mq.commercial_details = details
        mq.quotation_stage_id = pst.id
        mq.pricing_approval_status = "pending"
        mq.stage_updated_at = datetime.utcnow()
        _emit_mq_stage_system_message_if_changed(db, mq, prev_qsid, pending_code, actor_user_id)
        return {"applied_stage_code": pending_code, "rerouted_for_approval": True}

    if st.is_terminal and breaches:
        pst = (
            db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
                WorkflowStage.code == pending_code,
                WorkflowStage.is_active.is_(True),
            )
            .first()
        )
        if not pst:
            raise ValueError(
                f"Tolerance breach: configure a valid mq_pending_approval_stage_code (missing {pending_code!r})."
            )
        details = copy.deepcopy(dict(mq.commercial_details or {}))
        details["pricing_intended_execution_state"] = execution_state
        mq.commercial_details = details
        mq.quotation_stage_id = pst.id
        mq.pricing_approval_status = "pending"
        mq.stage_updated_at = datetime.utcnow()
        _emit_mq_stage_system_message_if_changed(db, mq, prev_qsid, pending_code, actor_user_id)
        return {"applied_stage_code": pending_code, "rerouted_for_approval": True}

    if st.is_terminal:
        other = other_terminal_master_quotation_same_project(db, project_id, str(mq.id))
        if other:
            raise ValueError(
                "Another quotation for this project is already in a terminal stage; "
                "only one terminal quotation is allowed per project."
            )

    details = copy.deepcopy(dict(mq.commercial_details or {}))
    details.pop("pricing_intended_execution_state", None)
    mq.commercial_details = details
    mq.quotation_stage_id = st.id
    mq.stage_updated_at = datetime.utcnow()
    if not breaches:
        mq.pricing_approval_status = "clear"
    mq.pricing_approval_action_at = None
    mq.pricing_approval_action_by_user_id = None
    _emit_mq_stage_system_message_if_changed(db, mq, prev_qsid, execution_state)
    return {"applied_stage_code": execution_state, "rerouted_for_approval": False}


def complete_pricing_approval(
    db: Session,
    mq: CommercialMasterQuotation,
    *,
    actor_user_id: str,
    approved: bool,
    notes: Optional[str] = None,
) -> None:
    approver_id = (mq.pricing_approver_user_id or "").strip()
    if approver_id and approver_id != (actor_user_id or "").strip():
        raise ValueError("Only the configured pricing approver may complete this action.")
    details = copy.deepcopy(dict(mq.commercial_details or {}))
    intended = details.pop("pricing_intended_execution_state", None)
    mq.commercial_details = details
    mq.pricing_approval_action_at = datetime.utcnow()
    mq.pricing_approval_action_by_user_id = actor_user_id
    if not approved:
        mq.pricing_approval_status = "rejected"
        return
    if not intended:
        mq.pricing_approval_status = "clear"
        return
    st = (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
            WorkflowStage.code == str(intended),
            WorkflowStage.is_active.is_(True),
        )
        .first()
    )
    if not st:
        mq.pricing_approval_status = "clear"
        return
    t = mq.tender
    project_id = str(t.project_id) if t else ""
    if project_id:
        other = other_terminal_master_quotation_same_project(db, project_id, str(mq.id))
        if other:
            raise ValueError(
                "Another quotation for this project is already in a terminal stage; "
                "only one terminal quotation is allowed per project."
            )
    mq.quotation_stage_id = st.id
    mq.stage_updated_at = datetime.utcnow()
    mq.pricing_approval_status = "clear"
    _ = notes
