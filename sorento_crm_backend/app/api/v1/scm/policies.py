"""SCM Policy Configuration endpoints — tune the reorder engine's policies from the app.

Three policy families + a resolution preview, all under ``/api/v1/scm/policies`` behind
the package's ``require_module_enabled_with_api_key("scm")`` guard. Read AND write are
both gated ``scm.policy.manage`` (AC-CFG-3): this is an admin/config surface, not a
dashboard view — the people who read it are the people allowed to change it.

Static sub-paths (``/classification``, ``/supplier-scoring``, ``/resolve``) are declared
BEFORE the parametric ``/{policy_id}`` routes so ``classification`` is never captured as
an id (route-shadowing gotcha).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_policy import (
    AbcXyzPolicy,
    AbcXyzWrite,
    ReorderPolicyPage,
    ReorderPolicyRow,
    ReorderPolicyWrite,
    ResolutionResult,
    SupplierScoringPolicy,
    SupplierScoringWrite,
)
from app.services.scm import policy_service as svc

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


# --- resolution preview -----------------------------------------------------

@router.get("/policies/resolve", response_model=ResolutionResult)
def resolve_policy(
    product_id: str = Query(...),
    warehouse_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Preview which policy a SKU resolves to (winner + full precedence chain).
    Produced by the SAME ``resolve_policy_for_sku`` the reorder run uses — never a
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
