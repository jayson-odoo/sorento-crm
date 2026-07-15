# Sorento CRM Request Plan and Ticket Drafts

## Summary

Create tickets first, then execute in this order: order tracking import, stock MCP/output cleanup, stock full-snapshot import, attachment UI/filtering, and forms/access-level/search expansion. The promotion create issue is out of scope because the requester will fix the missing `promotions` wrapper/header data.

Use Malaysia time (`Asia/Kuala_Lumpur`) for MCP `updated_at` values. Treat stock upload Excel files as a complete snapshot across all active warehouses.

## Tickets To Create First

### Ticket 1: Order Tracking Import Should Read Overall Tracking Sheet

Description: Import tracking currently reads `Daily Tracking`; uploaded workbook contains both `Daily Tracking` and `Overall Tracking` with the same headers, but `Overall Tracking` has the full order set. Update backend import and frontend preflight/copy to use `Overall Tracking`.

Initial response: Confirmed workbook has `Overall Tracking` with 1,948 rows and same structure as `Daily Tracking`.

Resolution plan: Backend import should prefer `Overall Tracking`; tests must prove the import reads Overall rows when both sheets exist. Frontend upload dialog should validate/display `Master` + `Overall Tracking`.

### Ticket 2: MCP Stock Tools Should Expose Only On-Hand Quantity and Ignore Inactive Warehouses

Description: `crm_inventory_stock_*` tools currently expose extra stock fields such as available/reserved/damaged/status and may include inactive warehouse locations.

Initial response: Stock APIs currently return full `StockResponse`; MCP proxies these responses directly.

Resolution plan: Add MCP response sanitization for stock tools so only relevant identifiers, warehouse/product info, `quantity_on_hand`, and Malaysia-normalized `updated_at` are exposed. Backend stock queries should exclude inactive warehouses.

### Ticket 3: Stock Upload Should Zero Missing Active Stock Rows With Ledger

Description: Stock import Excel is a full inventory snapshot. Any active-warehouse stock row missing from the upload should become zero and have a system adjustment ledger entry.

Initial response: Current bulk import only creates/updates rows present in the file.

Resolution plan: After processing uploaded rows, zero all active-warehouse stock records not represented in the file, create `SYSTEM_ADJUSTMENT` ledger entries, and include counts in validate/apply summaries.

### Ticket 4: MCP Stock Tools Should Return Last Updated Datetime

Description: n8n needs `updated_at` from stock MCP data so WhatsApp replies can show when data was last refreshed.

Initial response: Stock records have `updated_at`, but consistency and MCP output need tightening.

Resolution plan: Ensure stock mutations set/update timestamps, return Malaysia-time ISO values in `crm_inventory_stock_*`, and document this as the first phase before expanding to products, attachments, promotions, forms, and orders.

### Ticket 5: Attachment Access Levels UI and Smarter Filters

Description: Attachment upload/edit access-level selection should use a dropdown with ticked options, selected pills, and Select All. Attachment list filters should support attachment type, uploaded by, and uploaded at.

Initial response: Current upload/edit UI uses checkbox groups; attachment list advanced filters are not configured.

Resolution plan: Build/reuse an access-level multi-select component, wire it into upload and detail edit, add backend list filters, and expose them in the Files UI filter panel.

### Ticket 6: Forms Need Master Form Type, Access Levels, and Attachment Filename Search

Description: Form type should be configurable master data. Forms need access levels like promotions/attachments. MCP form retrieval must honor Respond contact access, accept/return `form_type`, and search linked attachment filenames. Promotion search should also match promotion attachment filenames.

Initial response: Forms already store raw `form_type`, `attachment_id`, and `access_levels`, but schemas/routes/MCP/search do not fully use them.

Resolution plan: Reuse master-data lookup configuration for form types, add access-level fields to form APIs/UI/MCP, filter by Respond contact access, add attachment filename search for forms and promotions, and return `form_type` in MCP results.

## Implementation Plan

1. Ticket creation first:
   - Create one ticket per item above with description, initial response, and resolution plan.
   - Mark the promotion create endpoint issue as “No code change: requester to fix payload wrapper/header.”

2. Backend changes:
   - Update order tracking import service and route docs from `Daily Tracking` to `Overall Tracking`.
   - Add/adjust inventory service filters to exclude inactive warehouses from stock reads.
   - Add full-snapshot zeroing logic and `SYSTEM_ADJUSTMENT` ledger creation to stock bulk import.
   - Normalize stock MCP `updated_at` to `Asia/Kuala_Lumpur`.
   - Add attachment filters for attachment type, uploaded by, and uploaded date range.
   - Expand forms schemas/services/routes/MCP catalog for form type, access levels, Respond contact filtering, and attachment filename search.
   - Expand promotion list/search to match linked promotion attachment filenames.

3. Frontend changes:
   - Update order tracking upload dialog validation, copy, and summary to use `Overall Tracking`.
   - Update stock import UI to surface zero-adjustment preview/apply counts.
   - Replace attachment access-level checkbox groups with a dropdown checklist, selected pills, and Select All.
   - Add Files advanced filters for attachment type, uploaded by, and uploaded at.
   - Add form type master-data selection and access-level controls to forms create/edit/detail/list flows as applicable.

## Test Plan

Backend:
- Add pytest coverage for order tracking import using a workbook with both tracking sheets and asserting `Overall Tracking` wins.
- Add inventory tests proving inactive warehouses are excluded and MCP stock output omits available/reserved/damaged/status.
- Add stock import tests for missing active rows being zeroed and ledgered as system adjustments.
- Add attachment list filter tests for type, uploader, and uploaded date range.
- Add forms tests for access-level filtering, `form_type`, attachment filename search, and MCP params/results.
- Add promotion search test for matching linked attachment filename.

Frontend / Playwright MCP:
- Verify order import from the UI by navigating through the app, selecting a workbook, and confirming `Overall Tracking` counts.
- Verify stock import preview/apply flow, including missing-row zero adjustment messaging.
- Verify Files access-level dropdown, Select All, selected pills, and attachment filters.
- Verify Forms form-type selection, access-level behavior, and search by attachment filename.
- Always inspect console messages, screenshots, and network requests after the flows.

Commands:
- Backend: `pytest` or targeted files under `sorento_crm_backend/tests/`.
- Frontend: `npm run test`, targeted Vitest where added, and Playwright MCP verification against running frontend/backend.
- E2E regression specs where flows deserve persistence: `npm run test:e2e`.

## Assumptions

- Promotion create endpoint bug will not be changed because requester will fix the missing `promotions` header/wrapper.
- Stock upload files are complete snapshots for all active warehouses.
- Inactive warehouse stock should be excluded globally from stock read/import-zero behavior.
- MCP datetime output should use Malaysia time.
- Form type master data should reuse the existing master-data/lookup pattern unless exploration during execution proves the repo has a more specific form-type master table.
