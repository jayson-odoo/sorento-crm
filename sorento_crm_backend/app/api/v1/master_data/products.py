"""Products API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.product_service import ProductService
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse, BulkImportProductsRequest
from app.schemas.common import ListResponse, ErrorResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[ProductResponse])
async def get_products(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    brand_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    item_type: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get products with pagination, filtering, and sorting."""
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
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    current_user: dict = Depends(get_current_user),
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


@router.post("/bulk-import", status_code=status.HTTP_202_ACCEPTED)
async def bulk_import_products(
    import_data: BulkImportProductsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk import products from Excel data (queued). Columns: Item Code, Description, Desc 2, Item Group (→ category), Item Brand (→ brand), Price, Is Active (T/F). Returns job ID for tracking."""
    try:
        from app.services.job_service import JobService
        from app.services.queue_service import enqueue_job
        from app.tasks.import_tasks import process_product_import

        job_service = JobService(db)
        job = job_service.create_job(
            job_type='product_import',
            user_id=current_user["id"],
            metadata={'total_rows': len(import_data.products)},
        )
        job.total_rows = len(import_data.products)
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
