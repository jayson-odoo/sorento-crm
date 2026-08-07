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
        note=(
            "The BUYER / end-customer company being billed — the debtor name as "
            "printed on the DO 'Bill To' / 'Sold To' / 'Customer' line. This is NOT "
            "the supplier/seller issuing the document (e.g. Sorento or our own "
            "company letterhead), NOT the salesperson, and NOT the project/site "
            "name. If a project or site name also appears, put that in "
            "project_title, not here. Return the company name only."
        ),
        examples=["ACME Sdn Bhd", "Tan Construction Sdn Bhd"],
    ),
    ExtractFieldSpec(name="contact_person", label="Contact person", kind="text"),
    ExtractFieldSpec(name="contact_number", label="Contact number", kind="text"),
    ExtractFieldSpec(
        name="customer_address",
        label="Delivery address",
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
            "SKU as it appears in the product master (examples supplied; follow that "
            "pattern). List EACH affected product as a separate entry in the top-level "
            "`products` array with its own quantity — do not pack multiple codes here. "
            "You may leave this top-level field blank when you populate `products`."
        ),
    ),
    ExtractFieldSpec(
        name="quantity",
        label="Quantity",
        kind="number",
        note=(
            "Per-product quantity belongs on each entry of the `products` array, not "
            "here. Leave this top-level field blank."
        ),
    ),
    ExtractFieldSpec(
        name="product_type",
        label="Product type",
        kind="text",
        note=(
            "Do not extract — auto-derived server-side from the product master "
            "category for the resolved product_code(s). Omit this field."
        ),
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
    ExtractFieldSpec(
        name="project_title",
        label="Project title",
        kind="text",
        note=(
            "The PROJECT or site/development name (e.g. a building, township, or "
            "job title) — NOT the customer company and NOT the salesperson. Leave "
            "blank if only a customer company is shown with no distinct project."
        ),
        examples=["Pavilion Damansara Heights", "Lot 12 Bungalow"],
    ),
]


_PORTAL_STOCK_INQUIRY: list[ExtractFieldSpec] = [
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
        name="item_description",
        label="Item description",
        kind="textarea",
        note="Free-text description of the requested item, as printed on the inquiry.",
    ),
    ExtractFieldSpec(
        name="quantity",
        label="Quantity",
        kind="number",
        note="Numeric quantity requested. Strip units and commas.",
    ),
    ExtractFieldSpec(
        name="delivery_date",
        label="Required delivery date",
        kind="date",
        note="ISO date YYYY-MM-DD when the item is required on site.",
    ),
    ExtractFieldSpec(
        name="project_customer",
        label="Project customer",
        kind="fk_customer",
        note=(
            "The BUYER / end-customer company (debtor) the inquiry is for — NOT the "
            "supplier/seller issuing the document, NOT the salesperson, and NOT the "
            "project/site name. The project or site name goes in project_name. "
            "Return the company name only."
        ),
        examples=["ACME Sdn Bhd", "Tan Construction Sdn Bhd"],
    ),
    ExtractFieldSpec(
        name="project_name",
        label="Project name",
        kind="text",
        note=(
            "The PROJECT or site/development name — NOT the customer company. Leave "
            "blank if no distinct project name appears."
        ),
        examples=["Pavilion Damansara Heights", "Lot 12 Bungalow"],
    ),
    ExtractFieldSpec(name="salesperson", label="Salesperson", kind="text"),
    ExtractFieldSpec(name="remark", label="Remark", kind="textarea"),
    ExtractFieldSpec(name="additional_remark", label="Additional remark", kind="textarea"),
]


_PORTAL_PURCHASE_REQUEST: list[ExtractFieldSpec] = [
    ExtractFieldSpec(
        name="customer_name",
        label="Customer name",
        kind="fk_customer",
        note=(
            "The BUYER / end-customer company (debtor) on the request header — NOT "
            "the supplier/seller issuing the document, NOT the salesperson, and NOT "
            "the project/site name (that goes in project_title). Company name only."
        ),
        examples=["ACME Sdn Bhd", "Tan Construction Sdn Bhd"],
    ),
    ExtractFieldSpec(
        name="project_title",
        label="Project title",
        kind="text",
        note=(
            "The PROJECT or site/development name — NOT the customer company. Leave "
            "blank if no distinct project name appears."
        ),
        examples=["Pavilion Damansara Heights", "Lot 12 Bungalow"],
    ),
    ExtractFieldSpec(
        name="purpose",
        label="Purpose",
        kind="textarea",
        note="One- or two-sentence summary of why the items are being requested.",
    ),
    ExtractFieldSpec(
        name="request_date",
        label="Request date",
        kind="date",
        note="ISO date YYYY-MM-DD the request was raised.",
    ),
    ExtractFieldSpec(
        name="expected_delivery_date",
        label="Expected delivery date",
        kind="date",
        note="ISO date YYYY-MM-DD the items are expected on site.",
    ),
    ExtractFieldSpec(
        name="expected_po_date",
        label="Expected PO date",
        kind="date",
        note="ISO date YYYY-MM-DD the PO is expected to be issued.",
    ),
    ExtractFieldSpec(name="requested_by", label="Requested by", kind="text"),
    ExtractFieldSpec(
        name="external_reference",
        label="External reference",
        kind="text",
        note="External PO / quote / RFQ reference number, if printed.",
    ),
]


_PORTAL_SPONSORSHIP_FORM: list[ExtractFieldSpec] = [
    ExtractFieldSpec(
        name="customer_name",
        label="Customer name",
        kind="fk_customer",
        note=(
            "The BUYER / end-customer company (debtor) on the sponsorship request "
            "header — NOT the supplier/seller issuing the document, NOT the "
            "salesperson, and NOT the project/site name (that goes in "
            "project_title). Company name only."
        ),
        examples=["ACME Sdn Bhd", "Tan Construction Sdn Bhd"],
    ),
    ExtractFieldSpec(
        name="project_title",
        label="Project title",
        kind="text",
        note=(
            "The PROJECT or site/development name — NOT the customer company. Leave "
            "blank if no distinct project name appears."
        ),
        examples=["Pavilion Damansara Heights", "Lot 12 Bungalow"],
    ),
    ExtractFieldSpec(
        name="sponsor_subject",
        label="Sponsor subject",
        kind="text",
        note="Short subject of the sponsorship — e.g. showroom, mockup, others.",
    ),
    ExtractFieldSpec(
        name="purpose",
        label="Purpose",
        kind="textarea",
        note="One- or two-sentence summary of why sponsorship is being requested.",
    ),
    ExtractFieldSpec(
        name="delivery_address",
        label="Delivery address",
        kind="textarea",
        note="Full delivery / site address as printed on the request.",
    ),
    ExtractFieldSpec(
        name="total_project_value",
        label="Total project value",
        kind="text",
        note=(
            "Free-text total project value as printed (may be descriptive, e.g. "
            "'BULK ORDER EST RM1.6MIL'). Do not strip non-numeric fragments."
        ),
    ),
    ExtractFieldSpec(
        name="request_date",
        label="Request date",
        kind="date",
        note="ISO date YYYY-MM-DD the request was raised.",
    ),
    ExtractFieldSpec(
        name="expected_delivery_date",
        label="Expected delivery date",
        kind="date",
        note="ISO date YYYY-MM-DD the items are expected on site.",
    ),
    ExtractFieldSpec(name="requested_by", label="Requested by", kind="text"),
]


# ---------------------------------------------------------------------------
# S3 - a CONSUMER's receipt. Deliberately NOT `portal.complaint`.
#
# `portal.complaint` is the dealer/CS track: it reads a Sorento delivery order and asks
# for the DO number and the BUYER being billed. A consumer's attachment is the DEALER's
# OWN invoice, and the S3-pre spike measured what that means:
#
#   - Every dealer document number tested against `orders` was a NO MATCH (AC-C12).
#     `KCS-2112-0054`, `CS002629`, `NV20-2-008850`, `IV01029`, `DO10-2-123494`, `CS40964` -
#     six for six. Asking for a DO number here would produce a field that matches nothing
#     and then invites somebody to join on it.
#   - The company at the top is the SHOP THE CONSUMER WALKED INTO. It is not a buyer being
#     billed and it is not Sorento; a receipt printed on the dealer's letterhead names the
#     dealer as the SELLER, which is the opposite of `portal.complaint`'s customer_name.
#   - 87% print a readable shop name and 97% a purchase date, so those two are worth
#     asking for. 24% print no usable shop name at all, which is why nothing here is
#     required and every field is editable afterwards (AC-C10a, AC-C14).
# ---------------------------------------------------------------------------
_PORTAL_CONSUMER_LODGE: list[ExtractFieldSpec] = [
    ExtractFieldSpec(
        name="shop_name",
        label="Shop name",
        kind="text",
        note=(
            "The SHOP or company that SOLD the item, as printed at the top of the "
            "receipt or invoice - the dealer's own letterhead. This is the SELLER, not "
            "a buyer being billed. Never return 'Sorento' unless Sorento itself issued "
            "the document. Return the company name only, including any Sdn Bhd suffix "
            "and any branch in brackets exactly as printed."
        ),
        examples=["TOTAL HOME DIY SDN BHD", "DiLOOMA SDN. BHD. (JLN IPOH BRANCH)"],
    ),
    ExtractFieldSpec(
        name="dealer_document_number",
        label="Receipt or invoice number",
        kind="text",
        note=(
            "The DEALER's own document number, verbatim. It is NOT a Sorento order "
            "number and must never be matched against one. Do not normalise it, do not "
            "strip prefixes, and if only a till reference is printed return that."
        ),
        examples=["KCS-2112-0054", "CS002629", "NV20-2-008850", "IV01029"],
    ),
    # TRANSCRIBE, do not convert. The model is good at reading paper and unreliable at
    # calendar arithmetic: asked for ISO directly it turned a receipt printed 03/08/2026
    # into 2026-03-03. So it copies the characters and `_derive_purchase_date` does the
    # conversion deterministically, day-first, in code that can be tested.
    ExtractFieldSpec(
        name="purchase_date_printed",
        label="Purchase date, as printed",
        kind="text",
        note=(
            "The date EXACTLY as printed on the receipt, character for character. Do NOT "
            "convert or reformat it: copy '03/08/2026' as '03/08/2026'. Return nothing at "
            "all if no date is legible."
        ),
        examples=["16/10/2025", "03/08/2026"],
    ),
    ExtractFieldSpec(
        name="purchase_date",
        label="Purchase date",
        kind="date",
        note=(
            "ISO date YYYY-MM-DD, the date on the RECEIPT. Malaysian receipts print "
            "DD/MM/YYYY, so 16/10/2025 is 2025-10-16 and never 2025-04-10. Return "
            "nothing at all if no date is legible: an invented date silently becomes "
            "every warranty verdict computed from it."
        ),
        examples=["2025-10-16"],
    ),
    ExtractFieldSpec(
        name="total_value",
        label="Receipt total",
        kind="number",
        note=(
            "The grand total printed on the receipt, digits only. Leave it out when the "
            "document shows no total - never spread or infer one from the line items."
        ),
    ),
    ExtractFieldSpec(
        name="site_address",
        label="Installation address",
        kind="textarea",
        note=(
            "Where the item is INSTALLED, if the document happens to show a delivery "
            "address. This is never the shop's own address."
        ),
    ),
    ExtractFieldSpec(
        name="sorento_order_number",
        label="Sorento order number, if quoted",
        kind="do_number",
        note=(
            "ONLY when the document is Sorento's own (the dealer track, AC-C13), where "
            "the order resolves the dealer, the products and the date directly. On a "
            "dealer's own receipt there is no such number - leave it out rather than "
            "offering the dealer's document number in its place."
        ),
        examples=["202604-0348"],
    ),
]


def _build_master_schema_from_field_linkage(entity_type: str) -> list[ExtractFieldSpec]:
    """Translate :mod:`app.services.field_linkage.registry` FieldSpecs into
    AI-extract ``ExtractFieldSpec`` so the per-attachment extract endpoint
    shares one source of truth with the upload-time field picker."""
    from app.services.field_linkage import get_field_specs as _get

    out: list[ExtractFieldSpec] = []
    for f in _get(entity_type):
        kind = f.kind if f.kind in ("text", "number", "date") else "text"
        out.append(
            ExtractFieldSpec(
                name=f.name,
                label=f.label,
                kind=kind,
                note=f.extract_note,
            )
        )
    return out


FORM_SCHEMAS: dict[str, list[ExtractFieldSpec]] = {
    "portal.complaint": _PORTAL_COMPLAINT,
    "portal.consumer_lodge": _PORTAL_CONSUMER_LODGE,
    "portal.stock_inquiry": _PORTAL_STOCK_INQUIRY,
    "portal.purchase_request": _PORTAL_PURCHASE_REQUEST,
    "portal.sponsorship_form": _PORTAL_SPONSORSHIP_FORM,
}


# Registry-driven master form keys — built lazily so we don't import the
# field_linkage registry at module load time (avoids import cycles during
# Alembic discovery).
_MASTER_FORM_KEY_TO_ENTITY: dict[str, str] = {
    "master.product_fields": "product",
    "master.promotion_fields": "promotion",
    "master.packing_list_fields": "packing_list",
    "master.form_fields": "form",
}


def get_form_schema(form_key: str) -> list[ExtractFieldSpec]:
    """Return the registered schema for ``form_key`` or raise ``KeyError``."""
    schema = FORM_SCHEMAS.get(form_key)
    if schema is not None:
        return schema
    entity_type = _MASTER_FORM_KEY_TO_ENTITY.get(form_key)
    if entity_type is None:
        raise KeyError(form_key)
    return _build_master_schema_from_field_linkage(entity_type)
