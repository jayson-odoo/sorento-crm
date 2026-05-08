"""Per-entity field registry for attachment field linkage.

An attachment can be tagged at upload time with an `entity_type` (the table the
document is meant to describe) and a list of `field_keys` (the columns of that
table the document answers). When the attachment is later linked to a specific
row via the existing link APIs, the link service fans the template out into
``attachment_field_links`` rows so the AI agent and the UI can surface the doc
inline next to the answered field.

This module is the single source of truth for:

* The list of supported entity types.
* The field keys allowed under each entity type, plus their human label, value
  kind, unit, group key (composite fields like Dimensions L×W×H), and a
  unit-canonicalization note that is fed to the LLM in AI-extract prompts.

Both the registry endpoint (``GET /api/v1/master-data/field-linkage-schema``)
and every link API import from here so the FE picker, the n8n payload
validator, and the AI-extract prompt stay aligned.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


FieldKind = Literal["text", "number", "lookup", "fk", "date"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: FieldKind = "text"
    unit: str | None = None
    group_key: str | None = None
    extract_note: str | None = None


_PRODUCT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="weight",
        label="Weight",
        kind="number",
        unit="kg",
        extract_note=(
            "Net product weight in kilograms (kg). If the document quotes grams, "
            "convert to kg (e.g. 850 g → 0.85). Omit if the document only quotes "
            "carton/gross weight."
        ),
    ),
    FieldSpec(
        name="dimensions_length",
        label="Length",
        kind="number",
        unit="mm",
        group_key="dimensions",
        extract_note=(
            "Product length in millimetres (mm). Convert from cm/in if necessary "
            "(1 cm = 10 mm, 1 in = 25.4 mm)."
        ),
    ),
    FieldSpec(
        name="dimensions_width",
        label="Width",
        kind="number",
        unit="mm",
        group_key="dimensions",
        extract_note=(
            "Product width in millimetres (mm). Convert from cm/in if necessary."
        ),
    ),
    FieldSpec(
        name="dimensions_height",
        label="Height",
        kind="number",
        unit="mm",
        group_key="dimensions",
        extract_note=(
            "Product height (or depth) in millimetres (mm). Convert from cm/in "
            "if necessary."
        ),
    ),
    FieldSpec(
        name="warranty_months",
        label="Warranty (Months)",
        kind="number",
        unit="months",
        extract_note=(
            "Warranty duration in whole months. Convert from years (1 year = 12 "
            "months)."
        ),
    ),
    FieldSpec(
        name="reorder_level",
        label="Reorder Level",
        kind="number",
        extract_note="Integer threshold below which the product should be reordered.",
    ),
    FieldSpec(
        name="reorder_quantity",
        label="Reorder Quantity",
        kind="number",
        extract_note="Integer quantity to reorder when the level threshold is hit.",
    ),
    FieldSpec(
        name="list_price",
        label="List Price",
        kind="number",
        unit="currency",
        extract_note="Numeric list price in the row's currency (default MYR).",
    ),
    FieldSpec(
        name="cost_price",
        label="Cost Price",
        kind="number",
        unit="currency",
        extract_note="Numeric cost price in the row's currency (default MYR).",
    ),
    FieldSpec(
        name="invoice_price",
        label="Invoice Price",
        kind="number",
        unit="currency",
        extract_note="Numeric invoice price in the row's currency (default MYR).",
    ),
)


_PROMOTION_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(name="description", label="Description", kind="text"),
    FieldSpec(
        name="start_date",
        label="Start Date",
        kind="date",
        extract_note="ISO date YYYY-MM-DD when the promotion begins.",
    ),
    FieldSpec(
        name="end_date",
        label="End Date",
        kind="date",
        extract_note="ISO date YYYY-MM-DD when the promotion ends.",
    ),
)


_PACKING_LIST_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(name="bill_of_lading_number", label="Bill of Lading", kind="text"),
    FieldSpec(name="shipping_container_number", label="Container Number", kind="text"),
    FieldSpec(name="invoice_number", label="Invoice Number", kind="text"),
    FieldSpec(
        name="total_items_shipped",
        label="Total Items Shipped",
        kind="number",
        extract_note="Integer count of items in the shipment.",
    ),
    FieldSpec(
        name="total_cartons",
        label="Total Cartons",
        kind="number",
        extract_note="Integer count of cartons in the shipment.",
    ),
    FieldSpec(name="notes", label="Notes", kind="text"),
)


_FORM_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(name="purpose", label="Purpose", kind="text"),
    FieldSpec(name="version", label="Version", kind="text"),
)


_REGISTRY: dict[str, tuple[FieldSpec, ...]] = {
    "product": _PRODUCT_FIELDS,
    "promotion": _PROMOTION_FIELDS,
    "packing_list": _PACKING_LIST_FIELDS,
    "form": _FORM_FIELDS,
}


SUPPORTED_ENTITY_TYPES: tuple[str, ...] = tuple(_REGISTRY.keys())


def get_field_specs(entity_type: str) -> tuple[FieldSpec, ...]:
    """Return the (immutable) tuple of FieldSpecs for an entity_type.

    Returns an empty tuple for unknown entity_types — callers that want a
    hard error should use :func:`validate_field_keys` first.
    """
    return _REGISTRY.get(entity_type, ())


def get_field_spec(entity_type: str, field_key: str) -> FieldSpec | None:
    for spec in get_field_specs(entity_type):
        if spec.name == field_key:
            return spec
    return None


def field_keys_for(entity_type: str) -> set[str]:
    return {spec.name for spec in get_field_specs(entity_type)}


def validate_field_keys(
    entity_type: str, keys: Iterable[str] | None
) -> tuple[list[str], list[str]]:
    """Split ``keys`` into ``(ok, unknown)`` for the given entity_type.

    An unknown ``entity_type`` returns ``(ok=[], unknown=list(keys))`` — link
    APIs that hit non-registered entity types should treat this as a no-op
    rather than a hard 400.
    """
    if not keys:
        return [], []
    valid = field_keys_for(entity_type)
    ok: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in keys:
        if not raw:
            continue
        key = str(raw).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        if key in valid:
            ok.append(key)
        else:
            unknown.append(key)
    return ok, unknown
