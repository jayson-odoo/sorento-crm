"""Build capability documents for MCP Tool-RAG indexing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import sys
from typing import Any


@dataclass(frozen=True)
class CapabilityDoc:
    source_id: str
    source_key: str
    title: str
    body_text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ToolDefinition:
    tool_name: str
    description: str
    typical_user_questions: list[str]
    category: str | None = None
    implementation_status: str = "planned"
    required_fields: list[str] | None = None
    optional_fields: list[str] | None = None


def _extract_category(tool_name: str) -> str:
    parts = tool_name.split("_")
    if len(parts) >= 3 and parts[0] == "crm":
        return parts[1]
    return "general"


def _question_templates(name: str, description: str) -> list[str]:
    base = name.replace("crm_", "").replace("_", " ")
    return [
        f"When should I use {name}?",
        f"Which tool helps me to {base}?",
        description[:180],
    ]


def _parse_required_query_hints(description: str) -> list[str]:
    lowered = description.lower()
    hints: list[str] = []
    if "required pattern" in lowered and "promotion_id" in lowered:
        hints.append("promotion_id")
    return hints


def _definitions_path_from_repo() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "sorento_crm_backend" / "app" / "data" / "tool_rag_definitions.json"


def load_tool_definitions(definitions_file: str | None = None) -> list[ToolDefinition]:
    if not definitions_file:
        return []
    path = Path(definitions_file)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    defs: list[ToolDefinition] = []
    for row in payload:
        tool_name = str(row.get("tool_name", "")).strip()
        description = str(row.get("description", "")).strip()
        questions = [str(q).strip() for q in (row.get("typical_user_questions") or []) if str(q).strip()]
        if not tool_name or not description or not questions:
            continue
        defs.append(
            ToolDefinition(
                tool_name=tool_name,
                description=description,
                typical_user_questions=questions,
                category=str(row.get("category")) if row.get("category") else None,
                implementation_status=str(row.get("implementation_status") or "planned"),
                required_fields=[str(x).strip() for x in (row.get("required_fields") or []) if str(x).strip()] or None,
                optional_fields=[str(x).strip() for x in (row.get("optional_fields") or []) if str(x).strip()] or None,
            )
        )
    return defs


def _load_catalog_specs():
    # Ensure sibling package is importable when executing from backend app path.
    repo_root = Path(__file__).resolve().parents[3]
    mcp_root = repo_root / "sorento_crm_mcp"
    if str(mcp_root) not in sys.path:
        sys.path.append(str(mcp_root))
    from sorento_crm_mcp.catalog import CATALOG  # type: ignore

    return CATALOG


def build_capability_documents(include_planned: bool = True, definitions_file: str | None = None) -> list[CapabilityDoc]:
    docs: list[CapabilityDoc] = []
    from_file = load_tool_definitions(definitions_file)
    if from_file:
        for td in from_file:
            category = td.category or _extract_category(td.tool_name)
            body_text = (
                f"Tool Name: {td.tool_name}\n"
                f"Category: {category}\n"
                f"Description: {td.description}\n"
                f"Required Fields: {', '.join(td.required_fields or []) if td.required_fields else 'none'}\n"
                f"Optional Fields: {', '.join(td.optional_fields or []) if td.optional_fields else 'none'}\n"
            )
            docs.append(
                CapabilityDoc(
                    source_id=f"{td.implementation_status}::{td.tool_name}",
                    source_key=td.tool_name,
                    title=td.tool_name,
                    body_text=body_text,
                    metadata={
                        "tool_name": td.tool_name,
                        "category": category,
                        "required_params": [],
                        "optional_params": [],
                        "required_fields": td.required_fields or [],
                        "optional_fields": td.optional_fields or [],
                        "aliases": [td.tool_name.replace("_", " ")],
                        "typical_user_questions": td.typical_user_questions,
                        "implementation_status": td.implementation_status,
                        "tool_type": "tool_rag_definition",
                    },
                )
            )
        return docs

    for spec in _load_catalog_specs():
        required_params = [*spec.path_params]
        optional_params = [*spec.query_params]
        required_params.extend(_parse_required_query_hints(spec.description))
        category = _extract_category(spec.name)
        user_facing_description, user_questions = _prompt_aligned_tool_summary(spec.name, spec.path, required_params, optional_params)
        body_text = (
            f"Tool Name: {spec.name}\n"
            f"Category: {category}\n"
            f"Description: {user_facing_description}\n"
            f"Path: {spec.path}\n"
            f"Required Params: {', '.join(required_params) if required_params else 'none'}\n"
            f"Optional Params: {', '.join(optional_params) if optional_params else 'none'}\n"
        )
        docs.append(
            CapabilityDoc(
                source_id=f"implemented::{spec.name}",
                source_key=spec.name,
                title=spec.name,
                body_text=body_text,
                metadata={
                    "tool_name": spec.name,
                    "category": category,
                    "required_params": required_params,
                    "optional_params": optional_params,
                    "aliases": [re.sub(r"^crm_", "", spec.name).replace("_", " ")],
                    "typical_user_questions": user_questions,
                    "implementation_status": "implemented",
                    "tool_type": "enquiry",
                    "api_path": spec.path,
                },
            )
        )

    if include_planned:
        docs.extend(_planned_capabilities())
    return docs


def _prompt_aligned_tool_summary(
    tool_name: str,
    path: str,
    required_params: list[str],
    optional_params: list[str],
) -> tuple[str, list[str]]:
    # Correlate descriptions to legacy next_agents intent language:
    # product/promotion/attachment/stock/lead_time/incoming/order/forms/workflow.
    if "products_get" in tool_name:
        return (
            "Fetch full product details by product_id for product information requests, including code, name, description, brand/category relations, and pricing fields returned by the API.",
            [
                "Show me details for this product id",
                "I need full product information for this item",
                "Open this product record and show all fields",
                "Can you retrieve this product profile?",
                "Get product details for this SKU id mapping",
            ],
        )
    if "products_list" in tool_name:
        return (
            "Search and list products using query/category/brand/status filters for catalog discovery questions such as bathtubs, sinks, faucets, toilets, furniture, and accessories.",
            [
                "Do you sell matte black kitchen sinks?",
                "List products matching this keyword",
                "Show available products in this category",
                "Find products by brand and status",
                "Search catalog items for this product type",
            ],
        )
    if "promotions_list" in tool_name or "promotions_get" in tool_name or "promotion_products" in tool_name:
        return (
            "Retrieve promotion details and linked product lines for promo-code or product-promotion enquiries, including active windows and promo item coverage.",
            [
                "What is included in this promo code?",
                "Show active promotions for this product",
                "List products under this promotion",
                "Get promotion details and dates",
                "Find promo lines for this campaign",
            ],
        )
    if "attachments" in tool_name or "directories" in tool_name:
        return (
            "Retrieve attachment metadata, file references, and linked entities for brochure, flyer, certificate, datasheet, and stock-list document requests.",
            [
                "Can I get the brochure for this product?",
                "Show attachments for this promotion",
                "Find the technical datasheet for this item",
                "Retrieve the latest stock list document",
                "Get attachment metadata for this file",
            ],
        )
    if "stock_balance" in tool_name or "stock_ledger" in tool_name or "stock_batches" in tool_name or "stock_alerts" in tool_name:
        return (
            "Return stock availability and inventory movement data by product and warehouse for stock-balance and sufficiency checks.",
            [
                "Do you have stock for this SKU?",
                "How many units are available by warehouse?",
                "Check inventory balance for this product",
                "Show stock movement for this item",
                "Find current stock quantity for this product",
            ],
        )
    if "packing_lists" in tool_name or "spo_allocations" in tool_name or "grn" in tool_name or "picking_lines" in tool_name:
        return (
            "Retrieve inbound shipment, SPO allocation, and GRN context for incoming-stock questions such as outstanding quantity, ETA, and shipment references.",
            [
                "Any incoming stock for this product?",
                "Track this inbound shipment number",
                "Show SPO allocation for this SKU",
                "What is the GRN status for this shipment?",
                "List inbound lines still pending receipt",
            ],
        )
    if "orders_" in tool_name:
        return (
            "Retrieve order and order-product relationships for delivery status, customer order listing, and product-in-order queries.",
            [
                "Track status for this order number",
                "List customer orders and statuses",
                "Find orders containing this product",
                "Show recent orders for this account",
                "Get order details for this order id",
            ],
        )
    if "forms_management_forms" in tool_name or "workflow_forms_definitions" in tool_name or "workflow_forms_submissions" in tool_name:
        return (
            "Retrieve form definitions and submission states for marketing/purchase/sponsorship workflow discovery and follow-up checks.",
            [
                "Show active forms I can submit",
                "Search forms for sponsorship",
                "Get this workflow form definition",
                "List submissions for this form",
                "What transitions are allowed for this submission?",
            ],
        )
    if "sla_" in tool_name:
        return (
            "Retrieve SLA policy and conversation-tracking metrics for escalation and SLA status monitoring.",
            [
                "Show SLA tracking for this conversation",
                "List active SLA policies",
                "Get SLA event logs for this tracking id",
                "Open SLA dashboard metrics",
                "Retrieve SLA policy tiers",
            ],
        )
    base_required = ", ".join(required_params) if required_params else "none"
    base_optional = ", ".join(optional_params) if optional_params else "none"
    return (
        f"Call {tool_name} to fetch API data from {path} with required params [{base_required}] and optional params [{base_optional}] for live CRM enquiries.",
        [
            f"Run {tool_name} for this request",
            "Fetch live CRM data for my query",
            "Get the relevant records from this endpoint",
            "Retrieve latest data for this context",
            "Load records that match these filters",
        ],
    )


def _planned_capabilities() -> list[CapabilityDoc]:
    planned = [
        {
            "tool_name": "create_purchase_request",
            "category": "workflow",
            "required_params": ["contact_id", "line_items"],
            "optional_params": ["remarks", "requested_by_name"],
            "tool_type": "form_submission",
            "description": "Create a purchase request and return request number and workflow state.",
        },
        {
            "tool_name": "update_rejected_purchase_request",
            "category": "workflow",
            "required_params": ["request_id", "contact_id"],
            "optional_params": ["line_items", "remarks"],
            "tool_type": "form_submission",
            "description": "Update a rejected purchase request before re-submission.",
        },
        {
            "tool_name": "create_stock_inquiry",
            "category": "workflow",
            "required_params": ["contact_id", "project_name", "line_items"],
            "optional_params": ["notes"],
            "tool_type": "form_submission",
            "description": "Create stock inquiry form with requested products and quantities.",
        },
        {
            "tool_name": "update_rejected_stock_inquiry",
            "category": "workflow",
            "required_params": ["stock_inquiry_id", "contact_id"],
            "optional_params": ["line_items", "notes"],
            "tool_type": "form_submission",
            "description": "Revise a rejected stock inquiry and submit for approval.",
        },
        {
            "tool_name": "create_complaint",
            "category": "service",
            "required_params": ["order_id", "complaint_type", "description"],
            "optional_params": ["line_items", "attachments"],
            "tool_type": "form_submission",
            "description": "Create complaint case from delivery/order context.",
        },
        {
            "tool_name": "submit_workflow_transition",
            "category": "workflow",
            "required_params": ["submission_id", "transition_code"],
            "optional_params": ["comment"],
            "tool_type": "workflow_action",
            "description": "Execute workflow transition chosen from allowed transitions.",
        },
    ]
    docs: list[CapabilityDoc] = []
    for row in planned:
        tool_name = row["tool_name"]
        docs.append(
            CapabilityDoc(
                source_id=f"planned::{tool_name}",
                source_key=tool_name,
                title=tool_name,
                body_text=(
                    f"Tool Name: {tool_name}\n"
                    f"Category: {row['category']}\n"
                    f"Description: {row['description']}\n"
                    f"Required Params: {', '.join(row['required_params'])}\n"
                    f"Optional Params: {', '.join(row['optional_params']) if row['optional_params'] else 'none'}\n"
                    "When To Use: Use when user asks to create or update form-based workflows.\n"
                    "When Not To Use: Do not use for read-only enquiries.\n"
                ),
                metadata={
                    **row,
                    "aliases": [tool_name.replace("_", " ")],
                    "typical_user_questions": [
                        f"Can you {tool_name.replace('_', ' ')} for me?",
                        f"I need help to {tool_name.replace('_', ' ')}",
                    ],
                    "implementation_status": "planned",
                },
            )
        )
    return docs
