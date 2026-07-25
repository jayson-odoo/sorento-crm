"""Shared reason taxonomy for import outcomes.

One code means the same thing in every importer, in the validation previews, and
in the frontend. Without a shared vocabulary each importer invents its own
phrasing ("Product not found: X" vs "product missing") and the aggregated
breakdown can never group them.

Adding a code: add the constant AND its label here. `label_for` falls back to a
humanised slug so an unregistered code still renders sensibly rather than
blowing up.
"""
from __future__ import annotations

# --- outcomes -------------------------------------------------------------
OUTCOME_CREATED = "created"
OUTCOME_UPDATED = "updated"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"

#: Outcomes that count towards `successful_rows`.
SUCCESS_OUTCOMES = (OUTCOME_CREATED, OUTCOME_UPDATED, OUTCOME_UNCHANGED)
ALL_OUTCOMES = SUCCESS_OUTCOMES + (OUTCOME_SKIPPED, OUTCOME_FAILED)

# --- success codes --------------------------------------------------------
CREATED = "created"
UPDATED = "updated"
UNCHANGED = "unchanged"
REPLACED = "replaced"
RENAMED_COPY = "renamed_copy"

# --- missing / malformed input -------------------------------------------
MISSING_DOC_NO = "missing_doc_no"
MISSING_ITEM_CODE = "missing_item_code"
MISSING_LOCATION = "missing_location"
MISSING_QUANTITY = "missing_quantity"
MISSING_CONTAINER = "missing_container"
MISSING_REQUIRED_FIELD = "missing_required_field"
INVALID_QUANTITY = "invalid_quantity"

# --- unresolved references ------------------------------------------------
ORDER_NOT_FOUND = "order_not_found"
PRODUCT_NOT_FOUND = "product_not_found"
WAREHOUSE_NOT_FOUND = "warehouse_not_found"
GRN_HEADER_NOT_FOUND = "grn_header_not_found"
PACKING_LIST_NOT_FOUND = "packing_list_not_found"
ORDER_NOT_IN_MASTER = "order_not_in_master"

# --- deliberate skips -----------------------------------------------------
DUPLICATE_LINE = "duplicate_line"
ALREADY_EXISTS = "already_exists"
ALREADY_RECEIVED_GUARD = "already_received_guard"

# --- attachment / file specific ------------------------------------------
FILENAME_COLLISION = "filename_collision"
EXTENSION_NOT_ALLOWED = "extension_not_allowed"
FILE_TOO_LARGE = "file_too_large"
NOT_FOUND_IN_ZIP = "not_found_in_zip"

# --- failures -------------------------------------------------------------
UPSERT_ERROR = "upsert_error"
ROW_ERROR = "row_error"
DB_ERROR = "db_error"

LABELS: dict[str, str] = {
    CREATED: "Created",
    UPDATED: "Updated",
    UNCHANGED: "Already up to date",
    REPLACED: "Replaced in place",
    RENAMED_COPY: "Renamed to keep both copies",
    MISSING_DOC_NO: "Missing document number",
    MISSING_ITEM_CODE: "Missing item code",
    MISSING_LOCATION: "Missing location",
    MISSING_QUANTITY: "Missing quantity",
    MISSING_CONTAINER: "Missing or invalid loading date (no container number)",
    MISSING_REQUIRED_FIELD: "Missing required field",
    INVALID_QUANTITY: "Invalid or zero quantity",
    ORDER_NOT_FOUND: "Order not found",
    PRODUCT_NOT_FOUND: "Product not found",
    WAREHOUSE_NOT_FOUND: "Warehouse not found",
    GRN_HEADER_NOT_FOUND: "GRN header not found",
    PACKING_LIST_NOT_FOUND: "Packing list not found for container",
    ORDER_NOT_IN_MASTER: "Order not found in Master sheet",
    DUPLICATE_LINE: "Identical line already exists on this order",
    ALREADY_EXISTS: "Already exists",
    ALREADY_RECEIVED_GUARD: "Blocked: quantity already received",
    FILENAME_COLLISION: "Filename already exists in the target folder",
    EXTENSION_NOT_ALLOWED: "File extension not allowed",
    FILE_TOO_LARGE: "File too large",
    NOT_FOUND_IN_ZIP: "Not found inside the uploaded zip",
    UPSERT_ERROR: "Could not be saved",
    ROW_ERROR: "Row could not be written",
    DB_ERROR: "Database error",
}


def label_for(code: str) -> str:
    """Human label for a code; unregistered codes degrade to a humanised slug."""
    if not code:
        return "Unspecified"
    known = LABELS.get(code)
    if known:
        return known
    return code.replace("_", " ").capitalize()
