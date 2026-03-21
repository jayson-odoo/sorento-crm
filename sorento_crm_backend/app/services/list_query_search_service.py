"""Execute advanced list search using shared filter compiler + existing list services."""
from sqlalchemy.orm import Session

from app.schemas.list_query import ListSearchRequest
from app.services.list_query_metadata_service import ListQueryMetadataService
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.services.procurement_service import SupplierService
from app.services.query.filter_compiler import compile_optional_filter


class ListQuerySearchService:
    def __init__(self, db: Session):
        self.db = db
        self.meta = ListQueryMetadataService(db)

    def search(self, req: ListSearchRequest) -> dict:
        resource = self.meta.get_resource(req.resource)
        if not resource:
            raise ValueError(f"Unknown resource: {req.resource}")

        field_by_key = self.meta.fields_by_key(req.resource)
        clause = compile_optional_filter(req.resource, req.filter, field_by_key)

        sort_field = req.sort or ("created_at" if req.resource != "suppliers" else "created_at")
        sort_dir = req.dir or "asc"

        if req.resource == "orders":
            svc = OrderService(self.db)
            return svc.list_orders(
                page=req.page,
                limit=req.limit,
                query=req.quick_search,
                customer_id=req.customer_id,
                order_status_id=req.order_status_id,
                has_order_lines=req.has_order_lines,
                sort_field=sort_field,
                sort_dir=sort_dir,
                advanced_filter_clause=clause,
            )
        if req.resource == "products":
            svc = ProductService(self.db)
            return svc.list_products(
                page=req.page,
                limit=req.limit,
                query=req.quick_search,
                category_id=req.category_id,
                brand_id=req.brand_id,
                status=req.product_status,
                price_min=req.price_min,
                price_max=req.price_max,
                item_type=req.item_type,
                sort_field=sort_field,
                sort_dir=sort_dir,
                advanced_filter_clause=clause,
            )
        if req.resource == "suppliers":
            svc = SupplierService(self.db)
            return svc.list_suppliers(
                page=req.page,
                limit=req.limit,
                query=req.quick_search,
                sort_field=sort_field,
                sort_dir=sort_dir,
                advanced_filter_clause=clause,
            )
        raise ValueError(f"Unsupported resource: {req.resource}")
