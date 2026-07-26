"""Collections, bundles, and resolving either into something renderable.

Permissions follow the same split as pages: reading a collection is
``page.view`` (automation may need it), changing one is ``page.edit``. There is
no separate collection permission - a collection has no life of its own outside
the page that shows it, and a third slug would be one more thing to get wrong in
a role.

Resolution endpoints take the viewer from the request principal. A staff user
previewing sees staff prices; the public renderer resolves anonymously. The
saved document never carried a price either way (AC-G1).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.dealer_kit import (
    BundleWrite,
    TileTemplateOut,
    TileTemplateWrite,
    CollectionOut,
    CollectionRename,
    CollectionWrite,
    ResolvedBundleOut,
    ResolvedCollectionOut,
    TileOut,
)
from app.services.dealer_kit import (
    bundle_service,
    collection_service,
    tile_template_service,
)
from app.services.dealer_kit.viewer import ViewerContext

router = APIRouter()

_VIEW = require_permission_with_api_key("dealer_kit.page.view")
_EDIT = require_permission("dealer_kit.page.edit")


def _user_id(user: dict | None) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _out(db: Session, row) -> CollectionOut:
    return CollectionOut(
        id=row.id,
        scope=row.scope,
        name=row.name,
        page_id=row.page_id,
        conditions=row.conditions_json,
        pinned_product_ids=list(row.pinned_product_ids or []),
        excluded_product_ids=list(row.excluded_product_ids or []),
        manual_order=list(row.manual_order or []),
        member_count=len(collection_service.resolve_members(db, row)),
        updated_at=row.updated_at,
    )


# --------------------------------------------------------------------------
# Collections
# --------------------------------------------------------------------------


@router.get("/collections", response_model=list[CollectionOut])
def list_collections(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    """Reusable collections only. Page-scoped ones are an editor detail (AC-F4)."""
    return [_out(db, row) for row in collection_service.list_library(db)]


@router.post(
    "/collections", response_model=CollectionOut, status_code=status.HTTP_201_CREATED
)
def create_collection(
    payload: CollectionWrite,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    row = collection_service.create_collection(
        db,
        scope=payload.scope,
        page_id=payload.page_id,
        name=payload.name,
        conditions=payload.conditions,
        pinned_product_ids=payload.pinned_product_ids,
        excluded_product_ids=payload.excluded_product_ids,
        manual_order=payload.manual_order,
        user_id=_user_id(user),
    )
    return _out(db, row)


@router.get("/collections/{collection_id}", response_model=CollectionOut)
def get_collection(
    collection_id: str, db: Session = Depends(get_db), _user: dict = Depends(_VIEW)
):
    return _out(db, collection_service.get_collection(db, collection_id))


@router.put("/collections/{collection_id}", response_model=CollectionOut)
def update_collection(
    collection_id: str,
    payload: CollectionWrite,
    db: Session = Depends(get_db),
    _user: dict = Depends(_EDIT),
):
    row = collection_service.update_collection(
        db,
        collection_id,
        name=payload.name,
        conditions_json=payload.conditions,
        pinned_product_ids=payload.pinned_product_ids,
        excluded_product_ids=payload.excluded_product_ids,
        manual_order=payload.manual_order,
    )
    return _out(db, row)


@router.post("/collections/{collection_id}/save-as-library", response_model=CollectionOut)
def save_as_library(
    collection_id: str,
    payload: CollectionRename,
    db: Session = Depends(get_db),
    _user: dict = Depends(_EDIT),
):
    """Promote a page's own selection into the reusable library (AC-F5).

    The same row is promoted, so the page that built it stays bound to it.
    """
    return _out(db, collection_service.save_as_library(db, collection_id, payload.name))


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: str, db: Session = Depends(get_db), _user: dict = Depends(_EDIT)
):
    collection_service.delete_collection(db, collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/collections/{collection_id}/resolve", response_model=ResolvedCollectionOut)
def resolve_collection(
    collection_id: str,
    show_invoice_price: bool = Query(False, alias="showInvoicePrice"),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    row = collection_service.get_collection(db, collection_id)
    # An authenticated CRM principal is staff. The public renderer never reaches
    # this route - it resolves anonymously through the public router.
    viewer = ViewerContext(is_staff=True, show_invoice_price=show_invoice_price)
    return ResolvedCollectionOut(
        collection_id=row.id,
        name=row.name,
        tiles=[TileOut(**tile) for tile in collection_service.resolve_tiles(db, row, viewer)],
    )


# --------------------------------------------------------------------------
# Bundles
# --------------------------------------------------------------------------


@router.get("/bundles", response_model=list[ResolvedBundleOut])
def list_bundles(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    """Resolved, so the list can show availability without a second call - and
    so it can never show a stale stored flag."""
    return [
        ResolvedBundleOut(**bundle_service.resolve_bundle(db, bundle.id))
        for bundle in bundle_service.list_bundles(db)
    ]


@router.post(
    "/bundles", response_model=ResolvedBundleOut, status_code=status.HTTP_201_CREATED
)
def create_bundle(
    payload: BundleWrite, db: Session = Depends(get_db), user: dict = Depends(_EDIT)
):
    bundle = bundle_service.create_bundle(
        db,
        name=payload.name,
        price=payload.price,
        components=[
            {"product_id": component.product_id, "quantity": component.quantity}
            for component in payload.components
        ],
        user_id=_user_id(user),
    )
    return ResolvedBundleOut(**bundle_service.resolve_bundle(db, bundle.id))


@router.get("/bundles/{bundle_id}/resolve", response_model=ResolvedBundleOut)
def resolve_bundle(
    bundle_id: str, db: Session = Depends(get_db), _user: dict = Depends(_VIEW)
):
    return ResolvedBundleOut(**bundle_service.resolve_bundle(db, bundle_id))


@router.delete("/bundles/{bundle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bundle(
    bundle_id: str, db: Session = Depends(get_db), _user: dict = Depends(_EDIT)
):
    bundle_service.delete_bundle(db, bundle_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# Tile designs
# --------------------------------------------------------------------------


def _template_out(row) -> TileTemplateOut:
    return TileTemplateOut(
        id=row.id,
        name=row.name,
        fields=tile_template_service.fields_of(row),
        updated_at=row.updated_at,
    )


@router.get("/tile-templates", response_model=list[TileTemplateOut])
def list_tile_templates(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    return [_template_out(row) for row in tile_template_service.list_templates(db)]


@router.post(
    "/tile-templates", response_model=TileTemplateOut, status_code=status.HTTP_201_CREATED
)
def create_tile_template(
    payload: TileTemplateWrite, db: Session = Depends(get_db), user: dict = Depends(_EDIT)
):
    return _template_out(
        tile_template_service.create_template(
            db, name=payload.name, fields=payload.fields, user_id=_user_id(user)
        )
    )


@router.put("/tile-templates/{template_id}", response_model=TileTemplateOut)
def update_tile_template(
    template_id: str,
    payload: TileTemplateWrite,
    db: Session = Depends(get_db),
    _user: dict = Depends(_EDIT),
):
    return _template_out(
        tile_template_service.update_template(
            db, template_id, name=payload.name, fields=payload.fields
        )
    )


@router.delete("/tile-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tile_template(
    template_id: str, db: Session = Depends(get_db), _user: dict = Depends(_EDIT)
):
    tile_template_service.delete_template(db, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
