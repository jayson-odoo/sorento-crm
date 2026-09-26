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
#: The sheet names a sales order the CRM holds, but no line of it fits the row. Three
#: reasons, reported as the FIRST filter that refused it, because they send the reader to
#: three different places: the catalogue, the warehouse, or the quantity on the order.
NO_LINE_FOR_ITEM = "no_line_for_item"
LOCATION_DIFFERS = "location_differs"
QTY_EXCEEDS_ORDERED = "qty_exceeds_ordered"
#: The sales order is not project demand, so it is not planned here and no order inquiry
#: row can hang off it.
ORDER_NOT_PLANNABLE = "order_not_plannable"
#: The sales order the row names DOES exist, and DOES carry lines, but every one of them is
#: closed or cancelled - no open line survives at all (AC-S4-6, R9). Its own code rather
#: than `NO_LINE_FOR_ITEM`, whose three reasons (catalogue, warehouse, quantity) all assume
#: an open line exists to be checked against: here there is none, so the row is refused
#: before any of those three checks ever runs, and the reader is sent to a fourth place -
#: the order's own status - instead of one of those three.
ORDER_FULLY_DELIVERED = "order_fully_delivered"

# --- written, and destructive: the half a job detail exists to show ------
#: An order line that is no longer on the uploaded book, so the upload closed it. Its own
#: code rather than UPDATED because it is the destructive half of an outstanding upload -
#: "12 lines updated" and "12 lines closed" are the same number about two very different
#: things, and the second is the one somebody has to be able to find afterwards. Carried on
#: OUTCOME_UPDATED: the row WAS written, it is not a skip.
LINE_CLOSED = "line_closed"
#: A scheduled delivery this feed wrote that the sheet has stopped stating, so it was
#: removed. Same reasoning as LINE_CLOSED, on the Order Inquiry side.
LINE_WITHDRAWN = "line_withdrawn"
#: A product whose reorder level the upload emptied, because the file carries the column
#: and this item's cell was blank. Same family as LINE_CLOSED: the row WAS written, and
#: "9,000 products updated" would bury the 642 that lost a number somebody may want back.
REORDER_LEVEL_CLEARED = "reorder_level_cleared"
#: A product whose unit of measure the upload moved to the configured default, because the
#: file states no unit for it. Same family again: the whole point of re-importing the stock
#: list is usually to correct exactly these rows, and "9,000 products updated" would bury
#: them. The message names the unit the product left and the one it landed on.
UOM_DEFAULTED = "uom_defaulted"

# --- deliberate skips -----------------------------------------------------
DUPLICATE_LINE = "duplicate_line"
#: The same key appeared EARLIER IN THE SAME FILE, so this row states nothing the
#: first one did not. Its own code rather than DUPLICATE_LINE, whose label speaks of
#: an order line already on the order: on a customer job there is no order, and the
#: GRN/SPO importers depend on that existing meaning (UAC AC-6.2).
DUPLICATE_IN_FILE = "duplicate_in_file"
ALREADY_EXISTS = "already_exists"
#: The sales order line this row names already carries an order inquiry row, raised by the
#: board or by an earlier upload. Left exactly as it is, links included: the sheet is a
#: migration, not a second opinion about a row somebody has since worked on.
ALREADY_RAISED = "already_raised"
#: The sales order line this row names sits beside a `Replaces N used` row (a replan that
#: redirected a received line), but its quantity or date matches no fresh row's own
#: `previous_qty` / `previous_delivery_date` exactly (`PLAN-oi-rollback-recover-planning-
#: rows.md`, ruling R6). Nothing is guessed at: no used row is raised, and this row is
#: named so purchasing and customer service know which delivery to look at by hand.
NO_USED_DELIVERY_MATCH = "no_used_delivery_match"
#: The sales order line this row names sits beside a top-up: every live ORDER / ORDER BACK
#: row on the line carries the ACTIVE decision's own id, but the sheet row's quantity plus
#: theirs does not equal the decision's `buy_qty` (`PLAN-oi-rollback-recover-planning-
#: rows.md`, ruling R8). Nothing is guessed at: no row is raised, and this row is named so
#: purchasing and customer service know which delivery to look at by hand.
TOP_UP_SUM_MISMATCH = "top_up_sum_mismatch"
#: The sales order line this row names already carries a MIGRATED row, on the line's own
#: date rather than the sheet's - the 18 Sep 2026 reversal of section 7.4. Re-uploading
#: the same sheet, corrected, is how that date gets fixed: the migrated row's own
#: `delivery_date` moves to the sheet's, and the fresh row beside it (raised for a later
#: planning change) has its `previous_delivery_date` corrected too, so the Was/Now (i)
#: stops printing the same wrong date twice. Rides on OUTCOME_UPDATED: the row WAS written.
DELIVERY_DATE_UPDATED = "delivery_date_updated"
ALREADY_RECEIVED_GUARD = "already_received_guard"
#: Real money on the document with no product behind it (handling, transport, misc). Counted
#: on the order and never written as a stock line: a quantity of 1 "HANDLING CHARGES" is not
#: inventory, and left as PRODUCT_NOT_FOUND it would sit in the unmatched-item list for ever
#: telling somebody to add a product that must never exist.
CHARGE_LINE = "charge_line"
#: The document already carries lines written by a DIFFERENT feed, so this upload left every
#: figure on it alone. Distinct from ALREADY_EXISTS, which says the row is simply already
#: held: this says two exports disagree and the disagreement is a decision for a person.
DOCUMENT_OWNED_ELSEWHERE = "document_owned_elsewhere"
#: A caption, a spacer or a package heading - a row that was never a line. Counted rather
#: than dropped silently, and its own code rather than a failure, because 9,144 of them in
#: one export would otherwise bury the handful of rows that really did fail.
NOT_A_LINE = "not_a_line"
#: The row states a netted quantity of zero and nothing else - no ordered figure behind it,
#: so there is no line to write. Not an error: on a file that states the open half of the
#: book, that line is reached by its ABSENCE, in the closed half of the diff. A row that DOES
#: state what was ordered against what went out is a completed line and is written, closed.
NOTHING_OUTSTANDING = "nothing_outstanding"
#: The row belongs to a shipping order (`SPO-...`), which the purchase-order book does not
#: carry: AutoCount exports both families in one file and this channel writes
#: `purchase_orders`, so importing one invents a purchase order nobody raised.
SHIPPING_ORDER = "shipping_order"
#: The row was counted into a delivery this same file already states on another tab. Nothing
#: is skipped - its quantity is in the instalment - so it rides on OUTCOME_UNCHANGED. Its own
#: code because a book of 15,797 rows describing 8,272 deliveries reads as loss otherwise.
RESTATES_AN_INSTALMENT = "restates_an_instalment"

# --- written, but worth a human's eye ------------------------------------
#: A customer was inserted while a NEAR-identical name already sat on the same
#: customer code ("CASH (SRT) - AISAH SHAMSUDlN" against "... SHAMSUDIN"). One code
#: legally carries many names, so this is never a skip: the row IS written and rides
#: on OUTCOME_CREATED. Distinct from ALREADY_EXISTS / DUPLICATE_LINE, which both
#: assert the row was NOT written.
CODE_EXISTS_UNDER_OTHER_NAME = "code_exists_under_other_name"
#: The row named a market segment no `market_segments.code` matches. The column is a
#: foreign key, so the value is dropped rather than costing a whole customer - but the
#: segment decides SCM demand class and fulfilment priority, so the row it happened on
#: is named here instead of only in a file-level list. Rides on whichever success
#: outcome the row earned (created / updated / unchanged); never a skip.
MARKET_SEGMENT_NOT_RECOGNISED = "market_segment_not_recognised"

# --- attachment / file specific ------------------------------------------
FILENAME_COLLISION = "filename_collision"
EXTENSION_NOT_ALLOWED = "extension_not_allowed"
FILE_TOO_LARGE = "file_too_large"
NOT_FOUND_IN_ZIP = "not_found_in_zip"

# --- failures -------------------------------------------------------------
UPSERT_ERROR = "upsert_error"
ROW_ERROR = "row_error"
DB_ERROR = "db_error"

# --- AutoCount pull (PLAN-autocount-pull-review.md) -----------------------
#: A row FoundryX itself left out of the snapshot (its own `excludedRows` /
#: `excludedNonzeroCount`, e.g. a mapping failure on their side). Never applied by
#: either preview or Confirm; rides on OUTCOME_SKIPPED, carrying FoundryX's own
#: reason/message so the reviewer sees exactly what AutoCount refused and why.
#: Upper-cased, unlike every other code here: it names FoundryX's own reason
#: vocabulary rather than one of ours, so it is spelled the way FoundryX's own
#: `excludedRows[].reason` codes are (see the cross-repo contract, Appendix A).
AUTOCOUNT_EXCLUDED = "AUTOCOUNT_EXCLUDED"
#: A stock row whose `location_code` matched a warehouse that exists but is inactive
#: (AC-SP-2) - never reaches `bulk_import_stock`, FED or otherwise.
AUTOCOUNT_NOT_APPLIED_INACTIVE = "AUTOCOUNT_NOT_APPLIED_INACTIVE"
#: A stock row whose `location_code` matched no warehouse in this company at all.
AUTOCOUNT_NOT_APPLIED_UNKNOWN = "AUTOCOUNT_NOT_APPLIED_UNKNOWN"
#: A header `negativePairList` entry - FoundryX's own record of an (item, location) it
#: read as negative on-hand. Display only, from the fetched header, never `bulk_import_
#: stock`'s input (AC-SP-4).
AUTOCOUNT_NEGATIVE = "AUTOCOUNT_NEGATIVE"

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
    NO_LINE_FOR_ITEM: "No sales order line for this item",
    LOCATION_DIFFERS: "No line for this item at that stock location",
    QTY_EXCEEDS_ORDERED: "Quantity exceeds what the line ordered",
    ORDER_NOT_PLANNABLE: "Not project demand, so it is not planned here",
    ORDER_FULLY_DELIVERED: "No open line left: every line is closed or cancelled",
    LINE_CLOSED: "Closed: no longer on the uploaded book",
    LINE_WITHDRAWN: "Withdrawn: this sheet no longer lists it",
    REORDER_LEVEL_CLEARED: "Reorder level cleared: blank in the file",
    UOM_DEFAULTED: "Unit of measure set from the default",
    DUPLICATE_LINE: "Identical line already exists on this order",
    DUPLICATE_IN_FILE: "The same row appears earlier in this file",
    ALREADY_EXISTS: "Already exists",
    ALREADY_RAISED: "Left alone: this line already carries an order inquiry",
    NO_USED_DELIVERY_MATCH: "Beside a used-row line, but no exact quantity/date match",
    TOP_UP_SUM_MISMATCH: "Beside a top-up line, but the quantities do not sum to plan",
    DELIVERY_DATE_UPDATED: "Delivery date corrected to the sheet's own",
    ALREADY_RECEIVED_GUARD: "Blocked: quantity already received",
    CHARGE_LINE: "Charge line: money on the order, no product",
    DOCUMENT_OWNED_ELSEWHERE: "Left alone: another upload owns this document",
    NOT_A_LINE: "Caption or spacer, not a line",
    NOTHING_OUTSTANDING: "Nothing outstanding on this row",
    SHIPPING_ORDER: "Shipping order: not part of the purchase-order book",
    RESTATES_AN_INSTALMENT: "Counted into a delivery this file already states",
    CODE_EXISTS_UNDER_OTHER_NAME: "Inserted; similar name already on this code",
    MARKET_SEGMENT_NOT_RECOGNISED: "Imported; market segment not recognised, left unset",
    FILENAME_COLLISION: "Filename already exists in the target folder",
    EXTENSION_NOT_ALLOWED: "File extension not allowed",
    FILE_TOO_LARGE: "File too large",
    NOT_FOUND_IN_ZIP: "Not found inside the uploaded zip",
    UPSERT_ERROR: "Could not be saved",
    ROW_ERROR: "Row could not be written",
    DB_ERROR: "Database error",
    AUTOCOUNT_EXCLUDED: "Left out by AutoCount",
    AUTOCOUNT_NOT_APPLIED_INACTIVE: "Not applied: warehouse is inactive",
    AUTOCOUNT_NOT_APPLIED_UNKNOWN: "Not applied: unknown location",
    AUTOCOUNT_NEGATIVE: "AutoCount reports a negative on-hand quantity",
}


def label_for(code: str) -> str:
    """Human label for a code; unregistered codes degrade to a humanised slug."""
    if not code:
        return "Unspecified"
    known = LABELS.get(code)
    if known:
        return known
    return code.replace("_", " ").capitalize()
