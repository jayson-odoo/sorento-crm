# PLAN: SO line description (SO-LINE-DESC, 30 Oct 2026)

Status: Review (reviewer READY after round 1, security clean, hand test filed 30 Oct; owner answered 16:13, Q2 = per-product tick). Track: full (size L:
migration, ingest contract field, purchasing-facing email). PR #2000. LEAD pattern.

Card: `documentation/plans/order-management/SO-LINE-DESC-card.md`. Mock:
`documentation/mockups/SO-LINE-DESC/index.html`. UAC: `so-line-desc-acceptance-criteria.md` (AC-1..AC-16).

## Problem

AutoCount staff key a generic spare-part code (RPACC, 5,404 SO lines; RPAC 1,683) and write the real
part in the line Description beside it. Shared service already sends that text on every SO line as
`product_name` (ss `presets.py:205-222, :282`); the CRM uses it only to resolve the product and drops
it (`app/schemas/canonical_documents.py:99`). Purchasing sees a bare "RPACC" on SO > Lines,
fulfilment planning and the OI email.

## ARCHITECTURE

- Layer: storage + ingest (backend), two read columns (frontend), one email-line decoration point
  (backend service). No shared-service change, no contract bump.
- Shared mechanism, not one shape per surface: the OI email body, the send/resend preview and the
  Excel all read `handover.lines` built by `handover_item`
  (`app/services/project_order_inquiry_service.py:4685`) through `build_handover_email` (~:14760;
  resend preview `app/services/oi_handover_resend.py:147`; Excel
  `app/services/order_inquiry_worklist_service.py:4021`). The decoration lives ONLY there, so the three
  cannot drift. No template migration for the text; Q5 (wrap) may need one template tweak.
- Classes fixed, not one row: every listed code, every OI line kind (new, changed with `was`,
  undone), empty description, description equal to the code.

## Slices

1. Migration `sld_0001_so_line_description`: `sales_order_lines.description TEXT NULL`;
   `products.show_so_line_description BOOLEAN NOT NULL DEFAULT false`; data step ticks
   `product_code = 'RPACC'` (every company). down_revision
   = main head at build time (re-check `alembic heads` after merging origin/main; 30 Oct: `pp4_0002`). Model `app/models/order.py:756-795`.
2. Ingest: `_line_values` (`app/services/document_ingest_service.py:1324`, pattern :1403-1406) writes
   `description` from `product_name` when sent (absent keeps, null clears, strip, blank -> NULL).
3. Read: SO detail serializer (`app/services/scm/sales_order_service.py:404`, line keys ~:520-544,
   schema `app/schemas/scm_orders.py:152`) and fulfilment board row (`_Row`
   `app/services/project_fulfilment_board_service.py:429`, fills :1686/:1869/:1960, `_contribution`
   :5531, schema `app/schemas/project_board.py:574`) through `core_sales_order_line_id`.
4. FE: Description column after Product in `SalesOrderDetail.tsx` (~:994) and
   `FulfilmentBoardListView.tsx` (~:640); explicit `size`, `truncate` + `title`.
5. Product tick: model `app/models/product.py` (pattern `has_serial_tracking`), schemas
   `app/schemas/product.py:185` (create/out) and `:252` (update, Optional), FE switch in
   `products/components/ProductForm.tsx:897-930` and badge in `products/[id]/components/ProductDetail.tsx:552-566`,
   type in `products/types/product.types.ts`. Product ingest from shared service must not touch it.
6. OI decoration in `handover_item`: `<code> - <description>` for ticked products, `was` side by its own
   product's tick (`order_inquiry_worklist_service.py:4030-4050`). Email wrap (Q5): template migration
   `oihr_0011_item_code_wrap` (pattern oihr_0009/0010: swap the ITEM CODE cell so it drops `nowrap` only
   when the line carries a description); Excel `wrap_text` on decorated cells.

## Test list (tester writes red first)

- Ingest: sent / absent / null / blank for `product_name` -> `description`.
- SO detail + fulfilment board responses carry `description` (assert the field: `response_model` drops
  undeclared fields).
- `handover_item`: listed code + description; listed + empty; listed + description == code; unlisted
  code with description; `was` line on a code switch; email body, preview body and Excel cell
  string-equal for the same lines.
- Product tick: GET/PUT round trip, default false, product ingest leaves it alone, migration ticks RPACC only.
- Global guards: `tests/test_schema_uuid_id_principle.py` (new column).

## Release order

CRM release first, then check the ss connection's `sorento_contract_version` (v2 needed), then one ss
Repush of sales orders (Q4 = a; measure load first, crew-note it). Migration SQL for the crew copy:
`crew/state/migrations/SO-LINE-DESC.sql` (`ADD COLUMN IF NOT EXISTS`).

## Repush load (Q4 = a, measured from shared-service code, origin/main)

- Repush (`POST /{company_id}/entities/sales_order/etl-task/repush`, ss `routers/companies.py:850-882`) clears
  the SO row hashes; the next reconcile re-sends EVERY SO with `DocDate >= task.fromDate`, cancelled included
  (ss `sql_source/source.py:296-322, 466-468`). No date / doc / open-only parameter.
- Size: prod SO task `fromDate` 2023-09-01 = 148,068 SOs, ~621k lines in Sep 2026
  (ss `documentation/plans/sprint-5/03-autocount-bulk-document-load.md:9-10`); today's count UNVERIFIED.
- Pace: extract 2,000 headers/page within a 600 s budget per tick; push 5,000 rows per run in POSTs of 200,
  concurrency 1 (ss `app/config.py:447-501`, `repositories/autocount_repository.py:639`). About 30 runs for
  ~150k SOs; precedent reconcile of 148,068 took 20 ticks / 4,220 s (ss sprint-5 test report :57-69).
- CRM cost: every re-sent SO takes the full ingest path (the quiet `backfill` mode is DO-only, ss
  `sinks_sorento.py:1416-1421`). Whether the CRM short-circuits an unchanged SO is UNVERIFIED (check before release).
- Measure before: `SELECT COUNT(*) FROM dbo.SO WHERE DocDate >= '<fromDate>'` via ss `POST /autocount/sql/preview`
  (ss `routers/sql.py:121`). After: repush response `clearedCount`, Runs tab `pushed`.
- Lever if the count is too heavy: temporarily raise the task `fromDate` (e.g. to the oldest SO still open)
  for the repush, then restore it. Owner decides at release with the measured count; crew-note it then.
