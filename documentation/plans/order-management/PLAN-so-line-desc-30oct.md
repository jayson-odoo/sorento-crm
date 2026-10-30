# PLAN: SO line description (SO-LINE-DESC, 30 Oct 2026)

Status: Plan (DRAFT; waits on the owner's answers to card Q1-Q5 and mock v1). Track: full (size L:
migration, ingest contract field, purchasing-facing email). PR #2000. LEAD pattern.

Card: `documentation/plans/order-management/SO-LINE-DESC-card.md`. Mock:
`documentation/mockups/SO-LINE-DESC/index.html`. UAC: `so-line-desc-acceptance-criteria.md` (after answers).

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

## Slices (after answers)

1. Migration `sld_0001_so_line_description`: `sales_order_lines.description TEXT NULL`, down_revision
   = main head at build time (today `agp1_0001_agent_foundation`). Model `app/models/order.py:756-795`.
2. Ingest: `_line_values` (`app/services/document_ingest_service.py:1324`, pattern :1403-1406) writes
   `description` from `product_name` when sent (absent keeps, null clears, strip, blank -> NULL).
3. Read: SO detail serializer (`app/services/scm/sales_order_service.py:404`, line keys ~:520-544,
   schema `app/schemas/scm_orders.py:152`) and fulfilment board row (`_Row`
   `app/services/project_fulfilment_board_service.py:429`, fills :1686/:1869/:1960, `_contribution`
   :5531, schema `app/schemas/project_board.py:574`) through `core_sales_order_line_id`.
4. FE: Description column after Product in `SalesOrderDetail.tsx` (~:994) and
   `FulfilmentBoardListView.tsx` (~:640); explicit `size`, `truncate` + `title`.
5. Setting (if Q2 = a): `system_settings` code-list column, both dict builders
   (`app/api/v1/user_management/settings.py:284`, GET :423-426 pattern, PUT :899-908 pattern), FE input on
   the settings page.
6. OI decoration in `handover_item`: `<code> - <description>` for listed codes, `was` side decorated by
   its own code (`order_inquiry_worklist_service.py:4030-4050`).

## Test list (tester writes red first)

- Ingest: sent / absent / null / blank for `product_name` -> `description`.
- SO detail + fulfilment board responses carry `description` (assert the field: `response_model` drops
  undeclared fields).
- `handover_item`: listed code + description; listed + empty; listed + description == code; unlisted
  code with description; `was` line on a code switch; email body, preview body and Excel cell
  string-equal for the same lines.
- Settings round trip (GET/PUT) if Q2 = a.
- Global guards: `tests/test_schema_uuid_id_principle.py` (new column).

## Release order

CRM release first, then check the ss connection's `sorento_contract_version` (v2 needed), then one ss
Repush of sales orders (if Q4 = a). Migration SQL for the crew copy:
`crew/state/migrations/SO-LINE-DESC.sql` (`ADD COLUMN IF NOT EXISTS`).
