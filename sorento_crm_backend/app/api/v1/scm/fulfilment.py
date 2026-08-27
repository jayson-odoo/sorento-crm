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
    supplier_code_alias_service,
    loading_plan_service,
    packing_list_service,
    spo_conversion_service,
    supplier_inventory_service,
    supplier_notice_service,
)
from app.services.scm.upload_intake import read_upload, read_upload_retained
from app.utils.http import content_disposition

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
    try:
        uuid.UUID(str(plan_id))
    except (ValueError, AttributeError, TypeError):
        # The column is a uuid, so a typo in the URL must be a 404 and not a database error.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loading plan not found")
    plan = db.query(LoadingPlan).filter(LoadingPlan.id == plan_id).first()
    if plan is None:
        # A 404 rather than an empty plan: the id came from somewhere, and rendering an empty
        # container for a plan that belongs to another company would be worse than saying no.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loading plan not found")
    return plan


def _refuse_cancelled(plan: LoadingPlan) -> None:
    """A cancelled plan is a record of what was asked, not a form (AC-A8)."""
    if plan.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "plan_cancelled",
                "message": "This plan is cancelled, so it can no longer be changed.",
            },
        )


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
    upload = await read_upload_retained(file)
    if validate_only:
        return supplier_inventory_service.validate(db, upload.data, supplier_id=supplier_id)
    out = supplier_inventory_service.apply(
        db, upload.data, supplier_id=supplier_id, actor=current_user.get("id")
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
    # Retain the supplier's OWN sheet, previewable like any resource attachment, so Ms Tee
    # can cross-check without opening Excel. Best-effort and AFTER the commit above - a
    # storage hiccup here must never turn a successful apply into a failed request.
    supplier_inventory_service.store_stock_list_attachment(
        db,
        upload.source_bytes,
        filename=upload.source_name,
        content_type=upload.content_type,
        supplier_id=supplier_id,
        uploaded_by=current_user.get("id"),
    )
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


@router.get("/supplier-inventory/stock-list-file")
def get_supplier_stock_list_file(
    supplier_id: str = Query(..., description="Whose stored stock list to show"),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The latest retained copy of the supplier's own sheet, so it can be opened in-system
    (like a resource attachment) instead of in Excel. `attachment_id` is null when nothing
    has been uploaded yet, or a past upload's storage write failed."""
    found = supplier_inventory_service.latest_stock_list_attachment(db, supplier_id=supplier_id)
    return {
        "supplier_id": supplier_id,
        "attachment_id": found["attachment_id"] if found else None,
        "filename": found["filename"] if found else None,
        "uploaded_at": found["uploaded_at"] if found else None,
    }


# --------------------------------------------------------------------------- #
# loading plan
# --------------------------------------------------------------------------- #


class SupplierCodeAliasWrite(BaseModel):
    supplier_id: str
    #: The supplier's spelling, verbatim - it is what their file says.
    supplier_code: str = Field(..., min_length=1, max_length=120)
    #: Exactly one of the two (R19, R20). A supplier who sells the whole WC writes our SET
    #: code, and no product carries it, so a picker that could only answer with a product
    #: had no way to say what the code means. The service refuses both and neither.
    product_id: Optional[str] = None
    product_set_id: Optional[str] = None


@router.get("/supplier-code-aliases")
def list_supplier_code_aliases(
    supplier_id: str = Query(..., description="Whose codes to show"),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """What this supplier's codes have been ruled to mean - automatic and by hand (R16)."""
    return {"data": supplier_code_alias_service.list_for_supplier(db, supplier_id)}


@router.get("/supplier-code-aliases/unmatched")
def list_unmatched_supplier_codes(
    supplier_id: str = Query(..., description="Whose unbound codes to show"),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The codes this supplier sent that bind to nothing we hold - the list somebody comes
    back to answer (R16). Declared before the `{alias_id}` routes so the literal path is not
    swallowed by the parameter."""
    return {"data": supplier_code_alias_service.unmatched_for_supplier(db, supplier_id)}


@router.post("/supplier-code-aliases", status_code=status.HTTP_201_CREATED)
def create_supplier_code_alias(
    body: SupplierCodeAliasWrite,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """"This code is that product" - or that SET. Replaces any earlier ruling and RE-BINDS
    the rows already uploaded under it, so the loading plan and the PI convert show the
    answer today rather than after the next upload."""
    out = supplier_code_alias_service.create(
        db,
        supplier_id=body.supplier_id,
        supplier_code=body.supplier_code,
        product_id=body.product_id,
        product_set_id=body.product_set_id,
        actor=_actor(current_user),
    )
    db.commit()
    return out


class SupplierCodeDismiss(BaseModel):
    supplier_id: str
    supplier_code: str = Field(..., min_length=1, max_length=120)


@router.post("/supplier-code-aliases/dismiss", status_code=status.HTTP_201_CREATED)
def dismiss_supplier_code(
    body: SupplierCodeDismiss,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """"That code is not one of ours." Takes it out of the queue and UNBINDS the rows already
    uploaded under it, so nothing goes on being offered to the plan under a code nobody
    claims. Forget (the DELETE below) puts it back.

    Declared before the `{alias_id}` route so the literal path is not swallowed by the
    parameter."""
    out = supplier_code_alias_service.dismiss(
        db,
        supplier_id=body.supplier_id,
        supplier_code=body.supplier_code,
        actor=_actor(current_user),
    )
    db.commit()
    return out


class SupplierCodeRematch(BaseModel):
    supplier_id: str


@router.post("/supplier-code-aliases/rematch")
def rematch_supplier_codes(
    body: SupplierCodeRematch,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Run the ladder again over what is still unbound (R18).

    Master data moves after a file lands - a product added, an alias recorded elsewhere - and
    the rows uploaded before it stay unbound under a code the ladder can now answer. Without
    this the only way to make them catch up is to upload the same file again.

    No `response_model`: the three counts ARE the answer the screen reports, and a model
    would be one more place for them to be dropped. Declared before the `{alias_id}` route so
    the literal path is not swallowed by the parameter."""
    out = supplier_code_alias_service.rematch(
        db, supplier_id=body.supplier_id, actor=_actor(current_user)
    )
    db.commit()
    return out


@router.delete("/supplier-code-aliases/{alias_id}")
def delete_supplier_code_alias(
    alias_id: str,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Forget the ruling, and put the rows back to whatever the ladder says now."""
    out = supplier_code_alias_service.delete(
        db, alias_id, actor=_actor(current_user)
    )
    db.commit()
    return out


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
    #: is planned to 65 here (the captain's ruling, 26 Aug), and planning to the brochure
    #: figure is how a container arrives short.
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


class LoadingPlanCreate(BaseModel):
    """Start a plan: whose container, how far ahead, and which document it starts from."""

    supplier_id: str
    #: "Sales order cut-off". None means every open order counts - the same words and the
    #: same rule the reorder run's own horizon uses.
    plan_horizon_date: Optional[date] = None
    document_kind: str = Field("none", pattern="^(stock_list|proforma|none)$")
    #: The retained sheet this plan was started from, so the record can offer "View uploaded
    #: list". Optional: the retain is itself best-effort, and a plan without it is still a plan.
    source_attachment_id: Optional[str] = None


@router.post("/loading-plans", status_code=status.HTTP_201_CREATED)
def create_loading_plan(
    body: LoadingPlanCreate,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """One plan row (R1). The suggestion behind it is computed on demand, never stored."""
    try:
        plan = loading_plan_service.create_record(
            db,
            supplier_id=body.supplier_id,
            plan_horizon_date=body.plan_horizon_date,
            document_kind=body.document_kind,
            source_attachment_id=body.source_attachment_id,
            actor=_actor(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    out = loading_plan_service.record_dict(db, plan)
    db.commit()
    return out


class LoadingPlanUpdate(BaseModel):
    """The only thing an open plan changes about itself: how far ahead it is planning."""

    plan_horizon_date: Optional[date] = None


@router.patch("/loading-plans/{plan_id}")
def update_loading_plan(
    plan_id: str,
    body: LoadingPlanUpdate,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Change the sales order cut-off (the record's "Change cut-off").

    A PATCH on the plan rather than a second plan: the buyer is narrowing the same ask, and
    two rows for one container would have nothing to tell them apart.
    """
    plan = _plan_or_404(db, plan_id)
    _refuse_cancelled(plan)
    plan.plan_horizon_date = body.plan_horizon_date
    db.flush()
    out = loading_plan_service.record_dict(db, plan)
    db.commit()
    return out


@router.get("/loading-plans")
def list_loading_plans(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    query: Optional[str] = Query(None),
    #: "active" (the default chip) is planning + sent. A cancelled plan is a decision
    #: already made, and a list that opens on it hides the work in front of somebody.
    status_filter: Optional[str] = Query(None, alias="status"),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    return loading_plan_service.list_records(
        db,
        page=page,
        limit=limit,
        sort=sort,
        direction=dir,
        query=query,
        status=status_filter,
    )


@router.get("/loading-plans/{plan_id}")
def get_loading_plan(
    plan_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    return loading_plan_service.record_dict(db, _plan_or_404(db, plan_id))


@router.post("/loading-plans/{plan_id}/cancel")
def cancel_loading_plan(
    plan_id: str,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Stop working on this plan, and stop the supplier's link answering (Q4)."""
    plan = _plan_or_404(db, plan_id)
    loading_plan_service.cancel_record(db, plan, actor=_actor(current_user))
    out = loading_plan_service.record_dict(db, plan)
    db.commit()
    return out


class LoadingPlanEdits(BaseModel):
    """The WHOLE map of typed quantities, `row_key -> qty` (R6).

    Not a patch: what is not in the map is not an edit any more, so a cleared cell cannot
    survive as a stale override, and one Save is one transaction.
    """

    line_edits: dict[str, float] = Field(default_factory=dict)


@router.put("/loading-plans/{plan_id}/edits")
def save_loading_plan_edits(
    plan_id: str,
    body: LoadingPlanEdits,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    plan = _plan_or_404(db, plan_id)
    _refuse_cancelled(plan)
    loading_plan_service.save_edits(db, plan, body.line_edits)
    out = loading_plan_service.record_dict(db, plan)
    db.commit()
    return out


@router.delete("/loading-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_loading_plan(
    plan_id: str,
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Hard delete, with its lines, per the CRUD standard - unless it was already sent.

    Q5: a notice is the record of what left the building, so deleting the plan under it would
    leave that record pointing at nothing. A sent plan is cancelled instead.
    """
    plan = _plan_or_404(db, plan_id)
    if loading_plan_service.has_notices(db, plan_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "plan_sent",
                "message": "Sent plans are cancelled, not deleted.",
            },
        )
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
    kind: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """A short-lived link to one of the notice's files, so Ms Tee can send it by hand (AC-F3).

    `kind=xlsx` is the supplier's own stock list with the quantity to load filled in (AC-C4);
    it exists on a container request and not on a loading notice.
    """
    return supplier_notice_service.document_url(db, notice_id, kind=kind)


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


class SpoLocationSplit(BaseModel):
    warehouse_id: str
    qty: float = Field(..., gt=0)


class SpoLineConfirm(BaseModel):
    shipment_line_id: str
    qty: float = Field(0, ge=0)
    include: bool = False
    # The multi-location ask (fourth doctrine-correction ask): zero, one or several
    # destinations for this ONE line's SPO qty, each writing its own `spo_allocations` row in
    # the same confirm (see `spo_conversion_service.create`'s docstring). Empty means no
    # allocation is written for this line, byte-identical to every call before this ask - the
    # single `warehouse_id` field the second amendment introduced is now the one-split case of
    # this list, not a separate field.
    location_splits: list[SpoLocationSplit] = Field(default_factory=list)
    # Which PO takes to draw from (F7, AC-G1). None means "every take you re-derive", which
    # is what every caller before this ask sent; a LIST narrows it, and the SPO quantity
    # falls to what those takes cover.
    po_take_ids: Optional[list[str]] = None
    # Which demand this SPO is being pointed at - `so_coverage[].key` (F7, AC-G3). The
    # project half is written as links; the retail half steers the split on screen and has
    # no row of its own to hang a link on.
    so_line_ids: list[str] = Field(default_factory=list)


class SpoCreateRequest(BaseModel):
    lines: list[SpoLineConfirm] = Field(
        ..., min_length=1, description="Every line on the shipment, ticked or not"
    )


@router.post("/packing-lists/preview")
async def preview_packing_list(
    file: UploadFile = File(..., description="The pre-load list or packing list"),
    supplier_id: Optional[str] = Form(None),
    currency: Optional[str] = Form(
        None, description="Only needed when neither the file nor the price list says"
    ),
    _user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Every container block the file holds, and what each would create. Writes nothing.

    Takes the supplier and the currency the apply will take, so the preview can say which
    money the prices are in before anything is written rather than after.
    """
    return packing_list_service.preview(
        db,
        await read_upload(file),
        source_ref=file.filename,
        supplier_id=supplier_id,
        currency=currency,
    )


@router.post("/packing-lists/apply")
async def apply_packing_list(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    supplier_id: Optional[str] = Form(
        None, description="Whose packing list this is. Required unless validate_only."
    ),
    shipment_date: Optional[str] = Form(None),
    currency: Optional[str] = Form(
        None, description="Only needed when neither the file nor the price list says"
    ),
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
        return packing_list_service.validate(
            db, data, source_ref=file.filename, supplier_id=supplier_id, currency=currency
        )

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
        currency=currency,
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
        # A container read before the per-supplier line existed - or read with no lines at
        # all - has its factory on the header and nowhere else. Reading the lines alone
        # printed no supplier under those containers, which says "we do not know" about a
        # container we do know.
        header_only = {
            str(r.supplier_id)
            for r in rows
            if r.supplier_id is not None and not suppliers_by_shipment.get(str(r.id))
        }
        if header_only:
            header_suppliers = {
                str(s.id): {
                    "supplier_id": str(s.id),
                    "supplier_code": s.supplier_code,
                    "supplier_name": s.supplier_name,
                }
                for s in db.query(Supplier).filter(Supplier.id.in_(header_only)).all()
            }
            for r in rows:
                key = str(r.id)
                if suppliers_by_shipment.get(key):
                    continue
                entry = (
                    header_suppliers.get(str(r.supplier_id))
                    if r.supplier_id is not None
                    else None
                )
                if entry is not None:
                    suppliers_by_shipment[key] = [entry]
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
        headers={"Content-Disposition": content_disposition(filename)},
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


@router.get("/inbound-shipments/{shipment_id}/spo-suggestion")
def spo_suggestion(
    shipment_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The SPO planner table: per shipment line, what an open PO PULLS this SPO up to - never
    a deduction (doctrine correction, `spo_conversion_service`'s module docstring, "fifth
    amendment") - and why a line cannot convert (no supplier, or nothing open to pull from at
    all). Also carries `po_takes` (the earliest-first per-PO breakdown behind `po_covered_qty`,
    each now naming its own PO date and supplier) and `location_options` +
    `suggested_warehouse_id` (candidate destination warehouses, ranked by Fulfilment Priority,
    each carrying `demand_lines` - the open SO demand this SPO would go on to serve there).
    `already_converted: true` when this shipment already has SPOs (409 on the write below); the
    caller shows the existing SPOs instead of the confirm screen. `self_heal_note` is non-null
    only when this call actually cleaned up a stale link (a CRM SPO removed some other way than
    the DELETE below) - see `spo_conversion_service._heal_stale_links`.
    """
    out = spo_conversion_service.suggest(db, shipment_id)
    db.commit()  # persists any self-heal cleanup (get_db closes without commit)
    return out


@router.post("/inbound-shipments/{shipment_id}/spo", status_code=status.HTTP_201_CREATED)
def create_spo(
    shipment_id: str,
    body: SpoCreateRequest,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """One CRM SPO per supplier represented on this shipment, from the confirmed lines.

    Refused (409) if this shipment already has one - re-running "Create SPO" must not
    double what the office is asked to key into AutoCount.
    """
    out = spo_conversion_service.create(
        db,
        shipment_id,
        [ln.model_dump() for ln in body.lines],
        actor=_actor(current_user),
        actor_user_id=current_user.get("id"),
    )
    db.commit()
    return out


@router.delete("/inbound-shipments/{shipment_id}/spo")
def delete_spo(
    shipment_id: str,
    current_user: dict = Depends(_WRITE),
    db: Session = Depends(get_db),
):
    """Unwind this shipment's SPO conversion - the Delete action on the planner's
    already-converted state. The mirror of `create_spo` above: same permission, same
    shipment scoping. Refused (409) if any header this shipment is linked to was not created
    by Create SPO (`source_system != crm_spo`) - an AutoCount import is never touched here.
    404 when this shipment has no SPO to delete (nothing ever converted, or a prior self-heal
    already cleared it)."""
    out = spo_conversion_service.unwind(db, shipment_id)
    db.commit()
    return out


@router.get("/inbound-shipments/{shipment_id}/spo-worksheet/export")
def export_spo_worksheet(
    shipment_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The AutoCount handoff: exactly what to key, per supplier. 404 until "Create SPO" has
    actually run on this shipment."""
    payload = spo_conversion_service.worksheet_payload(db, shipment_id)
    filename = spo_conversion_service.export_filename(payload)
    return Response(
        content=spo_conversion_service.to_xlsx(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition(filename)},
    )
