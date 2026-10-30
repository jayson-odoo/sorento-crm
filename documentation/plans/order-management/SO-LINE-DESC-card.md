# SO-LINE-DESC owner card (30 Oct 2026)

Status: Plan, size L, LEAD pattern. Behaviour card filed; no product code until the owner answers.

Owner ask (30 Oct ~11:25, SO428498 Lines tab): pull the AutoCount SO line description through shared
service, show it as its own column on SO > Lines and in fulfilment planning; in the OI email, the
preview before sending and the OI Excel attachment, NO new column: for selected codes (RPACC first)
the ITEM CODE cell carries code + description. Email = preview = attachment must tally.

## What already exists (read, not assumed)

- Shared service ALREADY reads `SODTL.Description` (the per-line text beside Item Code in AutoCount)
  and pushes it on every SO line as `product_name` (ss `origin/main`
  `service_backend/modules/autocount/presets.py:205-222` select, `:282` map;
  `canonical/documents.py:282-284`, sent when the connection's `sorento_contract_version` >= 2).
  `FurtherDescription` already arrives as `line_remark` (FULFIL-SO-REMARK, ss #131).
- The CRM receives `product_name` (`app/schemas/canonical_documents.py:99`) but uses it only to
  resolve the product; it is never stored on the line. Core `sales_order_lines` has no description
  column (`app/models/order.py:756-795`).
- So: **no shared-service change, no contract bump.** The gap is CRM-only.

## Rules

1. Storage: new nullable Text column `sales_order_lines.description` (core table). Ingest writes it from
   the line's `product_name` only when the key is sent: absent keeps the stored value, explicit null
   clears (same as `line_remark`, `app/services/document_ingest_service.py:1403-1406`). Read-only in
   the CRM; AutoCount owns it. Migration chains onto main's head `agp1_0001_agent_foundation`.
2. SO > Lines: new "Description" column right after Product
   (`app/(protected)/scm/sales-orders/[id]/components/SalesOrderDetail.tsx:914-994`), truncate + title.
   Product column unchanged (code, product master name underneath).
3. Fulfilment planning (list view): new "Description" column after Product (`item_code`)
   (`app/(protected)/project-sales/fulfilment-planning/components/FulfilmentBoardListView.tsx:638`),
   read from the core line through `projects.sales_order_lines.core_sales_order_line_id`.
4. OI email, send preview, OI Excel: no new column. For a code on the list, ITEM CODE reads
   `<code> - <description>`; every other code unchanged. One change point:
   `handover_item` `"item_code"` (`app/services/project_order_inquiry_service.py:4685`) feeds the
   email body (template cell `alembic/versions/oihr_0009_split_rows.py:53-54`), the send/resend
   preview (`app/services/oi_handover_resend.py:147`, same `build_handover_email`) and the Excel
   (`app/services/order_inquiry_worklist_service.py:4021`, cells `:4049-4050`). Tally by construction.
   A split row's "was" line follows the same rule.
5. Empty description, or description equal to the code: code alone, no trailing " - ".
6. Backfill: existing SOs gain the description only when shared service re-sends them (Repush,
   ss `routers/companies.py:850-882`) after the CRM release; new and edited SOs carry it from the
   next sync.

## Real examples

Lane cannot read rows: the auto-mode classifier blocks row reads on `sorento_prod_1020` (Production
Reads). Read-only SQL for crew to run: `documentation/plans/order-management/SO-LINE-DESC-rpacc-examples.sql`
(RP* line counts, 5 latest RPACC lines, SO428498; no customer columns). Mock v1 follows on those rows.

## Edge cases

- Email ITEM CODE cell is `white-space:nowrap` (`oihr_0009_split_rows.py:53`): a long description
  would stretch the table (Q5).
- Canonical `product_name` caps at 255 chars (`canonical_documents.py:99`); AutoCount's SODTL.Description
  length is UNVERIFIED (believed shorter).
- Live connection on contract v2: UNVERIFIED; SQL query 1 `with_line_remark > 0` proves it.
- Resend preview's own check `row.item_code in body_html` (`oi_handover_resend.py:210`) still holds:
  the code stays the cell's prefix.
- A code switch prints the old code (`was.item_code`, set only on a real change) then NEW ITEM CODE
  (`order_inquiry_worklist_service.py:4030-4050`, template `oihr_0009_split_rows.py:53`). Each side is
  decorated only if ITS code is on the list, using the line's description. Test pins it.
- Unchanged: Confirm split sheet (`LineSplitSheet.tsx:547`), OI worklist, fulfilment board cards.

## Questions (recommendation first)

1. Cell format: (a) `RPACC - <line description>` on one line; (b) code, line break, description in the
   same cell; (c) code + space + description. Rec (a): reads the same in the HTML body, the email's
   plain-text part and Excel; a line break renders differently per email client.
2. Code list: (a) a System Settings list, admins edit, starts as RPACC (pattern
   `handling_lock_enabled_types`, `app/models/user.py:575`, `app/api/v1/user_management/settings.py:423-426, 899-908`);
   (b) a tick on each product record; (c) fixed in code, change by release. Rec (a): one setting on
   an existing page, no product form change.
3. SO Lines Description column: (a) every line; (b) only where it differs from the product master
   name. Rec (a): staff edit Description on ordinary codes too, and (b) hides it inconsistently.
4. Backfill: (a) one shared-service Repush of sales orders after the CRM release, so open RPACC lines
   show it at once; (b) new and edited SOs only. Rec (a). Repush re-sends every SO; its load is UNVERIFIED.
5. Long text in the email cell: (a) the ITEM CODE cell wraps only when it carries a description
   (others keep nowrap); Excel cell wraps, column width unchanged; (b) keep nowrap everywhere.
   Rec (a).
