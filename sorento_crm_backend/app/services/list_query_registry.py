"""Central registry for list-query resources and shared metadata."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional

from app.models.marketing import Promotion
from app.models.order import Order
from app.models.product import Product
from app.models.procurement import Supplier
from app.models.tickets import Ticket
from app.models.workflow_forms import WorkflowFormDefinition, WorkflowSubmission
from app.schemas.marketing import PromotionResponse
from app.schemas.order import OrderResponse
from app.schemas.product import ProductResponse
from app.schemas.procurement import SupplierResponse
from app.schemas.tickets import TicketResponse
from app.schemas.workflow_forms import WorkflowFormDefinitionOut, WorkflowSubmissionOut


Serializer = Callable[[Iterable[Any]], list[Any]]


def _serialize_passthrough(rows: Iterable[Any]) -> list[Any]:
    return list(rows)


def _serialize_orders(rows: Iterable[Any]) -> list[Any]:
    return [OrderResponse.model_validate(x) for x in rows]


def _serialize_products(rows: Iterable[Any]) -> list[Any]:
    return [ProductResponse.model_validate(x) for x in rows]


def _serialize_suppliers(rows: Iterable[Any]) -> list[Any]:
    return [SupplierResponse.model_validate(x) for x in rows]


def _serialize_promotions(rows: Iterable[Any]) -> list[Any]:
    return [PromotionResponse.model_validate(x) for x in rows]


def _serialize_workflow_definitions(rows: Iterable[Any]) -> list[Any]:
    return [WorkflowFormDefinitionOut.model_validate(x) for x in rows]


def _serialize_workflow_submissions(rows: Iterable[Any]) -> list[Any]:
    return [WorkflowSubmissionOut.model_validate(x) for x in rows]


def _serialize_tickets(rows: Iterable[Any]) -> list[Any]:
    return [TicketResponse.model_validate(x) for x in rows]


@dataclass(frozen=True)
class ListQueryResourceAdapter:
    resource_key: str
    view_slug: str
    export_slug: str
    serializer: Serializer
    model: Optional[type[Any]] = None
    compile_prefix: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None


ADAPTERS: Dict[str, ListQueryResourceAdapter] = {
    "orders": ListQueryResourceAdapter(
        resource_key="orders",
        view_slug="order_management.orders.view",
        export_slug="order_management.orders.export",
        serializer=_serialize_orders,
        model=Order,
        compile_prefix="order",
        display_name="Orders",
        description="Order list filter/export metadata",
    ),
    "products": ListQueryResourceAdapter(
        resource_key="products",
        view_slug="master_data.products.view",
        export_slug="master_data.products.export",
        serializer=_serialize_products,
        model=Product,
        compile_prefix="product",
        display_name="Products",
        description="Product list filter/export metadata",
    ),
    "suppliers": ListQueryResourceAdapter(
        resource_key="suppliers",
        view_slug="procurement.suppliers.view",
        export_slug="procurement.suppliers.export",
        serializer=_serialize_suppliers,
        model=Supplier,
        compile_prefix="supplier",
        display_name="Suppliers",
        description="Supplier list filter/export metadata",
    ),
    "promotions": ListQueryResourceAdapter(
        resource_key="promotions",
        view_slug="marketing.promotions.view",
        # No dedicated export slug in current permission seed; keep same as view for now.
        export_slug="marketing.promotions.view",
        serializer=_serialize_promotions,
        model=Promotion,
        compile_prefix="promotion",
        display_name="Promotions",
        description="Promotion list filter/export metadata",
    ),
    "workflow_form_definitions": ListQueryResourceAdapter(
        resource_key="workflow_form_definitions",
        view_slug="workflow_forms.definitions.view",
        export_slug="workflow_forms.definitions.export",
        serializer=_serialize_workflow_definitions,
        model=WorkflowFormDefinition,
        compile_prefix="def",
        display_name="Workflow Form Definitions",
        description="Workflow form definition list-query metadata",
    ),
    "workflow_form_submissions": ListQueryResourceAdapter(
        resource_key="workflow_form_submissions",
        view_slug="workflow_forms.submissions.view",
        export_slug="workflow_forms.submissions.export",
        serializer=_serialize_workflow_submissions,
        model=WorkflowSubmission,
        compile_prefix="sub",
        display_name="Workflow Form Submissions",
        description="Workflow form submission list-query metadata",
    ),
    "tickets": ListQueryResourceAdapter(
        resource_key="tickets",
        view_slug="tickets.tickets.view",
        export_slug="tickets.tickets.export",
        serializer=_serialize_tickets,
        model=Ticket,
        compile_prefix="ticket",
        display_name="Tickets",
        description="Ticket list filter/export metadata",
    ),
}


def get_adapter(resource_key: str) -> Optional[ListQueryResourceAdapter]:
    return ADAPTERS.get((resource_key or "").strip())


def require_adapter(resource_key: str) -> ListQueryResourceAdapter:
    adapter = get_adapter(resource_key)
    if not adapter:
        raise ValueError(f"Unsupported resource: {resource_key}")
    return adapter


def list_registered_resource_keys() -> list[str]:
    return list(ADAPTERS.keys())
