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
from datetime import date
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.scm import ContainerSize, LoadingPlan
from app.services.scm import (
    allocation_suggestion_service,
    consolidated_packing_list,
    loading_plan_service,
    packing_list_service,
    supplier_inventory_service,
    supplier_notice_service,
)
from app.services.scm.upload_intake import read_upload

router = APIRouter()

# Same capability as the other upload channels: this rewrites what a container is planned
# from, so it sits behind the operator permission rather than the read one.
_WRITE = require_permission("scm.reorder.run")
_READ = require_permission("scm.dashboard.view")


def _actor(user: Optional[dict]) -> Optional[str]:
    """The caller's human name, never their id - same rule as every other SCM provenance."""
    user = user or {}
    return user.get("name") or user.get("email") or None


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


# --------------------------------------------------------------------------- #
# supplier notice (S8)
# --------------------------------------------------------------------------- #


@router.post("/loading-plans/{plan_id}/notices", status_code=status.HTTP_201_CREATED)
def approve_loading_plan(
    plan_id: str,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Approve the plan and tell the supplier: one action, every channel (AC-F1).

    Behind the operator permission, not the read one: this sends mail to an outside party.
    """
    _plan_or_404(db, plan_id)
    return supplier_notice_service.approve_and_notify(
        db, plan_id, actor=_actor(_user)
    )


@router.get("/loading-plans/{plan_id}/notices")
def list_plan_notices(
    plan_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    _plan_or_404(db, plan_id)
    rows = supplier_notice_service.list_for_plan(db, plan_id)
    return {"data": rows, "total": len(rows)}


@router.get("/supplier-notices")
def list_supplier_notices(
    supplier_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    rows = supplier_notice_service.list_for_supplier(db, supplier_id, limit=limit)
    return {"data": rows, "total": len(rows)}


@router.get("/supplier-notices/{notice_id}/document")
def supplier_notice_document(
    notice_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """A short-lived link to the document, so Ms Tee can send it by hand too (AC-F3)."""
    return supplier_notice_service.document_url(db, notice_id)


# --------------------------------------------------------------------------- #
# packing list and SPO allocation (S9)
# --------------------------------------------------------------------------- #


class AllocationSplit(BaseModel):
    po_line_id: Optional[str] = Field(
        None, description="Which Supply PO line this draws down. Null when it draws down none."
    )
    warehouse_id: str = Field(..., description="Where the quantity lands")
    qty: float = Field(..., gt=0)


class AllocationDecision(BaseModel):
    shipment_line_id: str
    splits: list[AllocationSplit] = Field(
        ..., min_length=1, description="One or more, and they must sum to what shipped"
    )


class AllocationApproval(BaseModel):
    decisions: list[AllocationDecision] = Field(..., min_length=1)


@router.post("/packing-lists/preview")
async def preview_packing_list(
    file: UploadFile = File(..., description="The pre-load list or packing list"),
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Every container block the file holds, and what each would create. Writes nothing."""
    return packing_list_service.preview(
        db, await read_upload(file), source_ref=file.filename
    )


@router.post("/packing-lists/apply")
async def apply_packing_list(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    supplier_id: Optional[str] = Form(
        None, description="Whose packing list this is. Required unless validate_only."
    ),
    shipment_date: Optional[str] = Form(None),
    validate_only: bool = Query(
        False,
        description="Test the file and write nothing. Returns {valid, errors, warnings, summary}.",
    ),
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """One inbound shipment per container block. Re-uploading the same file updates in place.

    The supplier is required on the writing path and refused before the file is even read.
    A packing list arrives from one factory, and an upload that will not say which one
    cannot be told apart from the container's whole contents - so it would replace the
    other factories' lines, which is the data loss the per-supplier line exists to end.
    `validate_only` writes nothing and may therefore omit it.
    """
    supplier = (supplier_id or "").strip()
    if not validate_only and not supplier:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "supplier_id is required: a packing list is uploaded as one supplier so it "
                "can never replace another supplier's lines"
            ),
        )
    data = await read_upload(file)
    if validate_only:
        return packing_list_service.validate(db, data, source_ref=file.filename)

    parsed_date = None
    if shipment_date:
        try:
            parsed_date = date.fromisoformat(shipment_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="shipment_date must be YYYY-MM-DD",
            )

    out = packing_list_service.apply(
        db,
        data,
        supplier_id=supplier,
        shipment_date=parsed_date,
        source_ref=file.filename,
        actor_id=current_user.get("id"),
    )
    db.commit()
    return out


@router.get("/inbound-shipments")
def list_inbound_shipments(
    supplier_id: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Containers we have read, newest first.

    The screen had only what the last upload returned, so a refresh emptied it and the work
    looked lost. A container is read once and decided later, often not in the same sitting.
    """
    from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
    from app.services.procurement_service import shipment_supplier_predicate

    q = db.query(InboundShipment)
    if supplier_id:
        # Header OR any line, shared with every other supplier filter: a container that
        # carries two factories has a NULL header supplier, so filtering on the header
        # alone hid the mixed containers from both of the suppliers actually on them.
        q = q.filter(shipment_supplier_predicate(supplier_id))
    rows = q.order_by(InboundShipment.created_at.desc()).limit(limit).all()

    shipment_ids = [r.id for r in rows]
    # Who is ON each container, in one query rather than one per row.
    suppliers_by_shipment: dict[str, list[dict]] = {}
    if shipment_ids:
        pairs = (
            db.query(
                InboundShipmentLine.shipment_id,
                Supplier.id,
                Supplier.supplier_code,
                Supplier.supplier_name,
            )
            .join(Supplier, Supplier.id == InboundShipmentLine.supplier_id)
            .filter(InboundShipmentLine.shipment_id.in_(shipment_ids))
            .distinct()
            .order_by(Supplier.supplier_name)
            .all()
        )
        for ship_id, sup_id, code, name in pairs:
            suppliers_by_shipment.setdefault(str(ship_id), []).append(
                {
                    "supplier_id": str(sup_id),
                    "supplier_code": code,
                    "supplier_name": name,
                }
            )
    line_counts: dict[str, int] = {}
    if shipment_ids:
        for ship_id, count in (
            db.query(InboundShipmentLine.shipment_id, func.count(InboundShipmentLine.id))
            .filter(InboundShipmentLine.shipment_id.in_(shipment_ids))
            .group_by(InboundShipmentLine.shipment_id)
            .all()
        ):
            line_counts[str(ship_id)] = int(count)

    return {
        "data": [
            {
                "shipment_id": str(r.id),
                "shipment_number": r.shipment_number,
                "container_no": r.shipping_container_number,
                "bl_no": r.bill_of_lading_number,
                "status": r.shipment_status,
                "lines": line_counts.get(str(r.id), 0),
                "suppliers": suppliers_by_shipment.get(str(r.id), []),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/inbound-shipments/{shipment_id}/allocation-suggestion")
def allocation_suggestion(
    shipment_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Per shipment line, the proposed Supply PO line and location, with its alternatives."""
    return allocation_suggestion_service.suggest(db, shipment_id)


@router.get("/inbound-shipments/{shipment_id}/packing-list")
def consolidated_packing_list_for_shipment(
    shipment_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The Sorento packing list: every factory on this container, subtotalled and split."""
    return consolidated_packing_list.build(db, shipment_id)


@router.get("/inbound-shipments/{shipment_id}/packing-list/export")
def export_consolidated_packing_list(
    shipment_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The same list as a workbook, named after the container rather than after its id."""
    payload = consolidated_packing_list.build(db, shipment_id)
    filename = consolidated_packing_list.export_filename(payload)
    return Response(
        content=consolidated_packing_list.to_xlsx(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/inbound-shipments/{shipment_id}/allocations")
def approve_allocations(
    shipment_id: str,
    body: AllocationApproval,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Write the allocations and advance the purchase orders, in one action (AC-G6)."""
    out = allocation_suggestion_service.approve(
        db,
        shipment_id,
        [d.model_dump() for d in body.decisions],
        actor_id=current_user.get("id"),
    )
    db.commit()
    return out
