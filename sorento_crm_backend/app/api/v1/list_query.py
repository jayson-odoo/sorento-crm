"""Dynamic list query metadata, advanced search, and export."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.list_query_metadata import ListQueryField
from app.models.user import UserListColumnConfig, UserPermission
from app.schemas.list_query import (
    ListExportRequest,
    ListQueryFieldResponse,
    ListQueryResourceResponse,
    ListSearchRequest,
    UserListColumnConfigPayload,
    UserListColumnConfigResponse,
)
from app.services.error_handler import handle_internal_error
from app.services.list_query_export_service import ListQueryExportService
from app.services.list_query_metadata_service import ListQueryMetadataService
from app.services.list_query_registry import get_adapter, require_adapter
from app.services.list_query_search_service import ListQuerySearchService
from app.services.user_service import UserPermissionService
from app.services.workflow_submission_dynamic_list_query import (
    build_dynamic_field_metas_for_definition,
    get_published_schema_for_definition,
)

router = APIRouter()


def _config_dict(raw: Any) -> Dict[str, Any] | None:
    return raw if isinstance(raw, dict) else None


def _orders_export_ui_meta(f: ListQueryField) -> tuple[str | None, str | None]:
    """Derive export dialog hierarchy for orders (order vs line → product / warehouse)."""
    if not bool(getattr(f, "is_line_field", False)):
        return "order", None
    fk = (str(getattr(f, "field_key", "") or "")).lower()
    if fk.startswith("line_product"):
        return "line", "product"
    if fk.startswith("line_warehouse"):
        return "line", "warehouse"
    return "line", None


def _infer_filter_ui_type(f: ListQueryField) -> str:
    ck = str(getattr(f, "compile_key", "") or "")
    dtype = str(getattr(f, "data_type", "string") or "string").lower()
    if ".id" in ck or dtype == "uuid":
        return "foreign_key"
    if dtype in ("number", "integer", "float", "decimal"):
        return "number"
    if dtype in ("date", "datetime"):
        return "date"
    if dtype in ("boolean",):
        return "select"
    return "text"


def _can_view(db: Session, user_id: str, resource_key: str) -> bool:
    adapter = get_adapter(resource_key)
    slug = adapter.view_slug if adapter else None
    if not slug:
        return False
    return UserPermissionService(db).check_user_has_permission(user_id, slug)


def _can_view_listing_key(db: Session, user_id: str, listing_key: str) -> bool:
    """
    Personalization configs are authorized by the listing key itself.

    This repo expects `listing_key` to be either:
    - the RBAC view permission slug (e.g. `order_management.orders.view`), or
    - a composite key prefixed with the RBAC permission slug, using `::`:
      `order_management.orders.view::orders-list`.
    """
    listing_key = (listing_key or "").strip()
    if not listing_key:
        return False
    perm_slug = listing_key.split("::", 1)[0].strip() or listing_key

    # If the permission slug does not exist in the RBAC catalog, treat the listing
    # as "module-auth only" (many routes in this repo use module guards instead
    # of fine-grained `require_permission`).
    perm_exists = db.query(UserPermission).filter(UserPermission.slug == perm_slug).first()
    if not perm_exists:
        return True

    return UserPermissionService(db).check_user_has_permission(user_id, perm_slug)


@router.get("/resources", response_model=List[ListQueryResourceResponse])
def list_resources(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ListQueryMetadataService(db)
    all_r = svc.list_resources()
    uid = current_user["id"]
    return [
        r
        for r in all_r
        if _can_view(db, uid, str(getattr(r, "resource_key", "") or ""))
    ]


@router.get("/resources/{resource_key}/fields", response_model=List[ListQueryFieldResponse])
def list_fields(
    resource_key: str,
    definition_id: Optional[str] = Query(
        None,
        description="For workflow_form_submissions: published schema of this definition adds form-field filters.",
    ),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_view(db, current_user["id"], resource_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    svc = ListQueryMetadataService(db)
    fields = svc.list_fields(resource_key)
    if not fields and not svc.get_resource(resource_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource")
    out: list[ListQueryFieldResponse] = []
    for f in fields:
        base = ListQueryFieldResponse.model_validate(f)
        sec, sub = (None, None)
        if resource_key == "orders":
            sec, sub = _orders_export_ui_meta(f)
        out.append(
            base.model_copy(
                update={
                    "export_section": sec,
                    "export_subgroup": sub,
                    "filter_ui_type": _infer_filter_ui_type(f),
                    "option_source": None,
                    "relation_resource_key": None,
                    "relation_label_field": None,
                    "is_generated": True,
                    "managed_by": "schema-introspection",
                }
            )
        )

    if resource_key == "workflow_form_submissions" and definition_id:
        schema = get_published_schema_for_definition(db, definition_id.strip())
        if schema:
            for m in build_dynamic_field_metas_for_definition(schema):
                out.append(
                    ListQueryFieldResponse(
                        field_key=m.field_key,
                        label=m.label,
                        data_type=m.data_type,
                        compile_key=m.compile_key,
                        allowed_operators=m.allowed_operators,
                        filterable=m.filterable,
                        exportable=m.exportable,
                        export_column_name=m.export_column_name,
                        is_line_field=m.is_line_field,
                        sort_order=m.sort_order,
                        export_section=None,
                        export_subgroup=None,
                        filter_ui_type="text",
                        option_source=None,
                        relation_resource_key=None,
                        relation_label_field=None,
                        is_generated=True,
                        managed_by="workflow-schema",
                    )
                )
    return out


@router.post("/search")
def advanced_search(
    body: ListSearchRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_adapter(body.resource)
    if not _can_view(db, current_user["id"], body.resource):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    try:
        result = ListQuerySearchService(db).search(body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))

    adapter = require_adapter(body.resource)
    data = adapter.serializer(result["data"])

    return {
        "data": data,
        "pagination": result["pagination"],
        "empty": result["empty"],
    }


@router.post("/export")
def export_rows(
    body: ListExportRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = require_adapter(body.resource)
    slug = adapter.export_slug
    if not slug or not UserPermissionService(db).check_user_has_permission(current_user["id"], slug):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Export permission required")
    try:
        rows = ListQueryExportService(db).export_rows(body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))
    return {"data": rows, "total": len(rows)}


@router.get("/column-config/{listing_key:path}", response_model=UserListColumnConfigResponse)
def get_list_column_config(
    listing_key: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing_key = (listing_key or "").strip()
    if not _can_view_listing_key(db, current_user["id"], listing_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    row = (
        db.query(UserListColumnConfig)
        .filter(
            UserListColumnConfig.user_id == current_user["id"],
            UserListColumnConfig.listing_key == listing_key,
        )
        .first()
    )
    cfg = _config_dict(getattr(row, "config", None)) if row else None
    return UserListColumnConfigResponse(listing_key=listing_key, config=cfg)


@router.put("/column-config/{listing_key:path}", response_model=UserListColumnConfigResponse)
def upsert_list_column_config(
    listing_key: str,
    body: UserListColumnConfigPayload,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing_key = (listing_key or "").strip()
    if not _can_view_listing_key(db, current_user["id"], listing_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    try:
        data = body.model_dump(exclude_none=True)
        row = (
            db.query(UserListColumnConfig)
            .filter(
                UserListColumnConfig.user_id == current_user["id"],
                UserListColumnConfig.listing_key == listing_key,
            )
            .first()
        )
        if row:
            setattr(row, "config", data)
        else:
            row = UserListColumnConfig(user_id=current_user["id"], listing_key=listing_key, config=data)
            db.add(row)
        db.commit()
        db.refresh(row)
        return UserListColumnConfigResponse(
            listing_key=listing_key,
            config=_config_dict(getattr(row, "config", None)),
        )
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.delete("/column-config/{listing_key:path}", status_code=status.HTTP_204_NO_CONTENT)
def reset_list_column_config(
    listing_key: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing_key = (listing_key or "").strip()
    if not _can_view_listing_key(db, current_user["id"], listing_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    try:
        row = (
            db.query(UserListColumnConfig)
            .filter(
                UserListColumnConfig.user_id == current_user["id"],
                UserListColumnConfig.listing_key == listing_key,
            )
            .first()
        )
        if row:
            db.delete(row)
            db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
