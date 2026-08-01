"""Execute advanced list search using shared filter compiler + existing list services."""
from sqlalchemy.orm import Session

from app.schemas.list_query import ListSearchRequest
from app.services.list_query_metadata_service import ListQueryMetadataService
from app.services.marketing_service import PromotionService
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.services.procurement_service import SupplierService
from app.services.query.filter_compiler import compile_optional_filter
from app.services.list_query_registry import require_adapter
from app.services.workflow_forms_service import WorkflowFormsService
from app.services.workflow_submission_dynamic_list_query import (
    filter_uses_dynamic_fields,
    merge_submission_field_maps,
)


class ListQuerySearchService:
    def __init__(self, db: Session):
        self.db = db
        self.meta = ListQueryMetadataService(db)

    def search(self, req: ListSearchRequest) -> dict:
        require_adapter(req.resource)
        resource = self.meta.get_resource(req.resource)
        if not resource:
            raise ValueError(f"Unknown resource: {req.resource}")

        field_by_key = self.meta.fields_by_key(req.resource)
        if req.resource == "workflow_form_submissions":
            wid = (req.workflow_form_definition_id or "").strip() or None
            if req.filter and filter_uses_dynamic_fields(req.filter) and not wid:
                raise ValueError(
                    "Scope to one workflow form (definition) to filter by form fields."
                )
            if wid:
                field_by_key = merge_submission_field_maps(field_by_key, wid, self.db)
        clause = compile_optional_filter(req.resource, req.filter, field_by_key)

        sort_field = req.sort or ("created_at" if req.resource != "suppliers" else "created_at")
        sort_dir = req.dir or "asc"

        handlers = {
            "orders": self._search_orders,
            "products": self._search_products,
            "suppliers": self._search_suppliers,
            "promotions": self._search_promotions,
            "workflow_form_definitions": self._search_workflow_form_definitions,
            "workflow_form_submissions": self._search_workflow_form_submissions,
        }
        handler = handlers.get(req.resource)
        if not handler:
            raise ValueError(f"Unsupported resource: {req.resource}")
        return handler(req, clause, sort_field, sort_dir)

    def _search_orders(self, req: ListSearchRequest, clause, sort_field: str, sort_dir: str) -> dict:
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

    def _search_products(self, req: ListSearchRequest, clause, sort_field: str, sort_dir: str) -> dict:
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

    def _search_suppliers(self, req: ListSearchRequest, clause, sort_field: str, sort_dir: str) -> dict:
        svc = SupplierService(self.db)
        return svc.list_suppliers(
            page=req.page,
            limit=req.limit,
            query=req.quick_search,
            sort_field=sort_field,
            sort_dir=sort_dir,
            advanced_filter_clause=clause,
        )

    def _search_promotions(self, req: ListSearchRequest, clause, sort_field: str, sort_dir: str) -> dict:
        svc = PromotionService(self.db)
        return svc.list_promotions(
            page=req.page,
            limit=req.limit,
            query=req.quick_search,
            status=req.promotion_status,
            user_type=req.promotion_access_level,
            sort_field=sort_field or "created_at",
            sort_dir=sort_dir or "desc",
            advanced_filter_clause=clause,
        )

    def _search_workflow_form_definitions(self, req: ListSearchRequest, clause, sort_field: str, sort_dir: str) -> dict:
        svc = WorkflowFormsService(self.db)
        raw = svc.list_definitions(
            page=req.page,
            limit=req.limit,
            query=req.quick_search,
            is_active=req.workflow_definition_is_active,
            sort_field=sort_field or "updated_at",
            sort_dir=sort_dir or "desc",
            advanced_filter_clause=clause,
        )
        return {
            "data": raw["data"],
            "pagination": {"total": raw["total"], "page": raw["page"], "limit": raw["limit"]},
            "empty": raw["total"] == 0,
        }

    def _search_workflow_form_submissions(self, req: ListSearchRequest, clause, sort_field: str, sort_dir: str) -> dict:
        svc = WorkflowFormsService(self.db)
        wf_def_id = (req.workflow_form_definition_id or "").strip() or None
        status_key = (req.workflow_submission_status_key or "").strip() or None
        raw = svc.list_submissions(
            page=req.page,
            limit=req.limit,
            definition_id=wf_def_id,
            status_key=status_key,
            query=req.quick_search,
            sort_field=sort_field or "updated_at",
            sort_dir=sort_dir or "desc",
            advanced_filter_clause=clause,
        )
        return {
            "data": raw["data"],
            "pagination": {"total": raw["total"], "page": raw["page"], "limit": raw["limit"]},
            "empty": raw["total"] == 0,
        }
