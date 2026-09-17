# Research: everything one fulfilment board Confirm writes (input to PLAN-board-undo-last-confirm)

Status: research note, 17 Sep 2026. Read-only map produced against `feat/oi-replan-received-links` at `2eb9188f5`. Line numbers drift; treat them as pointers, re-grep before relying on one.

Abbreviations: PSS = `app/services/project_supply_service.py`, POIS = `app/services/project_order_inquiry_service.py`, PCS = `app/services/planning_change_service.py`, STS = `app/services/stock_transfer_service.py`, OLS = `app/services/scm/order_link_service.py`, API = `app/api/v1/projects/fulfilment_planning.py`.

## 1. The write set of ONE confirmation, in execution order

Entry points: `API:383 confirm_all` -> `write_one` (`API:422`) -> either `supply.confirm` (`API:428`) or `_confirm_a_planning_change` (`API:646`); per-order `API:599 confirm_supply` -> same fork at `API:621-624`. The HTTP layer owns the commit (`API:625`); everything below is one transaction.

`PSS:4038 confirm` validates and delegates every write to `PSS:5604 _write_decision`.

### 1.1 `projects.so_supply_decisions`

| What | Where | Pre-image |
|---|---|---|
| prior revision `state='superseded'`, `superseded_at`, `superseded_reason="Reconfirmed by CS."` | `PSS:5620-5622` | Recoverable: row survives; reset `state`/`superseded_at`/`superseded_reason` restores it. Only an ACTIVE row is superseded, so no older reason is overwritten. |
| new row: `revision_no = latest+1`, `state='active'`, `line_snapshots`, `confirmed_by/at`, `supersedes_id = previous.id`, `suspected_system_issue`, `source_revision` | `PSS:5658-5673`, `supersedes_id` at `5671` | Recoverable: `supersedes_id` is the back-pointer an undo needs. Conflict guard `PSS:5674-5687` (partial unique index `uq_so_supply_decisions_active`, model `app/models/project_so.py:1245-1252`). |
| DONOR orders' active revisions superseded + re-issued minus the borrowed line | `PSS:5691 _supersede_borrowed_donors` -> `PSS:6064 _reissue_without_line` (`6095-6096` supersede, `6115` `supersedes_id`, `6122-6146` allocation copy) | Partially recoverable: chain followable via `supersedes_id`, but on a SECOND order's chain; undo must walk it too. |
| audit row | `SOSupplyDecision.__audit_track__ = True`, entity `project_so_supply_decisions` (`app/models/project_so.py:1208-1210`); listeners `app/services/audit_service.py:440`, collect `:338-392` | Recoverable (CREATE/UPDATE with `old_values`). The ONE audited table in the set. |

### 1.2 `projects.so_supply_decision_drafts` (CLEARED, hard delete)

`PSS:5763-5769` -> `project_line_draft_service.delete_drafts_for_lines` (`app/services/project_line_draft_service.py:344-372`), `db.delete(row)` per confirmed line keyed by `core_sales_order_line_id`. Only the NAMED lines' drafts go.

Pre-image LOST. No audit, no soft delete, no copy into the decision.

### 1.3 `projects.so_line_allocations`

- Named lines: `PSS:5704 _write_allocations` (def `PSS:6921`): reserve rows `6976-6987`, borrow rows `7024-7039`, buy row `7043-7055`. All carry `decision_id`, `confirmed_by`, `confirmed_at`.
- Carried lines: `PSS:5727 _carry_allocations` (def `PSS:7087`) copies the superseded revision's rows verbatim under the new `decision_id` (`7114-7129`).
- Nothing deleted or updated (docstring `PSS:6930-6935`). Holds stop counting because `_hold_rows` filters on the ACTIVE decision.

Pre-image recoverable: delete rows `WHERE decision_id = <new decision>`, re-activate the prior revision. Caveat: `_write_allocations` may ADOPT a standing unowned hold (`PSS:6941-6956`, `_unowned_holds` `PSS:7057`); the reallocation row (`decision_id IS NULL`, reason `Reallocated from %`) is not consumed, so safe.

### 1.4 `projects.allocation_claims`

`PSS:7005-7023`: one `AllocationClaim` per cross-project borrow, inserted at `state=CLAIM_ACCEPTED`, `claim_id` stamped on the allocation (`PSS:7032`).

Recoverable: insert-only, reachable by `so_line_allocations.claim_id`. Carried lines RE-USE the same `claim_id` (`PSS:7122`): an undo must not delete a claim a carried row still points at.

### 1.5 `projects.stock_transfers`

`PSS:5770 _write_transfers` (def `PSS:6860`) in a SAVEPOINT -> `STS:171 reconcile_for_decision` -> `STS:253 _keep_or_cancel` + `write_for_decision`:
- KEPT rows: `row.supply_decision_id = decision.id` (`STS:294`), state/number/approver untouched.
- GONE/SHRANK rows: `state = TRANSFER_CANCELLED`, `cancelled_reason = "Superseded by revision N"`, `cancelled_at` (`STS:304-306`).
- New `proposed` rows for the difference. `moved` rows never touched.

Half-lost: cancel is a reversible state flip; the repoint overwrites the previous `supply_decision_id` with no record. `(written, failed, kept)` returned (`PSS:6909`, `6917-6919`) but the confirmation commits regardless.

### 1.6 `projects.order_inquiries` (header)

`POIS:2447 ensure_inquiry` mints ONE header per order (`amendment_id = NULL`, `POIS:2465`). Reconfirm REUSES it and re-stamps `raised_by` / `raised_at` to the confirming actor (`POIS:725-733`). Gate `POIS:712-723`. Second minting site `PSS:5949-5953`.

Pre-image LOST for `raised_by` / `raised_at`; `OrderInquiry` not audited.

### 1.7 `projects.order_inquiry_rows`

All inside `POIS:638 refresh_for_decision`, called at `PSS:5788`.

| Case | Where | Fields written | Pre-image |
|---|---|---|---|
| Raised (outstanding > 0) | `POIS:937-959` | `qty`, `delivery_date`, `stock_location`, `verb`, `cited_document`, `supply_decision_id`, `state=raised`, handshake fields from `_handshake_for_raise` (`POIS:926`, def `1092`) | Insert-only; addressable by `supply_decision_id`. |
| Cancelled on supersede | `POIS:854-871` | `state=cancelled`, `row.note = "Superseded by revision N"` (BARE assignment) | Note LOST. State recoverable. |
| Partly-linked shrink | `POIS:895-909` | `row.qty = covered`, `refresh_link_state`, note appended | `qty` LOST (no `previous_qty` on this path). |
| Settled in place | `POIS:1122 _settle_row_in_place`: `qty` `1273`, `delivery_date` `1276-1277`, `stock_location` `1278-1279`, `supply_decision_id` `1280`, `order_inquiry_id` `1281`, note append `1283`, `previous_qty`/`previous_delivery_date` `1288-1289`, ack fields `1299-1303` | ONE step recoverable via `previous_*`, only when `changed` (`1269-1271`); depth-1 stack. `ack_state`/`acknowledged_by`, `supply_decision_id` LOST. |
| Settle with zero need | `POIS:1199-1228` | links removed, `state=cancelled`, note appended, `_retire_settled_cancel_balance` | `qty` kept (`1903-1906`); links LOST. |
| Redirected (received doc) | `POIS:1323 _redirect_row_if_received`: note `1359`, `redirected_to_pool = True` `1360`; open links on the row removed `1349` | Flag reversible; removed open links LOST. |
| CANCEL_BALANCE | `POIS:1003-1021` | new row `verb=cancel_balance`, born acknowledged | Insert-only. |
| Retired uncovered rows | `POIS:2179 _retire_uncovered_rows`: `state=cancelled`, note bare assign `2231` or append `2242`, `_unplace_drafts` `2240` | Note LOST on the `raised` branch. |
| Cancel-balance retire on settle | `POIS:2010-2035`, note bare assign `2032` | Note LOST. |
| Supply-borrow asker row | `PSS:5959-5987` | Insert-only. |
| Supply-borrow retire | `PSS:5787` -> `POIS:5619 retire_supply_borrow_rows` | see 1.8 |

`OrderInquiryRow` has no `__audit_track__`.

### 1.8 `projects.order_inquiry_links` + `scm.order_link_claim`

- Drafted by the raise-time cascade: `PSS:5825 _draft_links_for_decision` (def `6217`, SAVEPOINT) -> `POIS:6144 auto_place_for_products(trigger="raise", include_awaiting=True)` scoped to `POIS:3904 row_ids_of_decision` -> `POIS:5416 _write_link` (`5465-5477`), claim via `OLS:1016 claim_placed_on_po` (`POIS:5453-5463`); appends `Linked to ...; auto: <trigger>` to `row.note` and sets `row.actioned_by`/`actioned_at` (`POIS:5446-5448`).
- Deleted by `POIS:6769 _remove_links`: note append `6782-6783`, `OLS:1126 free_claim_if_orphaned` (`6791-6793`), `db.delete(link)` `6794`, clears `actioned_*` when none remain (`6800-6802`). Reached from `_settle_row_in_place` (`1207`, `1257`), `_redirect_row_if_received` (`1349`), `_stamp_rejected` (`3812`), `_unplace_drafts` (`6355`).
- `PCS:3824 _shift_links_off_retired_lines` moves/splits links to the survivor (batch path).
- `defer_auto_place=True` (`PSS:4046`, honoured `5824`) suppresses the cascade on the batch path; batch runs `PSS:6252 auto_place_for_confirmed_products` after.

Pre-image LOST: links and claims hard-deleted, neither audited. Row-note stamps are prose, never parsed back.

### 1.9 `projects.planning_change_rows` / `planning_change_batches` (batch path only)

- Rows: `PCS:4539 applied_state = applied`; `result_json` `4541`, `4546`, `4548-4552`, `4572`, `4574`. Failure: `applied_state='failed'` + `applied_reason` `4709-4711` / `4726-4728`. Supersede of older rows `1079-1080`, `1177-1178`, `4224-4225`.
- Batch: `PCS:4790-4792` `applied_at` / `applied_by` / `result_json`, gated `4789`.
- Board route: `API:707 set_row_decision` (writes `composition_json`) then `API:711 planning_change_service.apply(refuse_if_applied=True, only_pso_ids={order.id})`.

Recoverable-ish: `applied_state` back to `pending`; `from_json` holds the book pre-image (used by `rewind_book`). `result_json` overwritten (usually NULL before).

### 1.10 `sales_order_lines.purchasing_status`

NOT written by confirm (reads only: `app/services/scm/demand.py:176,218,478`, `reorder_run_service.py:1623`, `summary_order_service.py:1087`, `container_request_service.py:510,866`, `project_order_inquiry_import_service.py:303`; column `app/models/order.py:521`).

Confirm DOES write `projects.sales_order_lines.stock_location = fact.own_code` via `PSS:5705 _restamp_stock_location` (def `7210`): overwrite, no pre-image.

### 1.11 audit_logs / integration_log

`audit_logs` covers only `SOSupplyDecision`, `ProjectSalesOrder` (`project_so.py:450`), `OrderChangeNotice` (`:660`). `integration_log` (`app/models/integration.py:113`) has zero references in PSS / POIS / PCS.

### 1.12 Notifications / automations / email

| Side effect | Queued at | Fired at |
|---|---|---|
| `ProjectTask` "Order inquiry <ref>" | `POIS:2681 _hand_to_purchasing` (SAVEPOINT), called `1059-1060` | inline |
| in-app `project_order_inquiry_raised` | `POIS:2726 _notify_purchasing` -> session info key | `POIS:7328 _fire_pending_purchasing_notifications` (`after_commit`, fresh session) |
| automation `order_inquiry_changed_with_links` | `POIS:1781 _dispatch_changed_with_links` (callers `1221`, `1310`, `2246`) | `POIS:7292` (`after_commit`) |
| automation `order_inquiry_handover` (#962) | `POIS:1857 _record_handover` (callers `866`, `991`, `995`, `1022`, `1225`, `1318`, `2033`, `2232`, `2247`) | `POIS:7410 _fire_pending_handover` (`after_transaction_end`, root tx, commit-only via `7373`) |
| batch path purchasing notify | `PCS:4022 _notify_purchasing`, called `4751` | inline |

Trigger specs `app/services/automation_triggers.py:499` and `:533`. Automations are email-only (`automation_service.py:169`, `:868`); runs as `AutomationRun` (`:422`). No Respond.io send on this path. All four irreversible once fired; undo can only send a compensating message.

## 2. How a previous revision is restored today

| Mechanism | Where | What it does |
|---|---|---|
| `supersedes_id` | `PSS:5671`, `6115`; column `project_so.py:1235-1241` | Back-pointer only; nothing reads it to restore (only `tests/test_supply_partial_confirmation.py:250-251`). |
| `superseded_at` / `superseded_reason` | `PSS:4002-4003`, `5621-5622`, `6095-6096`, `6211`; read `PSS:9469`, `PCS:4521` | Display only. |
| `PSS:3989 supersede_for_material_change` | | Retires active revision with no replacement; releases step-3 placements (`PSS:4011`). Forward-only. |
| `PSS:6064 _reissue_without_line` | | Supersedes and mints a fresh ACTIVE revision minus one line, copying allocations (`6122-6146`). Never restores a superseded row to active. |
| `PSS:6146 uncover_lines` | | Same shape via `confirm(lines=[], uncover_line_ids=...)` (`6204-6209`), rewrites `superseded_reason` (`6211`). Forward-only. |
| `_apply_placed_redirect` | gone; comments at `PCS:1772`, `1821` | `redirected_to_pool` written only at `POIS:1360`. |
| `scripts/backfill_retire_superseded_order_inquiry_rows.py` | | Unrelated (merges provisional `sales_orders` rows). |
| `app/services/scm/planning_reset_service.py:36 reset_planning` | | The only undo today: hard DELETE, whole order, all revisions. Order: links -> rows -> inquiries -> `scm.order_link_claim` (`source='order_inquiry'`) -> `so_line_allocations` -> `stock_transfers` -> `so_supply_decisions` -> `planning_change_rows` -> orphaned batches (`:77-104`). `rewind_book=True` restores core + project lines from each batch's `from_json`, newest first (`:85-98`). `db.commit()` `:105`. Untouched: order, lines, POs, SPOs. |

Conclusion: nothing reinstates a superseded revision today. Every existing un-decide writes a new forward revision; the only reverse is `reset_planning`.

## 3. Signals that purchasing acted after a row was raised or settled

| Signal | Written where | Note for the refusal gate |
|---|---|---|
| `ack_state='acknowledged'` + `acknowledged_by/at` | `POIS:3663-3667` (`acknowledge_rows`); also BORN acknowledged on raise `954-957` via `_handshake_for_raise` `1092`, cancel-balance `1017-1019`, supply-borrow `PSS:5983-5985` | WEAK: every row is born acknowledged (G4). `acknowledged_by == confirming CS actor` means born, not read. |
| `ack_state='changed'` + `changed_at` | `POIS:1300-1303` (settle re-stamps then re-acknowledges) | Transient, unreliable. |
| `ack_state='rejected'` + `rejected_*` | `POIS:3799 _stamp_rejected` (`3813-3816`), unlinks first (`3807-3811`), then `3820 _uncover_rejected_line` -> `PSS:6146 uncover_lines` | STRONG. A rejection already wrote its own revision. |
| `actioned_by` / `actioned_at` | set `POIS:5447-5448` (`_write_link`, INCLUDING the auto cascade) and `3589-3590` (`mark_rows`); cleared `6800-6802` | AMBIGUOUS: the confirm's own cascade stamps it. Read with `auto`/`linked_by`. |
| `order_inquiry_links.auto = False` + `linked_by` | `POIS:5474` (`auto=bool(auto_trigger)`; manual `place_on_po` / `place_on_po_allocations` pass no trigger) | STRONGEST per-link signal. Existing predicates `POIS:4354 _cascade_only`, `4377 _only_cascade_links`; rows with a manual link are left alone at `2200-2202`, `817-819`. Reuse verbatim. |
| `state = actioned` (`mark_rows`) | `POIS:3548`, only writer | STRONG. Protected at `889-892`, `2191`, `PCS:3785-3787`. |
| `state = placed` with `po_ref`/`po_line_id` but no link row | `POIS:3583-3585` clears on de-place | SO349754 shape; `_settle_row_in_place` declines it (`1178-1179`). |
| Handover email sent | No OI-side row; only `AutomationRun` (`automation_service.py:422`), `source_id = order_inquiry_handover:<...>` from `POIS:7192` | Weak / indirect. |

## 4. Existing revision-history endpoints and UI

Backend:
- `API:178 GET /plans` -> `PSS:9342 list_decisions`: one row per revision, `state` defaults active, sortable by `revision_no` (`API:189`). Serializer `PSS:9442 _serialize_plan_row` (`revision_no`, `state`, `decided_by_name`, `decided_at`, `line_count`, `components_summary` `9473`, `challenged_reason`). No per-order revision-history endpoint, no undo endpoint.
- Board covered-line payload `project_fulfilment_board_service.py:1991` `revision_no` inside `_line_decision` (`1972`), full frozen composition for Amend. Frozen-reason sentence `2826`.
- Reset: `app/api/v1/scm/sales_orders.py:198 POST /sales-orders/{so_id}/reset-planning` (guard `_WRITE`), body `{rewind_book}`.

Frontend (`sorento_crm_frontend/`):
- "Decided rev N" marker `app/(protected)/project-sales/fulfilment-planning/components/BoardDecidedMarker.tsx:20-52`.
- Revision on the confirmed pill `BoardDecisionPill.tsx:26-35`, `137-190`.
- Amend flow `BoardLineDecisionPanel.tsx:115` (read-only with Amend button, C11), button `816`; helpers `app/(protected)/project-sales/_shared/lib/boardAmend.ts`. Copy at `BoardCellBreakdownDialog.tsx:474`, `FulfilmentBoardListView.tsx:177`.
- Confirm all: `FulfilmentBoardPanel.tsx:804` state, `1692` `AlertDialog`; service `app/(protected)/project-sales/_shared/services/fulfilmentPlanningService.ts:550-564`.
- Reset placement precedent: `app/(protected)/scm/sales-orders/components/SalesOrdersGrid.tsx:882-894` (toolbar item `reset-planning`, `RotateCcw`, gated `canReset` `119`), `ConfirmDeleteDialog` at `1258-1290`, comment `1253-1256` explains the dialog (acts on a SELECTION and collects an answer). A per-order Undo acts on one order and collects nothing, so the deferred-action countdown (D7) is the consistent choice. Service `app/(protected)/scm/services/salesOrderService.ts:264-268`.

## 5. Tests to reuse for red undo tests

Shared fixture factory `tests/test_so_supply_confirmation.py` (30+ importers): `api()` `366-392` yields `(client, world)`, `_World` `355`; `_line_payload` `394`; builders `_sorento` `101`, `_second_company` `105`, `_user` `114`, `_product` `121`, `_warehouse` `142`, `_stock` `173`, `_core_so` `186`, `_core_line` `201`, `_project_so` `221`, `_project_line` `239`, `_classification` `259`, `_reorder_level` `281`, `_spo` `293`, `_client` `313`, `_restore` `337`, `_act_as` `346`.

End-to-end confirm tests:
- `tests/test_so_supply_confirmation.py:580` reconfirm supersedes + increments; `630` race 409; `693` singleton; `957` cross-project claim; `1138` re-confirm no stacked shortfall.
- `tests/test_supply_partial_confirmation.py`: `_decision` `39`, `_two_line_order` `51`, `_snapshot_of` `376`, `rows_of` `488`; tests `216`, `249-251` (asserts `superseded_at` / `supersedes_id`), `384`, `423`.
- `tests/test_project_so_confirm_all_route.py:48`.
- `tests/test_planning_change_apply_on_board.py` (batch path): `world()` `133`, `api(world)` `154`, `_po_line` `180`, `_link` `199`, `_order_row` `212`, `_rows_of` `225`, `_confirm` `234`, `_form_three` `263`, `_apply_from_board` `343`, `_apply_from_the_one_confirm` `752`; tests `359`, `390`, `463`, `707`, `729`, `777`, `801`.
- `tests/test_order_inquiry_draft_links.py:189`, `309`, `350`.
- Also `test_order_inquiry_changed_with_links_automation.py`, `test_order_inquiry_handshake_edges.py`, `test_stock_transfer_reconcile.py`, `test_project_supply_borrow_row_ack.py`, `test_confirm_reserve_guard.py`.

## Pre-image LOST: what an undo cannot recover unless stored first

1. `so_supply_decision_drafts` rows (hard delete `project_line_draft_service.py:368` via `PSS:5765`).
2. `order_inquiry_links` rows (hard delete `POIS:6794`, `_unplace_drafts`, `_shift_links_off_retired_lines`).
3. `scm.order_link_claim` rows (`OLS:1126`, `OLS:1097`).
4. `order_inquiry_rows.note` at three bare-assignment sites (`POIS:858`, `2231`, `2032`); append sites grow unparseable prose (`1146`).
5. `order_inquiry_rows.qty` on the partly-linked shrink (`POIS:898`, no `previous_qty`).
6. `previous_qty` / `previous_delivery_date` beyond one step (`1288-1289`, depth-1, only when `changed`).
7. `order_inquiry_rows.supply_decision_id` before a settle (`1280`).
8. `ack_state` / `acknowledged_by` / `acknowledged_at` / `changed_at` (`1300-1303`).
9. `actioned_by` / `actioned_at` (`5447-5448`, nulled `6801-6802`).
10. `order_inquiries.raised_by` / `raised_at` (`732-733`).
11. `stock_transfers.supply_decision_id` on a KEPT row (`STS:294`).
12. `projects.sales_order_lines.stock_location` (`PSS:7226`).
13. `planning_change_rows.result_json` (`PCS:4541/4548/4574`).
14. Post-commit side effects (`POIS:7292`, `7410`, `7328`, `2703`, `PCS:4022`): already sent.
15. `allocation_claims` shared by a carried row (`PSS:7122`): no column says which decision minted a claim.

Tractable because: `so_supply_decisions.supersedes_id` gives the exact chain, and everything to delete on `so_line_allocations` / newly raised `order_inquiry_rows` / `stock_transfers` is addressable by `decision_id` / `supply_decision_id`. Everything in the list above is not.

## Addendum: second independent pass, 17 Sep (corrections and additions to the sections above)

1. **Two forks reach the DB.** Plain Confirm (no `batch_id`): `API:599-624` -> `PSS.confirm`. Planning-change Confirm (board opened at `?batch=<id>`): same route, `batch_id` set -> `API:646 _confirm_a_planning_change` -> `PCS:4597 apply` -> `PCS:4163 _apply_one_order` -> `PSS.confirm` (`PCS:4417`) PLUS its own writes: `planning_change_rows.applied_state/result_json` (`PCS:4538-4574`), `planning_change_batches.applied_at/by/result_json` (`4789-4794`), `_retire_inquiry_rows` (`4390-4394`, before confirm), `_shift_links_off_retired_lines` (`4455-4457`, link `row_id` repointed), `_execute_reallocations` (`4486-4489`), `_notify_purchasing` (`4752`). Undo must know which fork minted the newest revision; a plain rollback of PSS writes is insufficient on the batch fork.

2. **`auto=False` is NOT proof of purchasing action.** The confirm's own step-3 borrow placement (`POIS:5482 place_supply_borrow` -> `5697 place_on_po_allocations` with `auto_trigger=None`, manual flag at `5735`) writes `auto=False` links with `linked_by = the confirming CS actor`. The unambiguous signals are `order_inquiry_rows.state = 'actioned'` (only `mark_rows`, `POIS:3587-3591`, permission `projects.order_inquiry.action`) and `rejected_by IS NOT NULL` (only `reject_row(s)`, permission `projects.order_inquiries.acknowledge`). A purchasing manual link is `auto=False AND linked_by <> the revision's confirming actor AND the row is not the step-3 ORDER_BACK row that revision minted`. Section 3 above overstated `auto=False`.

3. **`sales_order_lines.stock_location` is partly recoverable**: the previous active revision's `line_snapshots[...]["location"]` (`PSS:6694 _snapshot`) holds the value `_restamp_stock_location` writes, so undo restores it from the prior snapshot. Revision 1 has no prior snapshot; the pre-first-confirm value is lost.

4. **Cancelled `stock_transfers` are findable**: `cancelled_reason = "Superseded by revision N"` names the revision, so undo can locate and restore them by that string plus `project_sales_order_id`. Only `proposed` rows the confirm inserted are safe to delete; `approved` / `moved` rows are a person's action.

5. **Pre-cancel `state` of a cancelled OI row is not stored.** The `was_qty` goes only into the handover email payload in `Session.info`. Undo reconstructs structurally (a row this revision cancelled from `raised` goes back to `raised`).

6. **`allocation_claims`** are stamped `accepted` directly (`PSS:7015`, no `requested` step). `_group_borrow_held_qty` (`PSS:7164`) reads historical claims for netting, so undo deletes the claim row rather than reverting a state, and only when no carried row still points at it.

7. **Extra writes missed by section 1**: `projects.tasks` (one purchasing task per inquiry header, `POIS:2703-2717`, idempotent); `order_inquiries.raised_by/raised_at` re-stamped on reconfirm (`POIS:701-733`); `_raise_borrow_shortfalls` donor-hole rows (`POIS:2053`, writes `2123-2135`, `2154-2176`); `_retire_supply_borrows` (`PSS:5787` -> `POIS:5619`).

8. **No revision-history API or UI exists.** Every `@router` in `fulfilment_planning.py` (`:95-750`) returns the current decision only. `SupplyCompositionSection.tsx:250-256` shows a single "Revision N" label plus challenged (`219-231`) and superseded (`234-243`) banners. `[psoId]/revisions/page.tsx` + `AmendmentReviewClient.tsx` is the book-diff amendment review, a different feature; do not cite it as precedent. Undo introduces the first backward look across `so_supply_decisions`.

9. **Reset planning** (`planning_reset_service.py:36`) deletes unconditionally and never checks purchasing action; it is evidence of the table set, not a template. Route `app/api/v1/scm/sales_orders.py:198-208`; button `SalesOrdersGrid.tsx:885-886`, dialog with rewind checkbox `368-370`, `1255-1290`.

10. **Fixture chain, in call order** (`tests/test_so_supply_confirmation.py`): `_sorento` `101` -> `project_seed_service.run` (in `api` fixture `373`) -> `_user` `114` -> `register_project` (`375-378`) -> `_product` `121` -> `_warehouse` x2 (`own_wh` segment project, `pool_wh` segment dealer, `380-383`) -> `_stock` `173` -> `_core_so` `186` -> `_core_line` `201` -> `_project_so` `221` (pass `so_id=core_so.id`) -> `_project_line` `239` -> `_client` `313` / `api` `366-391` -> `_line_payload` `394` -> POST `f"{BASE}/sales-orders/{order.id}/confirm"` (`BASE` at `42`). Shortest happy path `411-458`; second revision `580-629`; race `630-692`. `tests/test_supply_partial_confirmation.py:25-36` imports the chain and adds `_decision` `39-48`, `_two_line_order` `51-62`.

11. **Disagreement between the two passes, unresolved**: pass one says `_apply_placed_redirect` is gone and `redirected_to_pool` is written only at `POIS:1360`; pass two says PCS references it at `1429`, `1772`, `1821`. Grep before the plan relies on either.
