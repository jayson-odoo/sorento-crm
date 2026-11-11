# PLAN: Order Inquiry lines link to purchase orders with the shared Stock Debt link function (OI-PO-LINK)

Status: Build (card answered by crew 11 Nov, owner may veto). Stacked on #2332's branch (merged into this lane at 8954e73d). Track: normal (size M, LEAD pattern: tester, coder,
reviewer subagents). Depends on #2332 (STOCKDEBT-LIVE-ACTIONS, head 11f7a635, not merged): coding stacks on its
branch `claude/stockdebt-frozen-so-po-link-t3dlxa` if it is still open when the card is answered.

## 0. Owner, 11 Nov (verbatim)

"next is other than stock debt right, we should apply this linking function to order inquiry also so purchasing can
link, it is a same unified function". The Stock Debt PO link was accepted as built: the link lives on the AutoCount
PO ROW (one PO row per SO row; partial qty splits the PO row into a linked row + a free row; FromDocType SO /
FromDocNo / FromDocDtlKey written by the Shared Service).

## 1. Journey

Purchasing opens Project Sales > Order Inquiries, ticks rows whose sales order line is in AutoCount, opens Actions >
"Link to PO..." and gets the SAME popup Stock Debt shows: one row per ticked sales order line, a PO line picker
(open PO lines of the product, same AutoCount book, with free qty) and the qty. Link sends one write per SO line
through the same Shared Service path; the popup turns into one result per line in plain words (done, refused with
the reason and Try again, unknown -> looked up first). The ticked OI rows then show the PO in their PO column
(the existing AutoCount book step re-runs for exactly those rows, `R18` in `PLAN-oi-links-autocount-truth-24sep.md`).
"Change PO..." and "Unlink from PO..." work the same way. Right-click on a row offers the same three items for that
row.

## 2. What exists (measured, cited)

Stock Debt (#2332 head 11f7a635):
- Service `sorento_crm_backend/app/services/scm/stock_debt_po_link_service.py`: `StockDebtPoLinkService` with
  `options` (:214), `link` (:511, validates every line, then one SS write per SO line via `_send_link`), `unlink`
  (:591), `change` (unlink-first, then link), `relink` (:614), `relocate` (:658), `resume` (:675). Every write goes
  through `_send_intent` (idempotency key per intent + row state, `send_with_attempts`, a definite refusal releases the
  key so Try again is a new attempt) and `_apply_safely` (AutoCount read-back onto CRM PO lines).
- The ONLY places the service is tied to a snapshot row: `_row(snapshot_id, row_id)` (:154), `_row_line_ids(row)`
  (:165, the SO lines a write may name), `row.product_id` (`_po_line` :287, `options` :216), `_row_company_code`
  (:172) and `_row_so_refs` (:299). Everything else is scope-free.
- Routes `sorento_crm_backend/app/api/v1/projects/stock_debt_snapshots.py:246-` (`PO_LINK`, `_require_switch` on
  `system_settings.stock_debt_po_link_enabled`, permission `projects.stock_debt.link_po`,
  `app/rbac/permission_registry.py:703`). Schemas `app/schemas/stock_debt_snapshot.py:199-275` (`PoLinkIn` 1..50
  lines, `PoChangeIn`, `PoUnlinkIn`, `PoLinkResults`).
- CRM storage of a link: `purchase_order_lines.from_so_line_ref` (`app/models/procurement.py:975`), the AutoCount
  SO row ref `{db}:{DocKey}:{DtlKey}` = `sales_order_lines.source_ref`.
- FE `sorento_crm_frontend/app/(protected)/project-sales/stock-debt/`: `components/PoLinkDialog.tsx` (662 lines,
  modes link / unlink / relink / change, typed on `SnapshotLine`), `lib/poLinkWording.ts` (menu enable rules +
  result wording), `hooks/useStockDebtSnapshots.ts:125-185` (`usePoLinkOptions`, `usePoLinkMutations(id, rowId)`,
  `usePoLinkSwitch`), drill menu `components/SnapshotDrillDialog.tsx:290-330`.

Order Inquiry (main 110e494f):
- `projects.order_inquiries` (`app/models/project_so.py:816`), rows `projects.order_inquiry_rows`
  (`:990`, `so_line_id` -> `projects.sales_order_lines` :1011, whose `core_sales_order_line_id` (:544) is the
  AutoCount-backed `public.sales_order_lines` row with `source_ref`). CRM-side placements
  `projects.order_inquiry_links` (:1145); AutoCount is the source of truth for them (R18).
- Worklist routes `app/api/v1/projects/order_inquiries.py:292` (list), `:510` (summary), `:1798` (`auto-place`, which
  with `row_ids` is "Link selected": re-runs the AutoCount book step for exactly those rows).
- FE `order-inquiries/components/OrderInquiriesClient.tsx`: rows-first Actions menu (`secondaryActions`,
  :1851-1960: Auto link all, Choose document, Link selected, Unlink selected, Reject, Unconfirm, ...).

## 3. Design: one shared function, two scopes

### Backend
1. Rename/move the service to `app/services/scm/po_link_service.py` as `PoLinkService(db, scope)`. A `PoLinkScope`
   is a tiny value object: `product_id`, `so_line_ids` (the public SO lines a write may name), `company_code`.
   Every `_row(...)` / `_row_line_ids` / `row.product_id` / `_row_so_refs` read becomes a read of the scope. All
   validation, `_send_intent`, `_apply`, wording and order of writes stay the same code.
2. Stock Debt builds its scope from the snapshot row (`scope_for_snapshot_row(db, snapshot_id, row_id)`, 404 as
   today); `StockDebtPoLinkService` stays importable as a thin alias so its routes and tests are untouched
   (byte-for-byte behaviour, every existing po-link test green with no edit).
3. Order Inquiry builds its scope from ticked OI row ids (`scope_for_oi_rows(db, row_ids)`): each row's
   `so_line_id -> core_sales_order_line_id`; rows must share ONE product (the dialog is per product, like a Stock
   Debt row); rows with no AutoCount SO line are refused by name. Company scoping is the session's (same query
   scope as every OI read).
4. Routes `POST /project-sales/order-inquiries/po-link/{options,link,unlink,change}` taking `row_ids` + the same
   bodies as Stock Debt; same switch, same permission (Q1), same schemas. `relocate` / `resume` reuse the Stock Debt
   routes (scope-free already). After a write whose outcome is `done`, the same request re-runs the OI book step
   for exactly the ticked rows (`auto-place` with `row_ids`), so the PO column shows the link without a manual
   "Link selected".

5. **Batch per PO line (crew addition, owner 22:55: faster, lighter AutoCount writes).** The shared service groups
   the validated lines by PO line and sends ONE Shared Service batch operation per PO line (PO row + N
   `(SO row, qty)`), shape from lane PO-LINK-BATCH's crew-note. Until that SS op is merged, the same grouping
   function sends the current per-line write for each member (one switch-over point, `_send_group`), so the
   follow-up is one small change. Retry rule kept: a refusal releases (Try again = new attempt), only a confirmed
   success locks, an unknown answer keeps its key so the retry replays.

6. **Actor trace (crew addition, owner: every db1 write traced to the person).** `PoLinkService(db, scope,
   actor={id, name})`: every SS write call carries `X-Request-ID` (the press's request id, already sent) plus
   `X-Actor-User-Id` / `X-Actor-Name` (header names provisional until lane AC-DB1-READY's crew-note; one constant
   to change). Each write also stores one audit EVENT `scm.po_line.crm_link_write` on the PO line (actor = the
   pressing user, `new_values` = action, outcome, SO number/line, qty, `request_id`, `operation_id`), rolled up to
   the PO header like the ingest's link events (`po_link_history.py`).
7. **Batch op shape (PO-LINK-BATCH crew-note 6799080814, provisional):** `POST po-links/batch`
   `{companyCode, poDocKey, poDtlKey, docDate, links:[{soDocKey, soDtlKey, qty, soDocDate}]}`, all or nothing,
   1..20 links. Not merged in the SS yet, so this lane ships the grouping with the per-line send inside
   `_send_group`; the switch to the batch call is the one small follow-up.

### Frontend
1. Move `PoLinkDialog.tsx`, `poLinkWording.ts` and the po-link hooks to `project-sales/_shared/po-link/`. The dialog
   takes a `PoLinkTarget` (`{ key, api: { options, link, unlink, change, relink? } }`) and lines in a shared
   `PoLinkLine` shape (`sales_order_line_id, so_number, line_no, open_qty, po_links`). Stock Debt maps
   `SnapshotLine` -> `PoLinkLine` (identity mapping of the fields it already reads); its tests stay green.
2. OI: three items in the existing Actions menu (rows-first; counts as "Link to PO... (2 of 3)" like its siblings),
   the same three in the row right-click menu, greyed with the reason (switch off / no AutoCount SO line / mixed
   products / `poLinkMenu` capability reasons).

## 4. Owner standing rules that apply (self-checked at handtest / done)

Rows-first bulk action; one main button per step (Link inside the popup); right-click row actions; one line per row
in the dialog grid; no ids in UI; plain words; every failed AutoCount write retryable (refusal releases, unknown is
looked up first, only done locks); ERP features behind the admin switch OFF by default, every call logged; number
field typing rule; dd/mm/yyyy dates; nothing hangs; one bad line never fails the batch (each SO line is its own
write and result); History tab (PO link history `po_link_history.py` already records every write); assistant
coverage (a write action: n/a unless the registry lists stock-debt link, checked at DoD).

## 5. Tests (tester writes first, red)

- Shared function: one test module drives `PoLinkService` through BOTH scopes with the same fake AutoCount and
  asserts the same body, key and refusal for the same SO/PO pair.
- OI happy path: two OI rows -> link -> SS called once per SO line, `from_so_line_ref` written, OI row PO column
  shows the PO after the response.
- Partial split: qty < PO row qty -> split body, linked row + free row applied.
- Refusal retry: definite refusal -> result `refused`, second press sends under a new attempt key; unknown outcome
  -> key kept.
- Scope refusals: OI row without AutoCount SO line, mixed products, SO line not in the ticked rows.
- Switch OFF -> 403, permission missing -> 403.
- FE: the shared dialog renders from both screens; OI menu enable/disable reasons; existing Stock Debt
  `PoLinkDialog.test.tsx` / `poLinkWording.test.ts` green unchanged (moved path only).

## 6. Rulings (crew for the owner, 11 Nov, behaviour card on #2350)

- Q1 (a): one permission `projects.stock_debt.link_po` and one Settings switch
  (`system_settings.stock_debt_po_link_enabled`) for both screens; their labels are reworded to cover both
  (permission name "Link PO lines in AutoCount (Stock Debt, Order Inquiries)"; switch label likewise). No new
  permission slug, no migration.
- Q2 (b): OI gets "Link to PO...", "Change PO...", "Unlink from PO..."; the existing "Unlink selected" is renamed
  "Remove link in CRM" and "Link selected" (re-runs the AutoCount book step, R18) is renamed "Recheck in AutoCount".
- Q3 (a): default qty = the SO line's still-needed qty (outstanding less POs already linked), capped at the PO line's
  free qty: Stock Debt's `stillNeeds` / `qtyCap` unchanged.

UAC: `oi-po-link-11nov-acceptance-criteria.md`.
