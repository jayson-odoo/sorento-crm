"""SCM Policy Configuration endpoints - tune the reorder engine's policies from the app.

Three policy families + a resolution preview, all under ``/api/v1/scm/policies`` behind
the package's ``require_module_enabled_with_api_key("scm")`` guard. Read AND write are
both gated ``scm.policy.manage`` (AC-CFG-3): this is an admin/config surface, not a
dashboard view - the people who read it are the people allowed to change it.

Static sub-paths (``/classification``, ``/supplier-scoring``, ``/resolve``) are declared
BEFORE the parametric ``/{policy_id}`` routes so ``classification`` is never captured as
an id (route-shadowing gotcha).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_policy import (
    AbcXyzPolicy,
    AbcXyzWrite,
    FulfilmentPriorityPolicy,
    FulfilmentPriorityWrite,
    ReorderPolicyPage,
    ReorderPolicyRow,
    ReorderPolicyWrite,
    ResolutionResult,
    SupplierScoringPolicy,
    SupplierScoringWrite,
)
from app.services.error_handler import AppException
from app.services.scm import policy_service as svc
from app.services.scm import priority as priority_svc

router = APIRouter()

_MANAGE = require_permission_with_api_key("scm.policy.manage")


# --- classification thresholds (single global row) --------------------------

@router.get("/policies/classification", response_model=AbcXyzPolicy)
def get_classification(
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return svc.get_classification(db)


@router.put("/policies/classification", response_model=AbcXyzPolicy)
def put_classification(
    body: AbcXyzWrite,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return svc.put_classification(db, body)


# --- supplier scoring (single global row) -----------------------------------

@router.get("/policies/supplier-scoring", response_model=SupplierScoringPolicy)
def get_supplier_scoring(
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return svc.get_supplier_scoring(db)


@router.put("/policies/supplier-scoring", response_model=SupplierScoringPolicy)
def put_supplier_scoring(
    body: SupplierScoringWrite,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return svc.put_supplier_scoring(db, body)


# --- fulfilment priority (single active `scm.priority_policy` row) ----------
#
# PLAN-demo-followups-19aug-ladder-v2.md C1/C2. Declared here, before the parametric
# `/policies/{policy_id}` routes below, for the same route-shadowing reason `classification`
# and `supplier-scoring` are - "fulfilment-priority" must never be swallowed as a policy id.

@router.get("/policies/fulfilment-priority", response_model=FulfilmentPriorityPolicy)
def get_fulfilment_priority(
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return priority_svc.fulfilment_priority_as_dict(priority_svc.active_policy(db))


@router.put("/policies/fulfilment-priority", response_model=FulfilmentPriorityPolicy)
def put_fulfilment_priority(
    body: FulfilmentPriorityWrite,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Writes a NEW policy revision and activates it - never mutates an old row (see
    `priority.create_revision`), so switching back is "activate the previous revision",
    not "undo an edit"."""
    current = priority_svc.active_policy(db)
    # The TBA freshness rule, and it applies to a CHANGE only (fixed 30 Aug, review of S2).
    # A date in the past turns every open order into a placeholder - every line dated on or
    # after it stops taking supply - so moving the line back is refused. But once a
    # configured date has quietly passed, an UNCHANGED resubmission of it is not that move,
    # and refusing it locked the whole panel: no weight, no coverage date and no class
    # weight could be saved again until somebody also picked a new TBA date. The schema
    # cannot make this call - it needs the active revision - so it is made here.
    if (
        body.tba_date_from is not None
        and body.tba_date_from < date.today()
        and (current is None or current.tba_date_from != body.tba_date_from)
    ):
        raise AppException(
            status_code=422,
            message="TBA date from must be today or later.",
            code="tba_date_from_in_the_past",
        )
    revision = priority_svc.create_revision(
        db,
        name=current.name if current is not None else priority_svc.FAIR_POLICY_NAME,
        factors=body.factors,
        demand_class_weights=body.demand_class_weights,
        reorder_coverage_until=body.reorder_coverage_until,
        # An omitted `tba_date_from` keeps the date the active revision already carries -
        # the same "the body did not say, so nothing changes" the name and notes above get.
        # The column is NOT NULL, so `create_revision` supplies the default only when there
        # is no active revision to copy from.
        tba_date_from=(
            body.tba_date_from
            if body.tba_date_from is not None
            else (current.tba_date_from if current is not None else None)
        ),
        notes=current.notes if current is not None else None,
    )
    db.commit()
    return priority_svc.fulfilment_priority_as_dict(revision)


# --- resolution preview -----------------------------------------------------

@router.get("/policies/resolve", response_model=ResolutionResult)
def resolve_policy(
    product_id: str = Query(...),
    warehouse_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Preview which policy a SKU resolves to (winner + full precedence chain).
    Produced by the SAME ``resolve_policy_for_sku`` the reorder run uses - never a
    reimplementation (AC-PREV-2). ``warehouse_id`` accepts a warehouse_code."""
    return svc.resolve(db, product_id, warehouse_id)


# --- reorder policy CRUD ----------------------------------------------------

@router.get("/policies", response_model=ReorderPolicyPage)
def list_policies(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=1000),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc"),
    query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return svc.list_policies(db, page=page, limit=limit, sort=sort,
                             direction=dir, query=query)


@router.post("/policies", response_model=ReorderPolicyRow, status_code=201)
def create_policy(
    body: ReorderPolicyWrite,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return svc.create_policy(db, body)


@router.put("/policies/{policy_id}", response_model=ReorderPolicyRow)
def update_policy(
    policy_id: str,
    body: ReorderPolicyWrite,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return svc.update_policy(db, policy_id, body)


@router.delete("/policies/{policy_id}", status_code=204)
def delete_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    svc.delete_policy(db, policy_id)
    return Response(status_code=204)
