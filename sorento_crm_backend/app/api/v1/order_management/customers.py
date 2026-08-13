"""Customers API routes."""
from fastapi import APIRouter, Depends, File, Query, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user, require_permission
from app.services.job_service import JobService
from app.services.order_service import CustomerService
from app.services.queue_service import enqueue_job
from app.schemas.order import CustomerCreate, CustomerUpdate, CustomerResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[CustomerResponse])
async def get_customers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get customers with pagination, search, and sorting."""
    try:
        service = CustomerService(db)
        result = service.list_customers(
            page=page,
            limit=limit,
            query=query,
            sort_field=sort or "created_at",
            sort_dir=dir or "desc",
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/neighbours")
async def get_customer_neighbours(
    id: str = Query(..., description="Customer id to resolve neighbours for"),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Prev/next neighbours of a customer within the active filtered+sorted list set.

    Accepts the same filter/sort/search params as the list GET (page/limit are
    irrelevant and ignored). Returns ``{total, index, prev_id, next_id}`` with the
    1-based ``index`` and circular wrap-around neighbours. If the record is not in
    the filtered set, falls back to the unfiltered, default-sorted set.
    """
    try:
        service = CustomerService(db)
        return service.neighbours(
            customer_id=id,
            query=query,
            sort_field=sort or "created_at",
            sort_dir=dir or "desc",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
async def import_customers(
    file: UploadFile = File(..., description="Excel file: customer (debtor) listing"),
    validate_only: bool = Query(
        False, description="If true, read the file and report what it would do. Writes nothing."
    ),
    current_user: dict = Depends(require_permission("order_management.customers.import")),
    db: Session = Depends(get_db),
):
    """Queue a customer import. Use validate_only=true to test without importing."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls", ".xlsm")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Excel file (.xlsx, .xls or .xlsm) required",
        )
    file_data = await file.read()
    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty"
        )
    # Retain the ORIGINAL bytes (pre-macro-strip) for source-file tracing.
    source_bytes, source_name, source_ctype = file_data, file.filename, file.content_type
    from app.services.excel_macro_stripper import maybe_strip
    file_data, cleaned_name = maybe_strip(file_data, file.filename or "unknown.xlsx")

    from app.services.job_service import active_company_id_from_scope

    company_id = active_company_id_from_scope(db)
    if not company_id:
        # Customers are an owned table (ADR 0007), so "whose customer book is this?" has
        # no answer without a single company. Refused for BOTH modes, not just the queue:
        # 884 code+name pairs are held by both Sorento and Mocha, so a dry run reading
        # across companies answers "884 unchanged" about the wrong book and then Confirm
        # 400s anyway. A preview that cannot be trusted is worse than no preview.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select a single company before importing customers.",
        )

    if validate_only:
        from app.models.base import get_company_scope
        from app.tasks.import_tasks import validate_customer_import

        # Preview at the SAME company scope the import will run at: which customers we
        # already hold is what decides create vs update.
        result = validate_customer_import(file_data, company_scope=get_company_scope(db))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "valid": result["valid"],
                "errors": result["errors"],
                "warnings": result.get("warnings", []),
                "summary": result.get("summary"),
            },
        )

    from app.tasks.import_tasks import process_customer_import
    job_service = JobService(db)
    job = job_service.create_job(
        job_type="customer_import",
        user_id=current_user["id"],
        filename=cleaned_name,
        company_id=company_id,
    )
    from app.services.import_source_store import store_import_source_file
    store_import_source_file(job, source_bytes, source_name, source_ctype)
    db.commit()
    rq_job = enqueue_job(
        process_customer_import,
        str(job.id),
        file_data,
        cleaned_name,
        current_user["id"],
        queue_name="imports",
        job_timeout=3600,
        job_id=str(job.job_id),  # pre-assign RQ id = DB job_id; see update_job_with_rq_id
    )
    job_service.update_job_with_rq_id(job, rq_job.id)
    return {"message": "Customer import queued.", "job_id": job.job_id, "id": str(job.id)}


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single customer by ID."""
    try:
        validate_uuid_path(customer_id, resource="Customer")
        service = CustomerService(db)
        customer = service.get_customer(customer_id)
        return customer
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new customer."""
    try:
        service = CustomerService(db)
        customer = service.create_customer(customer_data)
        return customer
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    customer_data: CustomerUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a customer."""
    try:
        validate_uuid_path(customer_id, resource="Customer")
        service = CustomerService(db)
        customer = service.update_customer(customer_id, customer_data)
        return customer
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{customer_id}", status_code=status.HTTP_200_OK)
async def delete_customer(
    customer_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a customer."""
    try:
        validate_uuid_path(customer_id, resource="Customer")
        service = CustomerService(db)
        # Implement delete logic
        return {"message": "Customer deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
