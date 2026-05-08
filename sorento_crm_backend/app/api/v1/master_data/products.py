"""Products API routes."""
import logging
import time
from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.product_service import ProductService
from app.services.attachment_field_link_service import AttachmentFieldLinkService
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse, BulkImportProductsRequest, BulkDeleteProductsRequest
from app.schemas.common import ListResponse, ErrorResponse, ValidateImportResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=ListResponse[ProductResponse])
def get_products(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=5000),
    query: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    brand_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    item_type: Optional[str] = Query(None),
    length_min: Optional[float] = Query(None, description="Minimum dimensions_length in mm."),
    length_max: Optional[float] = Query(None, description="Maximum dimensions_length in mm."),
    width_min: Optional[float] = Query(None, description="Minimum dimensions_width in mm."),
    width_max: Optional[float] = Query(None, description="Maximum dimensions_width in mm."),
    height_min: Optional[float] = Query(None, description="Minimum dimensions_height in mm."),
    height_max: Optional[float] = Query(None, description="Maximum dimensions_height in mm."),
    any_dimension_min: Optional[float] = Query(
        None,
        description="Minimum value (mm) for ANY of length/width/height. Use for axis-agnostic queries like 'dimensions > 300mm'.",
    ),
    any_dimension_max: Optional[float] = Query(
        None,
        description="Maximum value (mm) for ANY of length/width/height.",
    ),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get products with pagination, filtering, and sorting."""
    started = time.perf_counter()
    logger.info(
        "products.get start page=%s limit=%s query=%s category_id=%s brand_id=%s status=%s item_type=%s",
        page,
        limit,
        (query or "")[:80],
        category_id,
        brand_id,
        status,
        item_type,
    )
    try:
        service = ProductService(db)
        result = service.list_products(
            page=page,
            limit=limit,
            query=query,
            category_id=category_id,
            brand_id=brand_id,
            status=status,
            price_min=price_min,
            price_max=price_max,
            item_type=item_type,
            length_min=length_min,
            length_max=length_max,
            width_min=width_min,
            width_max=width_max,
            height_min=height_min,
            height_max=height_max,
            any_dimension_min=any_dimension_min,
            any_dimension_max=any_dimension_max,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        data_len = len(result.get("data") or []) if isinstance(result, dict) else -1
        total = (result.get("pagination") or {}).get("total") if isinstance(result, dict) else None
        logger.info(
            "products.get done elapsed_ms=%.1f rows=%s total=%s",
            elapsed_ms,
            data_len,
            total,
        )
        return result
    except Exception as e:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception("products.get failed elapsed_ms=%.1f error=%s", elapsed_ms, str(e))
        raise handle_internal_error(str(e))


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single product by ID."""
    try:
        service = ProductService(db)
        product = service.get_product(product_id)
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new product."""
    try:
        service = ProductService(db)
        product = service.create_product(product_data, current_user["id"])
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a product."""
    try:
        service = ProductService(db)
        product = service.update_product(product_id, product_data, current_user["id"])
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/bulk-import",
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"description": "Validation only (validate_only=true)", "model": ValidateImportResponse}},
)
async def bulk_import_products(
    import_data: BulkImportProductsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk import products from Excel data (queued). If validate_only=true, run validation only and return errors/warnings (no job)."""
    try:
        if getattr(import_data, "validate_only", False):
            service = ProductService(db)
            result = service.validate_products_import(import_data.products)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "valid": result["valid"],
                    "errors": result["errors"],
                    "warnings": result.get("warnings", []),
                    "summary": result.get("summary"),
                },
            )

        from app.services.job_service import JobService
        from app.services.queue_service import enqueue_job
        from app.tasks.import_tasks import process_product_import

        job_service = JobService(db)
        job = job_service.create_job(
            job_type='product_import',
            user_id=current_user["id"],
            metadata={'total_rows': len(import_data.products)},
        )
        setattr(job, "total_rows", len(import_data.products))
        db.commit()

        rq_job = enqueue_job(
            process_product_import,
            str(job.id),
            import_data.products,
            current_user["id"],
            queue_name='imports',
            job_timeout=3600,
        )
        job_service.update_job_with_rq_id(job, rq_job.id)

        return {
            'job_id': rq_job.id,
            'status': 'queued',
            'message': 'Import job queued successfully',
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_products(
    body: BulkDeleteProductsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk delete products by ID. Body: { ids: string[] }."""
    try:
        service = ProductService(db)
        result = service.bulk_delete_products(body.ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
async def delete_product(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a product."""
    try:
        service = ProductService(db)
        result = service.delete_product(product_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


class _FieldLinksBody(BaseModel):
    field_keys: List[str] = []


@router.get("/{product_id}/attachments/{attachment_id}/field-links", status_code=status.HTTP_200_OK)
async def get_product_attachment_field_links(
    product_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Read the per-row field keys currently linked to one product +
    attachment. Used by the FE Manage-field-links dialog to populate the
    initial selection."""
    try:
        product = ProductService(db).get_product(product_id)
        pid = str(product.get("id") if isinstance(product, dict) else getattr(product, "id"))
        rows = AttachmentFieldLinkService(db).list_for_attachment_and_row(
            attachment_id, "product", pid
        )
        return {
            "product_id": pid,
            "attachment_id": attachment_id,
            "field_keys": sorted({r.field_key for r in rows}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{product_id}/attachments/{attachment_id}/field-links", status_code=status.HTTP_200_OK)
async def set_product_attachment_field_links(
    product_id: str,
    attachment_id: str,
    body: _FieldLinksBody = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Idempotently replace the per-row field-link rows for one product +
    attachment with ``body.field_keys``."""
    try:
        # Resolve product UUID — accept SKU like other endpoints.
        product = ProductService(db).get_product(product_id)
        pid = str(product.get("id") if isinstance(product, dict) else getattr(product, "id"))
        service = AttachmentFieldLinkService(db)
        keys = service.set_links(
            "product",
            pid,
            attachment_id,
            body.field_keys,
            created_by=current_user.get("id") if isinstance(current_user, dict) else None,
        )
        db.commit()
        return {"product_id": pid, "attachment_id": attachment_id, "field_keys": keys}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
