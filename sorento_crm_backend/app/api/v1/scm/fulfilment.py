"""Fulfilment: the supplier's stock list, and the container plan built from it.

Ms Tee's half of the module. Planning decides WHAT to buy; this decides what physically goes
on the next container and what the supplier is asked to finish.

Two-step upload for the same reason as every other channel here: the stock list REPLACES what
we hold for that supplier, so nothing is written from a single click, and `?validate_only=true`
returns the same `{valid, errors, warnings, summary}` verdict a Test means everywhere else in
this system.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.scm import ContainerSize, LoadingPlan
from app.services.scm import loading_plan_service, supplier_inventory_service
from app.services.scm.upload_intake import read_upload

router = APIRouter()

# Same capability as the other upload channels: this rewrites what a container is planned
# from, so it sits behind the operator permission rather than the read one.
_WRITE = require_permission("scm.reorder.run")
_READ = require_permission("scm.dashboard.view")


def _plan_or_404(db: Session, plan_id: str) -> LoadingPlan:
    plan = db.query(LoadingPlan).filter(LoadingPlan.id == plan_id).first()
    if plan is None:
        # A 404 rather than an empty plan: the id came from somewhere, and rendering an empty
        # container for a plan that belongs to another company would be worse than saying no.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loading plan not found")
    return plan


# --------------------------------------------------------------------------- #
# supplier inventory
# --------------------------------------------------------------------------- #


@router.post("/supplier-inventory/preview")
async def preview_supplier_inventory(
    file: UploadFile = File(..., description="The supplier's own stock list"),
    supplier_id: str = Form(..., description="Which supplier sent it"),
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """What the file says, and how many rows it would replace. Writes nothing.

    The supplier is asked for because the sheet never says: it carries model numbers and
    quantities and no indication of who wrote it.
    """
    return supplier_inventory_service.preview(
        db, await read_upload(file), supplier_id=supplier_id
    )


@router.post("/supplier-inventory/apply")
async def apply_supplier_inventory(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    supplier_id: str = Form(...),
    validate_only: bool = Query(
        False,
        description="Test the file and write nothing. Returns {valid, errors, warnings, summary}.",
    ),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Replace this supplier's stock snapshot."""
    data = await read_upload(file)
    if validate_only:
        return supplier_inventory_service.validate(db, data, supplier_id=supplier_id)
    out = supplier_inventory_service.apply(
        db, data, supplier_id=supplier_id, actor=current_user.get("id")
    )
    if not out.get("readable"):
        missing = ", ".join(out.get("missing_columns") or [])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This file has no {missing} column."
                if missing
                else "This file could not be read."
            ),
        )
    db.commit()
    return out


@router.get("/supplier-inventory")
def list_supplier_inventory(
    supplier_id: str = Query(..., description="Whose stock list to show"),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """What we currently believe this supplier is holding."""
    from app.models.scm import SupplierInventory

    rows = (
        db.query(SupplierInventory)
        .filter(SupplierInventory.supplier_id == supplier_id)
        .order_by(SupplierInventory.qty_packed.desc())
        .all()
    )
    return {
        "supplier_id": supplier_id,
        "as_of": max((r.as_of for r in rows), default=None),
        "rows": [
            {
                "item_code": r.item_code,
                "product_id": str(r.product_id) if r.product_id else None,
                "product_name": r.product_name,
                "qty_packed": float(r.qty_packed or 0),
                "qty_unfinished": float(r.qty_unfinished or 0),
                "cbm_per_unit": float(r.cbm_per_unit) if r.cbm_per_unit is not None else None,
                "matched": r.product_id is not None,
            }
            for r in rows
        ],
    }


@router.get("/supplier-inventory/unfinished")
def list_unfinished(
    supplier_id: str = Query(...),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Stock the supplier holds unfinished, so it can be asked for (AC-E2)."""
    return {"rows": loading_plan_service.unfinished_at_supplier(db, supplier_id)}


# --------------------------------------------------------------------------- #
# loading plan
# --------------------------------------------------------------------------- #


@router.get("/container-sizes")
def get_container_sizes(
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Configured container volumes (AC-E3)."""
    return {"sizes": loading_plan_service.container_sizes(db)}


class ContainerSizeWrite(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    label: Optional[str] = None
    #: Internal LOADABLE volume, not the nominal external size. A 40HQ is sold as 76 cbm and
    #: packs about 68, and planning to the brochure figure is how a container arrives short.
    cbm: float = Field(..., gt=0)
    is_default: bool = False
    is_active: bool = True


def _size_or_404(db: Session, size_id: str) -> ContainerSize:
    row = db.query(ContainerSize).filter(ContainerSize.id == size_id).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Container size not found"
        )
    return row


def _clear_other_defaults(db: Session, keep_id: Optional[str]) -> None:
    """Exactly one default, or `_resolve_container` picks whichever row comes back first."""
    q = db.query(ContainerSize).filter(ContainerSize.is_default.is_(True))
    if keep_id:
        q = q.filter(ContainerSize.id != keep_id)
    q.update({"is_default": False}, synchronize_session=False)


@router.post("/container-sizes", status_code=status.HTTP_201_CREATED)
def create_container_size(
    body: ContainerSizeWrite,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    row = ContainerSize(
        id=str(uuid.uuid4()),
        code=body.code.strip(),
        label=body.label,
        cbm=body.cbm,
        is_default=body.is_default,
        is_active=body.is_active,
    )
    db.add(row)
    if body.is_default:
        _clear_other_defaults(db, row.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A container size called {body.code} already exists.",
        )
    return {"sizes": loading_plan_service.container_sizes(db)}


@router.put("/container-sizes/{size_id}")
def update_container_size(
    size_id: str,
    body: ContainerSizeWrite,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    row = _size_or_404(db, size_id)
    row.code = body.code.strip()
    row.label = body.label
    row.cbm = body.cbm
    row.is_default = body.is_default
    row.is_active = body.is_active
    if body.is_default:
        _clear_other_defaults(db, size_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A container size called {body.code} already exists.",
        )
    return {"sizes": loading_plan_service.container_sizes(db)}


@router.delete("/container-sizes/{size_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_container_size(
    size_id: str,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Hard delete, per the CRUD standard.

    Plans already built keep their own `container_cbm`, so deleting a size does not rewrite
    history - it only removes an option from the next plan.
    """
    db.delete(_size_or_404(db, size_id))
    db.commit()


class LoadingPlanRequest(BaseModel):
    supplier_id: str
    container_count: int = Field(1, ge=1)
    container_type: Optional[str] = None
    #: An override for a container that is not one of the configured sizes. Rare, and never
    #: the normal path: a size somebody keeps overriding belongs in the size table.
    container_cbm: Optional[float] = Field(None, gt=0)


@router.post("/loading-plans", status_code=status.HTTP_201_CREATED)
def create_loading_plan(
    body: LoadingPlanRequest,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    try:
        plan = loading_plan_service.build(
            db,
            supplier_id=body.supplier_id,
            container_count=body.container_count,
            container_type=body.container_type,
            container_cbm=body.container_cbm,
            actor=current_user.get("id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    out = loading_plan_service.serialize(db, plan)
    db.commit()
    return out


class LoadingPlanUpdate(BaseModel):
    container_count: Optional[int] = Field(None, ge=1)
    container_type: Optional[str] = None
    container_cbm: Optional[float] = Field(None, gt=0)


@router.patch("/loading-plans/{plan_id}")
def update_loading_plan(
    plan_id: str,
    body: LoadingPlanUpdate,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Re-run this plan with a different container count or size (AC-E6).

    In place, so one decision leaves one plan behind, and with no re-upload: the stock list
    is already held.
    """
    plan = _plan_or_404(db, plan_id)
    # What the caller did NOT change must survive the re-run. An explicit volume wins, then a
    # named size, and otherwise the plan keeps the volume it was built with - without this
    # last branch, changing only the container COUNT silently re-planned against the tenant
    # default size and the capacity came back a different number than the one on screen.
    if body.container_cbm is not None:
        cbm, ctype = body.container_cbm, body.container_type or plan.container_type
    elif body.container_type:
        cbm, ctype = None, body.container_type
    else:
        cbm, ctype = float(plan.container_cbm), plan.container_type
    try:
        plan = loading_plan_service.build(
            db,
            supplier_id=str(plan.supplier_id),
            container_count=body.container_count or plan.container_count,
            container_type=ctype,
            container_cbm=cbm,
            actor=current_user.get("id"),
            plan=plan,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    out = loading_plan_service.serialize(db, plan)
    db.commit()
    return out


@router.get("/loading-plans")
def list_loading_plans(
    supplier_id: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    q = db.query(LoadingPlan)
    if supplier_id:
        q = q.filter(LoadingPlan.supplier_id == supplier_id)
    rows = q.order_by(LoadingPlan.computed_at.desc()).limit(limit).all()
    return {
        "data": [loading_plan_service.serialize(db, p, with_lines=False) for p in rows],
        "total": len(rows),
    }


@router.get("/loading-plans/{plan_id}")
def get_loading_plan(
    plan_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    return loading_plan_service.serialize(db, _plan_or_404(db, plan_id))


@router.delete("/loading-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_loading_plan(
    plan_id: str,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Hard delete, with its lines, per the CRUD standard."""
    plan = _plan_or_404(db, plan_id)
    db.delete(plan)
    db.commit()
