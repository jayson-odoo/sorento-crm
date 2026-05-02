"""Per-form-key field registry for AI extract.

Source of truth for the *complaint* portal form mirrors the FE registry at
``sorento_crm_frontend/app/(auth)/portal/components/SubmissionForm.tsx`` —
keep both in sync; the BE side here is authoritative for the LLM prompt.

Registering a new form is a one-line addition: append a list of
:class:`ExtractFieldSpec` under a new ``form_key``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ExtractFieldKind = Literal[
    "text",
    "textarea",
    "date",
    "number",
    "lookup",
    "fk_product",
    "fk_customer",
    "do_number",
    "multi_text",
]


@dataclass(frozen=True)
class ExtractFieldSpec:
    name: str
    label: str
    kind: ExtractFieldKind = "text"
    table: str | None = None
    column: str | None = None
    set_key: str | None = None
    note: str | None = None
    examples: list[str] = field(default_factory=list)


_PORTAL_COMPLAINT: list[ExtractFieldSpec] = [
    ExtractFieldSpec(
        name="delivery_order_number",
        label="Delivery order number(s)",
        kind="do_number",
        note=(
            "One or more DO numbers. Comma-separate when multiple. Examples: "
            "PS202603-0071, PO2509-013, DO-2025-1234."
        ),
        examples=["PS202603-0071", "PO2509-013"],
    ),
    ExtractFieldSpec(
        name="customer_name",
        label="Customer name",
        kind="fk_customer",
        note="Free text; prefer the registered debtor name as printed on the DO header.",
    ),
    ExtractFieldSpec(name="contact_person", label="Contact person", kind="text"),
    ExtractFieldSpec(name="contact_number", label="Contact number", kind="text"),
    ExtractFieldSpec(
        name="customer_address",
        label="Customer address",
        kind="textarea",
        note="Full delivery / site address as printed on the DO or attached message.",
    ),
    ExtractFieldSpec(
        name="customer_type",
        label="Customer type",
        kind="lookup",
        table="complaints",
        column="customer_type",
        set_key="complaints_customer_type",
    ),
    ExtractFieldSpec(
        name="complaint_date",
        label="Complaint date",
        kind="date",
        note="ISO date YYYY-MM-DD. Use the date the complaint was raised, not the order date.",
    ),
    ExtractFieldSpec(
        name="product_code",
        label="Product code",
        kind="fk_product",
        note=(
            "SKU as it appears in the product master. Examples will be supplied; "
            "follow that pattern. If the document only shows a product name, return "
            "the closest matching code from the examples."
        ),
    ),
    ExtractFieldSpec(
        name="product_type",
        label="Product type",
        kind="text",
        note="Generic category, e.g. bathtub, basin, water closet, kitchen sink, faucet, shower, accessory.",
    ),
    ExtractFieldSpec(
        name="within_warranty",
        label="Within warranty",
        kind="lookup",
        table="complaints",
        column="within_warranty",
        set_key="complaints_within_warranty",
    ),
    ExtractFieldSpec(
        name="defects_discovered",
        label="Defects discovered",
        kind="lookup",
        table="complaints",
        column="defects_discovered",
        set_key="complaints_defects_discovered",
    ),
    ExtractFieldSpec(
        name="complaint_type",
        label="Complaint type",
        kind="lookup",
        table="complaints",
        column="complaint_type",
        set_key="complaints_complaint_type",
    ),
    ExtractFieldSpec(
        name="defect_description",
        label="Defect description",
        kind="textarea",
        note="One- or two-sentence summary of the defect.",
    ),
    ExtractFieldSpec(name="salesperson", label="Salesperson", kind="text"),
    ExtractFieldSpec(name="project_title", label="Project title", kind="text"),
]


FORM_SCHEMAS: dict[str, list[ExtractFieldSpec]] = {
    "portal.complaint": _PORTAL_COMPLAINT,
}


def get_form_schema(form_key: str) -> list[ExtractFieldSpec]:
    """Return the registered schema for ``form_key`` or raise ``KeyError``."""
    schema = FORM_SCHEMAS.get(form_key)
    if schema is None:
        raise KeyError(form_key)
    return schema
