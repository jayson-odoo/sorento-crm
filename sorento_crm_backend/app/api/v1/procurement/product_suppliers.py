"""Product suppliers API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user, require_permission
from app.services.procurement_service import ProductSupplierService
from app.schemas.procurement import ProductSupplierCreate, ProductSupplierUpdate, ProductSupplierResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

# #1288 AC-S2-14: the CRUD routes get their existing permission slugs enforced (plan
# section 10) - a migration sweep grants them wherever a role could already write a link.
PS_VIEW_PERM = "procurement.product_suppliers.view"
PS_ADD_PERM = "procurement.product_suppliers.add"
PS_EDIT_PERM = "procurement.product_suppliers.edit"
PS_DELETE_PERM = "procurement.product_suppliers.delete"

router = APIRouter()


@router.get("/", response_model=ListResponse[ProductSupplierResponse])
async def get_product_suppliers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    product_id: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission(PS_VIEW_PERM)),
    db: Session = Depends(get_db)
):
    """Get product suppliers with pagination and filtering."""
    try:
        service = ProductSupplierService(db)
        result = service.list_product_suppliers(
            page=page,
            limit=limit,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
            product_id=product_id,
            supplier_id=supplier_id
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{product_supplier_id}", response_model=ProductSupplierResponse)
async def get_product_supplier(
    product_supplier_id: str,
    current_user: dict = Depends(require_permission(PS_VIEW_PERM)),
    db: Session = Depends(get_db)
):
    """Get a single product supplier by ID."""
    try:
        validate_uuid_path(product_supplier_id, resource="Product Supplier")
        service = ProductSupplierService(db)
        product_supplier = service.get_product_supplier(product_supplier_id)
        return product_supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ProductSupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_product_supplier(
    product_supplier_data: ProductSupplierCreate,
    current_user: dict = Depends(require_permission(PS_ADD_PERM)),
    db: Session = Depends(get_db)
):
    """Create a new product supplier relationship."""
    try:
        service = ProductSupplierService(db)
        product_supplier = service.create_product_supplier(product_supplier_data)
        return product_supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{product_supplier_id}", response_model=ProductSupplierResponse)
async def update_product_supplier(
    product_supplier_id: str,
    product_supplier_data: ProductSupplierUpdate,
    current_user: dict = Depends(require_permission(PS_EDIT_PERM)),
    db: Session = Depends(get_db)
):
    """Update a product supplier relationship."""
    try:
        validate_uuid_path(product_supplier_id, resource="Product Supplier")
        service = ProductSupplierService(db)
        product_supplier = service.update_product_supplier(product_supplier_id, product_supplier_data)
        return product_supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{product_supplier_id}", status_code=status.HTTP_200_OK)
async def delete_product_supplier(
    product_supplier_id: str,
    current_user: dict = Depends(require_permission(PS_DELETE_PERM)),
    db: Session = Depends(get_db)
):
    """Delete a product supplier relationship."""
    try:
        validate_uuid_path(product_supplier_id, resource="Product Supplier")
        service = ProductSupplierService(db)
        service.delete_product_supplier(product_supplier_id)
        return {"message": "Product supplier deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/product/{product_id}")
async def get_product_suppliers_by_product(
    product_id: str,
    current_user: dict = Depends(require_permission(PS_VIEW_PERM)),
    db: Session = Depends(get_db)
):
    """Every current sourcing link for a product, "their code" (S4) and its cost lists
    (#1288, AC-CL-08) alongside each one.

    A bare list, NOT `{"data": [...]}` - this route predates the cost-price lane and two
    FE components (`ProductSuppliersTab.tsx`, `ProductSuppliersSection.tsx`) already read
    the response as an array of `ProductSupplier`; only a `costs` field is new here.
    """
    try:
        from app.services.procurement.supplier_cost_service import costs_for_link

        service = ProductSupplierService(db)
        rows = service.list_suppliers_for_product(product_id)
        data = []
        for row in rows:
            data.append({
                "id": str(row.id),
                "product_id": str(row.product_id),
                "supplier_id": str(row.supplier_id),
                "standard_lead_time_days": row.standard_lead_time_days,
                "moq": row.moq,
                "order_multiple": row.order_multiple,
                "unit_cost": float(row.unit_cost) if row.unit_cost is not None else None,
                "currency": row.currency,
                "is_primary_supplier": row.is_primary_supplier,
                "lead_time_variability_days": (
                    float(row.lead_time_variability_days)
                    if row.lead_time_variability_days is not None else None
                ),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "supplier_item_code": getattr(row, "supplier_item_code", None),
                "product": (
                    {
                        "id": str(row.product.id),
                        "product_code": row.product.product_code,
                        "product_name": row.product.product_name,
                    }
                    if row.product else None
                ),
                "supplier": (
                    {
                        "id": str(row.supplier.id),
                        "supplier_code": row.supplier.supplier_code,
                        "supplier_name": row.supplier.supplier_name,
                    }
                    if row.supplier else None
                ),
                "costs": costs_for_link(db, row.id),
            })
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# --------------------------------------------------------------------------------- costs
# Hand edits to a link's dated cost lists (#1288, AC-CL-06, contract 2.3). Not routed
# through a change set - only Sorento staff holding `product_suppliers.edit` reach this.


@router.post("/{link_id}/costs", status_code=status.HTTP_201_CREATED)
async def create_product_supplier_cost(
    link_id: str,
    body: dict,
    current_user: dict = Depends(require_permission(PS_EDIT_PERM)),
    db: Session = Depends(get_db),
):
    from app.services.procurement.supplier_cost_service import create_cost

    return create_cost(db, link_id, body, current_user)


@router.put("/{link_id}/costs/{cost_id}")
async def update_product_supplier_cost(
    link_id: str,
    cost_id: str,
    body: dict,
    current_user: dict = Depends(require_permission(PS_EDIT_PERM)),
    db: Session = Depends(get_db),
):
    from app.services.procurement.supplier_cost_service import update_cost

    return update_cost(db, link_id, cost_id, body, current_user)


@router.delete("/{link_id}/costs/{cost_id}")
async def delete_product_supplier_cost(
    link_id: str,
    cost_id: str,
    current_user: dict = Depends(require_permission(PS_EDIT_PERM)),
    db: Session = Depends(get_db),
):
    from app.services.procurement.supplier_cost_service import delete_cost

    delete_cost(db, link_id, cost_id, current_user)
    return {"message": "Cost row deleted"}
