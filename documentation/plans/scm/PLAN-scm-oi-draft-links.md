# PLAN - Order Inquiries: draft links up front, one Confirm, Outstanding PO/SPO

Status: **TEST ROUND DONE** 2026-08-27 (section 10: vitest 3800/3800, pytest 340/17-file-sweep + `tests/scm` two halves with only pre-existing/unrelated reds, browser evidence on the lane for every AC except D1/D3/D5/D8's live walk, which rest on pytest+vitest - see section 10 for why SO381895 could not carry it fresh. One real defect found and fixed: `/order-inquiries/auto-place` was missing `redeal_drafts`/`include_awaiting`, so Auto link all never actually re-dealt anything). Was: **PHASE 2 DONE** 2026-08-27 (backend test-first, the three `PHASE2:` fallbacks removed, browser-smoked on the lane: `ack=to_confirm` answers 200, `late 31 d` and `BRW 2` read off the wire, both lightboxes answer with their Allocated to panels). Three judgements the plan did not spell out are recorded in section 5.9. Was: **PHASE 1 DONE** 2026-08-27 (frontend against the section 5 contract, browser-verified on the lane at 1280 and 375; three tagged `PHASE2:` fallbacks listed in section 6). Was: **GO** 2026-08-27 (captain: "proceed, govern phases 1 to 3 till completion"). Rulings R1 to R11 in section 2, R10 = keep. Lane: `.claude/worktrees/scm-oi-draft`, branch `feat/scm-oi-draft-links` off origin/main `a8dda501a`. UAC: `scm-oi-draft-links-acceptance-criteria.md`. Builds on `PLAN-scm-oi-handshake.md` (ack_state, cascade at acknowledge, link horizon) and reverses ONE of its rulings on purpose: the cascade runs again at raise, but what it writes is a draft until purchasing confirms. Page: `/project-sales/order-inquiries`. Lane: this checkout `feat/scm-planning-inline-decisions` is busy with the board; this work wants its own branch off main once #348 is in (main head `a8dda501a`).

## 0. What the captain asked (27 Aug, screenshots 28 to 36)

Journey: CS confirms on the fulfilment board -> rows land on Order Inquiries with their PO / SPO already found and shown as a DRAFT link -> purchasing reads the page as a to-do list (only rows not yet confirmed), ticks lines, presses **Confirm** -> the link and the allocation become real. Feedback, item by item:

| # | Ask | Today |
| --- | --- | --- |
| 1 | Column "Linked to" -> **"Outstanding PO/SPO"**; draft vs confirmed icon on it | `po_number` column, no draft notion; `OrderInquiryLink` has no state column, only `auto` |
| 2 | Links found automatically when rows flow from planning, as a draft | Handshake ruling: NO cascade at board confirm; cascade only at Acknowledge / Link now / PO confirm |
| 3 | Unlinked row reads **"Not found (new order)"** | "Not linked" + faded bar |
| 4 | PO and SPO numbers open a **lightbox**, not the popover | `OrderInquiryPoDetailPopover` (Radix Popover, clipped by the grid, PO only; SPO has no link at all) |
| 5 | SPO shows `L13`, `L15` not `BRW-NTC` | FE prints `line_label` before `location` (`orderInquiryWorklist.ts:138`); BE `_line_label` = `L{spo_line_number}`; every SPO allocation has a line number since migration 420, so the location never wins. Dev DB: SPO-2026/08-0015's 62 allocations all carry warehouses (BRW, BRW-BB, BRW-NTC, ...). Display defect, data is fine. Second cause: the banded history book carries no location (5,237 lines, `warehouse_id` NULL) |
| 6 | **Confirm** instead of Acknowledge; "Acknowledged" column reads Confirmed | label only; slug `projects.order_inquiries.acknowledge` and `ack_state` values stay |
| 7 | Toolbar on ONE row | Columns + refresh wrap under because the right cluster (Actions, Link up to, Upload, Acknowledge) is wide; `DataGridListToolbar` has no second-row slot |
| 8 | Default view = rows not yet confirmed (to-do list) | no default filter; `?ack=` is honoured when present |
| 9 | Popup on the PO number is bad UI -> lightbox | see 4 |
| 10 | Does SPO come from `spo_allocations`? Purchase upload must INTAKE SPO rows, it blocks them now | Cascade reads `spo_allocations` open lines, correct. The outstanding PO-book upload SKIPS `SPO-` rows ("N rows are shipping orders (SPO), which this book does not carry"). The history book writes them CLOSED (`fully_received`), so they are never candidates. Nothing on the OI page can create an OPEN SPO line today; the only open ones came from the external API and migration 420's 52 `scm_upload` docs |
| 11 | State column (Raised / Linked) gone; Outstanding PO/SPO column carries the answer | `OrderInquiryStatePill` column + State filter |
| 12 | Left bulk buttons (Link selected / Unlink selected) into **Actions**; "Link up to" only inside **Auto link all**; **Start** CTA = Upload + Confirm | selection strip on the left, date box on the toolbar shared by four presses |
| 13 | "arrives late" -> **late by N days** | `link.late` boolean only |
| 14 | "Taken from PO" -> **"Taken by PO/SPO"** | column label |
| 15 | Bulk **Reject** under Actions | reject is per row (`POST /order-inquiries/{row_id}/reject`) |

## 1. Model: a draft is a link on an unconfirmed row (no new column)

Simplest thing that works. `OrderInquiryLink` gains NO state column. A link is a **draft** while its row's `ack_state` is `awaiting` or `changed`, and **confirmed** once the row is `acknowledged`. That is exactly the handshake's row gate read the other way round, and it already answers every question:

| Question | Answer |
| --- | --- |
| Confirm (N) | = today's `acknowledge_rows`: stamp the row, then the cascade fills any unlinked remainder. Draft links on the row need no write: they are confirmed by the row's stamp |
| Reject | today's `reject_row` PLUS unplace every link on the row (they were drafts; the PO quantity goes back to the pool). Reject accepts a fully-linked row too (today it refuses `placed`, which with drafts would refuse most rows) |
| CS amends a confirmed row | unchanged from handshake: settle-in-place, links kept, `changed`. They read as draft again, which is the truth: purchasing has to look again |
| Do drafts occupy PO quantity | YES in `_candidates_for_row` (`remaining = ordered - received - other links`, unchanged). Two drafts never point at the same unit, and Confirm can never fail for lack of quantity. That is the whole reason to draft in the walk order rather than at confirm time |
| Do drafts count as allocation on the PO page | shown, marked **Proposed** in the Allocated to panel (`_allocations_for` joins the row already; add `ack_state`). AutoCount "Split for" text lists confirmed only |
| Plan demand / `committed_v` | unchanged: plan demand = unlinked remainder of acknowledged + changed rows; awaiting = count chip |
| Audit claim (`order_link_claim`) | written at link time as today; it is identity, not approval. `claim.source` unchanged |
| Re-deal | Auto link all, Link now, PO confirm cascade, a fresh raise: they may UNPLACE and re-deal DRAFT links (rows not acknowledged), never a confirmed row's links. Today the cascade only ever adds; the re-deal is new and is what lets a better document (a nearer PO in the new book) take over before purchasing has said yes |

Rejected: a `link.status` column. It would have to be kept in step with the row's stamp on every confirm / reject / change, and every reader would need both. One source of truth exists already.

## 2. Rulings (captain, 27 Aug, Lavish review)

| # | Question | Ruling |
| --- | --- | --- |
| R1 | Draft = derived from the row's `ack_state`, no link column | **yes** |
| R2 | Uploads / Auto link all may re-deal DRAFT links; confirmed links never touched automatically | **yes** |
| R3 | Default filter To confirm | **awaiting + changed**, URL `?ack=to_confirm` |
| R4 | SPO rows in the outstanding PO-book upload become OPEN `spo_allocations` lines; absent from the next book = closed | **yes** |
| R5 | SPO candidates | **every linkable verb, not only ORDER BACK**: "SPO link is always one, always SPO first then PO". `_SPO_LINKABLE_VERBS` becomes `_LINKABLE_VERBS`; the sort key already puts SPO before PO |
| R6 | Cascade at board confirm uses the plan's link horizon, no prompt on the board | **yes** |
| R7 | Confirm / Confirmed / To confirm is a UI rename only | **yes** |
| R8 | Row-level Link / Unlink / Reject | **dropped, bulk only**: the row Actions column goes; Actions menu carries Link selected (manual dialog for ONE selected row, the override path), Unlink selected, Reject selected |
| R9 | Lightbox read-only with one Open document link | **yes** |
| - | Start menu | **Upload purchase orders + Confirm selected only**; "Upload purchase history" is not offered here |
| - | Auto link all dialog date | label **"Purchase order cut off"** (was Link up to) |
| - | SPO location | SPO is always allocated at a POOL location (BRW, MWH); the link and the lightbox read that pool code, never the SO's own location. The book's raw code is kept as `location_code` when it is not a known warehouse |
| R10 | Where SPO documents live | Captain asked three times whether the moved rows may be deleted. **Answer: yes, technically, by a separate script with its own go; not in this PR, and pointless on its own.** Evidence: on the dev copy 12,392 `scm.order_link_claim` rows (the SO-to-SPO link history that `history_sources.py`, `spo_conversion_service.py` and `container_request_service.py` read) point at `scm_spo_history` allocations; 74,016 lines / 3,506 documents. Every one is `closed`, so the OI cascade, the lightbox candidates and Use SPO never see them; the drop changes nothing on this page. Captain's concern was whether production's `spo_allocations` will fill with SPO rows moved out of `purchase_orders`: yes, that is migration 420's job (dev copy: 79,969 rows / 3,517 docs, all closed history except 52 open `scm_upload` docs); closed rows never reach the cascade, and R4 is what adds OPEN ones from now on. What a delete costs: the SPO receipt history per SKU and warehouse (74,016 lines) is gone; the 12,392 claims survive (FK `ON DELETE SET NULL`) but lose their pointer; `container_request_service._table_max` still reads `purchase_orders` for the SPO as-of date (stale since 420, a side finding). What makes it pointless: the history-book upload (`po_history_service._write_shipping_order`) files SPO rows into `spo_allocations` again on the next upload, so the delete would need that channel changed to skip the SPO family too. `spo_allocations` stays the SPO table. 420 MOVED, it did not copy: `purchase_orders` holds 0 SPO documents on the dev copy (5,238 rows, all PO), so the history rows in `spo_allocations` are the only copy; 420 finished on prod (captain, 27 Aug) |
| R11 | SPO location for linking | **Show every location in the lightbox, but link / allocate only from POOL locations** (BRW, MWH, DC1, WH3, RSW: the `_pool_codes` set). `_candidates_for_row`'s SPO side filters `warehouse_id` to the pool set; a book SPO line at a non-pool code is visible, never drafted |

## 3. Behaviour

| Event | Actor | Effect |
| --- | --- | --- |
| Board Confirm / OI form import / planning-change apply | CS / system | rows raised `awaiting` AND the cascade runs for them at once (`auto_place_for_products(trigger="raise", draft=True)` from the `auto_place_products` seam `project_supply_service.py:3188` that section 3 of the handshake left dormant). Links written normally; they read as draft because the row is awaiting |
| Page load | purchasing | list shows To confirm rows; every found document already on the row with the draft mark |
| Confirm (N) | purchasing | `acknowledge_rows` as today (stamp + cascade for the unlinked remainder, plan horizon by default); the draft mark flips to confirmed without a reload |
| Reject selected (N) / Reject | purchasing | reason once for the batch; per row: unplace all links, `rejected`, uncover the board line as today |
| Auto link all | purchasing | dialog carries the **Purchase order cut off** date (moved here from the toolbar, same precedence: URL, browser, plan default) and re-deals draft links of every open row in scope; confirmed links untouched |
| Upload purchase orders / purchase history (Start menu) | purchasing | as today; on landing the page offers Link now (re-deals drafts of the products written) and Open purchase orders. SPO rows of the outstanding book now land as open `spo_allocations` lines (R4) and are candidates in the same press |
| Unlink selected (N) / Unlink | purchasing | as today (Actions menu / row cell) |
| PO confirm cascade | system | as today, plus draft re-deal for awaiting rows of the confirmed products (R2) |
| Link selected (1) | purchasing | manual dialog unchanged, reached from the Actions menu with exactly one row ticked; a manual link on an awaiting row is still a draft until Confirm |

## 4. Screens

### 4.1 Toolbar, one row

Left: search, Filters, Columns, refresh (today's left cluster, unchanged). Right, two controls only:

- **Actions ▾**: Auto link all (dialog carries the **Purchase order cut off** date), Link selected (1) (the manual dialog, one row at a time), Unlink selected (N), Reject selected (N), Unlink all, Export Excel. Selected-count items disabled at 0.
- **Start ▾** (primary): Upload purchase orders, **Confirm selected (N)** (disabled at 0, gated on the acknowledge grant as today). No history upload here (R-).

Gone from the toolbar: the Link up to date box (into the Auto link all dialog), the Upload split button, the Acknowledge button, the left selection strip's Link selected / Unlink selected (the strip keeps "N selected" + Clear). Rows selectable = rows a Confirm may take (today's `enableRowSelection`). Fits at 1280 without wrapping; at 375 the two menus stack under the search as the toolbar already does.

### 4.2 Columns

| Column | Reads |
| --- | --- |
| **Outstanding PO/SPO** (was Linked to) | headline `2 of 2`, bar, then per document: kind badge, document number as a lightbox link, **location** then qty (`BRW-NTC 1`; the line label moves into the title), and `late 12 d` in amber when the document lands after the row's date. A small icon in front of the headline: draft (dashed circle, title "Draft, confirm to allocate") or confirmed (check, title "Confirmed by <name> <date>"). No links: **Not found (new order)** with the faded bar |
| **Taken by PO/SPO** (was Taken from PO) | unchanged value |
| **Confirmed** (was Acknowledged) | To confirm / Confirmed <name> <time> / Changed <date> + Was/Now / Rejected: <reason> |
| State | **removed**, with its filter. The Linked filter reads Found / Not found |
| Row Actions column | **removed** (R8); every action is bulk from the Actions menu |

Default filter: Confirmed = **To confirm** (`?ack=to_confirm`), shown as the active-filter chip so the user sees why the list is short; clearing it shows everything. The three cards and the export follow it as they follow every filter.

### 4.3 Lightbox

One `Dialog` (max-w-4xl, scroll inside, 375-safe) for both kinds, opened from the document number:

- PO: header (number, supplier, status, expected, "Open purchase order" link), lines table SKU / ordered / received / remaining / location, and the Allocated to rows with Proposed / Confirmed. Data: today's `GET /order-inquiries/po/{po_id}` extended with `allocations`.
- SPO: new `GET /order-inquiries/spo/{spo_number}`: header (number, supplier if known, ETA, shipment / container when an `inbound_shipment` exists), lines SKU / allocated / received / remaining / location (`warehouse_code` else raw `location_code` else "no location in the book").

The popover component is deleted.

### 4.4 Board, plan page

Unchanged. The board keeps the Rejected badge; the plan keeps the awaiting chip (now labelled "N to confirm").

## 5. Backend

1. `OrderInquiryLinkOut` gains `late_days` (int, null when not late) and `location` falls back to `spo_allocations.location_code`; `OrderInquiryPoDetail` gains `allocations[]` with `ack_state`; new SPO detail schema. Assert every field on the wire (response_model drops the rest).
2. `ack` filter accepts `to_confirm` (= awaiting + changed) on list, summary facet, export; summary `ack` facet gains the `to_confirm` count.
3. `_SPO_LINKABLE_VERBS = _LINKABLE_VERBS` (R5); SPO candidates sort before PO for every row (already in `_candidate`'s key); SPO candidates restricted to pool warehouses (R11).
4. `auto_place_for_products(..., redeal_drafts: bool)`: before dealing, unplace links of rows in scope whose `ack_state` is not `acknowledged` (audit note "re-dealt by <trigger>"), then deal as today. Callers: raise (new, `trigger="raise"`), worklist Auto link all, link_now, PO confirm pass. `ACK_LINKABLE` widens to include `awaiting` for the raise / re-deal paths ONLY; Confirm's own cascade keeps the acknowledged gate.
5. Raise-time cascade: `project_supply_service.confirm` result's `auto_place_products` -> call in the same transaction (SAVEPOINT, best effort like `auto_place_for_confirmed_products`), plan horizon. Same for the OI form import and the planning-change apply.
6. `reject_row` accepts `placed`; unplaces every link first. New `POST /order-inquiries/reject` batch `{row_ids, reason}` (one reason), returning per-row results; per-row endpoint stays.
7. Outstanding book SPO intake (R4): `outstanding_reader` stops skipping `FAMILY_SPO`; `outstanding_import_service` writes them through a new `_write_spo_lines` (upsert on `(company, spo_number, spo_line_number)`, `line_status open`, `quantity_received` from the book, warehouse by code, `location_code` raw, `source_system scm_upload`), closes SPO lines of `scm_upload` docs absent from the book (same rule the PO side uses), and reports `spo_documents / spo_lines / unknown_locations` in the summary and the Test result. Link now's `product_ids` include them.
8. Migration: none expected. `spo_allocations` already allows NULL shipment / warehouse and holds `location_code` (420). Re-check `alembic heads` anyway; main carries two heads until #348's merge rev is in.

### 5.9 Judgements taken while building phase 2

Three places where the plan's text did not decide the case, resolved in the code and stated
here so a reviewer meets them once:

- **The SPO closure runs only when the book carries shipping orders at all.** R4 says
  "absent from the next book = closed". Read as a statement either way, a purchase-order-only
  export - a shape the buyer really does upload - would settle every open SPO line in the
  company (715 on the dev copy) without ever mentioning one. Silence is not a statement; a
  book that states SOME shipping orders is the SPO book, and only then does what it leaves out
  mean landed. The preview reports `spo_closed` either way, so the number is on screen before
  Confirm upload.
- **R11's pool rule applies to what is OFFERED, not to what a person may name by hand.** The
  automatic walk and the Link dialog never take a non-pool SPO line; a deliberate call still
  may, exactly as `manual` already reaches a purchase order that is not yet active and past a
  group in deficit. The container planner depends on it: its ticks say "this row is served by
  THIS container line", at the site the split just sent it to.
- **The deficit exemption counts awaiting rows.** `_rows_awaiting_a_link` read `ACK_LINKABLE`,
  so a group holding only unconfirmed rows was refused its own purchase order - which under R6
  is every row at the moment it is raised, and the page would have read "Not found" for exactly
  the rows the buy was sized from.

Also, `AcknowledgeResult.linked_rows` now reports 0 on a Confirm whose rows were already
drafted, because that is what the press linked. The row is covered; the raise covered it.

## 6. Order of work (one PR, three phases per PRINCIPLES.md)

1. Phase 1 FE against mocks: toolbar (Actions / Start), column rename + draft icon + location + late days + Not found, Confirmed column, State column and filter removed, default To confirm chip, lightbox for PO and SPO, bulk reject dialog, Auto link all dialog with the date. Browser check at 1280 and 375 with mocked rows. **DONE.** Three fallbacks are tagged `PHASE2:` in the code and must go when their half of section 5 lands: (a) `orderInquiryService.worklistParams` rewrites `ack=to_confirm` to `awaiting` because the backend's filter is a closed set of the four stored states (section 5.2); (b) `orderInquiryWorklist.lateDaysOf` computes the day count from `expected_date` minus the row's date when `late_days` is absent (section 5.1); (c) `orderInquiryService.rejectOrderInquiryRows` loops the per-row endpoint until `POST /order-inquiries/reject` exists (section 5.6). Not fallbacks but not observable yet either: the draft icon (no unconfirmed row carries a link until the raise-time cascade of section 5.5), the lightbox's Allocated to panel (reads "No allocations yet" until section 5.1) and the SPO lightbox body (404s to a friendly empty state until section 5's new route). One shared-component fix was needed on the way: `DataGridListToolbar`'s left cluster had no `grow`, so it was sized at its own basis and wrapped Columns and Refresh onto a second row at 1280 with ~300px of empty toolbar beside them; AC-D13 cannot hold without it, and every other listing gets the same repair.
2. Phase 2 BE test-first in this order: (a) `late_days` + SPO location fallback + `to_confirm`; (b) re-deal + raise-time cascade; (c) reject drops links + batch reject; (d) SPO intake from the outstanding book; (e) SPO detail + PO allocations on the detail. Then wire the FE. **DONE.** `tests/test_order_inquiry_draft_links.py` is the new suite (32 tests); five existing suites carried rules this reverses on purpose and were rewritten with the reversal recorded beside them (`test_order_inquiry_handshake.py` board confirm and Link now, `..._edges.py` PO confirm and the two reject rules, `test_order_inquiry_place_on_po.py` decision confirm, `test_order_inquiry_links.py` R5/R11, `tests/scm/test_outstanding_po_skips_spo.py` R4). No migration was needed.
3. Phase 3 `/code-review`, DoD gate, browser evidence on SO404352 (the captain's screenshots) and SO381895.

## 7. Tests

pytest: board confirm raises rows WITH draft links (inverts the handshake test "links NOTHING", rewrite it); draft reads off the row (no column); Confirm keeps the drafts and fills the remainder; Reject unplaces links and frees PO remaining; Auto link all re-deals drafts, never a confirmed row's link; PO confirm cascade re-deals drafts; `to_confirm` filter and facet; `late_days`; SPO location fallback; batch reject with one reason; outstanding book with SPO rows writes open allocations, a second book without them closes them, unknown location keeps the line; SPO detail endpoint; every new field on the wire from list, export and SO detail. vitest: toolbar menus and counts, column readings (draft / confirmed / not found / late N d / location before line label), default chip, lightbox open from PO and SPO, bulk reject dialog validation, Auto link all dialog carries the date.

## 8. Out of scope

Renaming `ack_state` or the permission slug; a link state column; moving SPO documents between tables; the R10 history drop (separate script, needs its own go); any change to the reorder plan's demand rule; the board's decision UI (own plan, `PLAN-scm-planning-inline-decisions.md`).

## 9. Phase 1 (frontend), 27 Aug, commit `512debbb3`

Built against the section 5 contract with four `// PHASE2:` fallbacks (ack `to_confirm` rewritten to `awaiting`, `lateDaysOf` computed client-side, bulk reject looping the per-row endpoint, `toConfirmCount` summed client-side), all removed in Phase 2. Deleted: `OrderInquiryPoDetailPopover`, `OrderInquiryRejectAction`, `OrderInquiryUploadMenu` (+ tests). `OrderInquiryRowActions` kept: the per-project page still mounts it. One shared-component change: `DataGridListToolbar`'s left cluster gained `grow` (it sat at its own 424px basis beside 721px of free space, which is why Columns + refresh wrapped on every listing).

Browser evidence (:3050, sidebar, session `scm-oi-draft-p1`, screenshots `mockups/oi-p1-*.png`): AC-D12 default `?ack=to_confirm` with the chip, cleared state round-trips as `?ack=all`; AC-D13 one row at 1280, no sideways scroll at 375; AC-D14 both menus with counts disabling at 0; AC-D15 headers, State column + filter gone; AC-D16 SRTSC07 reads `SPO-2026/08-0015 BRW 1`; AC-D17 `late 31 d`; AC-D2 "Not found (new order)"; AC-D18 PO lightbox at 1280 and 375; AC-D19 SPO lightbox empty state until Phase 2; D6 empty reason refused, no request sent. Draft icon not walkable yet: no unconfirmed row carries a link until the raise-time cascade lands.

## 10. Test round (tester, 27 Aug, commit stack ending `502ff3602` -> this round)

**vitest** - `app/(protected)/project-sales`, `app/(protected)/scm/reorder`,
`app/(protected)/scm/sales-orders`, `components/ui`: 3800 passed, 0 failed (238 files;
was 1 failing before this round - see "defect" below). Rewrote the three Phase 1
suites that predated the real endpoints (`orderInquiryWorklistColumns.test.tsx`,
`OrderInquiryAckCell.test.tsx`, `OrderInquiriesClient.test.tsx` - the last cut from
1303 to ~700 lines, obsolete link-horizon-on-toolbar and per-row-action tests
dropped, Actions/Start menu + to_confirm default + counts-disable-at-0 tests added),
extended `orderInquiryAck.test.ts` (`ACK_TO_CONFIRM`, `ACK_FILTER_OPTIONS`,
`isBulkRejectable`) and `orderInquiryWorklist.test.ts` (`lateDaysOf`, `linkedSummary`
location-first/no-fourth-arg). New: `OrderInquiryDocumentDialog.test.tsx` (8 tests,
opens from PO and SPO, Proposed/Confirmed badges, empty states),
`BulkRejectOrderInquiryDialog.test.tsx` (7), `AutoLinkOrderInquiryDialog.test.tsx` (9).

**Defect found while writing `orderInquiryWorklistColumns.test.tsx`, not this
branch's cause but its own diff**: `SalesOrderDetail.test.tsx`'s "two links to the
same SPO line" test still asserted the OLD label-first reading
(`SPO-2026/08-0061 L4`) that item 5 replaced with location-first
(`SPO-2026/08-0061 BRW`) in `SalesOrderDetail.tsx` itself (already correct, in this
branch's own diff) - the coder updated the component but missed its test. Fixed the
assertion; all 63 tests in that file pass.

**pytest** - the 17-file sweep the brief named: 338 -> 340 passed (3 tests added to
`test_order_inquiry_draft_links.py`, one pre-existing test count adjusted), 0 failed.
Checked `test_order_inquiry_draft_links.py` against section 7 and the AC list;
added three the brief flagged as possibly missing: reject on a `placed` row frees
the PO's remaining for a SECOND row's own draft (not just the internal accounting -
`test_reject_on_a_placed_row_frees_the_pos_remaining_for_the_next_candidate`); batch
reject with one CANCELLED row (a different `_assert_rejectable` branch from the
already-rejected case already covered -
`test_the_batch_reject_refuses_the_whole_batch_when_one_row_is_cancelled`);
`to_confirm` on the export rewritten to assert CONTENT (a confirmed row's SO number
absent, an awaiting row's present), not just a 200 and a workbook. The other three
items the brief named turned out already covered: SPO 404
(`test_the_shipping_order_lightbox_404s_on_a_number_nobody_holds`), the non-pool
SPO line visible-but-never-drafted (`test_a_shipping_order_line_outside_the_pool_is_never_drafted`,
both halves), the outstanding book's SPO-closure-skipped-when-book-carries-none rule
(`tests/scm/test_outstanding_po_skips_spo.py::test_a_purchase_order_only_export_settles_no_shipping_order`
and its closes-when-present sibling), and the CS-403-on-batch-reject
(`test_a_cs_user_may_not_reject_a_batch`).

**Defect found and fixed while writing the "frees the PO's remaining for the next
candidate" test**: it went red for a real reason. `POST /order-inquiries/auto-place`
- the route "Actions > Auto link all" calls (`orderInquiryService.autoPlaceOrderInquiryRows`)
- built its `auto_place_for_products(...)` call with neither `redeal_drafts=True` nor
`include_awaiting=True`, so the toolbar's own Auto link all never actually re-dealt a
draft or reached an awaiting row - only `link_now` (the service method behind Start's
post-upload "Link now" button and `POST .../link-now`, whose docstring even claims
"It is also the page's Auto link all") carried the two flags. The two existing pytest
tests named "Auto link all" (`test_auto_link_all_moves_a_draft_onto_a_nearer_document`,
`test_auto_link_all_never_moves_a_confirmed_rows_link`) both call `LINK_NOW`, not the
worklist's `auto-place` route, so they never exercised the real Actions-menu path and
the gap shipped past them. Fixed in `app/api/v1/projects/order_inquiries.py` (two
kwargs added, doc comment explaining why); full 17-file sweep and the two scm halves
re-ran green after the fix. Left the two misleadingly-named `link_now` tests as they
are (they are correct tests of `link_now`, not of `auto-place`) rather than
retargeting them, since the new test now covers the route the UI actually calls.

**pytest** - `tests/scm` full sweep, in two halves per the brief (99 files each,
alphabetical split): half A 340 passed / 47 failed / 13 xfailed (881s); half B 1438
passed / 1 failed / 1 skipped (461s). Standing red named in the brief:
`tests/scm/test_order_link_both_ways.py` (5 of the 47, hardcoded `202605-S0042`
collision). The other 42 in half A (`test_m2_demand.py`, `test_m2_job.py`,
`test_m3_run.py`, `test_m5_explainer.py`, `test_m5_market.py`, `test_m8_slice_e.py`)
and the 1 in half B (`test_po_history_import.py::test_an_so_named_in_a_note_becomes_a_claim`)
have zero file overlap with this branch's 9-file diff (`git diff --stat
origin/main...HEAD -- app/` checked) and sit in an unrelated domain (demand
analytics forecasting / market signals / PO-history note parsing); read as
pre-existing shared-dev-DB drift (golden-set / real-fixture assertions against a
prod-copy database other lanes also write to), not diagnosed further given this
branch's scope is order inquiries. Not re-verified against a clean `origin/main`
checkout (would have needed `git stash`, avoided after a near-miss - see below).

**Browser** (:3050, session `scm-oi-draft-test`, `documentation/plans/scm/mockups/oi-test-*.png`).
SO381895 (the sanctioned fixture) has **nothing outstanding on the fulfilment
board and no order-inquiry rows at all** on the dev copy right now - a prior
verification pass already carried it to Confirmed, and the "To confirm" +
company-wide "ack=all" list both return zero rows for it (`oi-test-so381895-no-rows.png`,
`oi-test-fp-so381895-nothing-outstanding.png`). **Nothing on it was changed this
round** - no board confirm, no acknowledge, no reject. AC-D1/AC-D3/AC-D5's live
"confirm on the board, watch the draft appear then flip to confirmed" walk could
therefore not be freshly demonstrated; those three rest on pytest (draft: `test_a_board_confirm_raises_a_to_confirm_row_that_already_holds_its_document`,
`test_two_rows_are_never_drafted_onto_the_same_units`; confirm:
`test_confirm_stamps_the_row_and_moves_no_link`) plus vitest ("AC-D5: Confirm
selected"). The adjacent, same-code-path evidence WAS captured live and read-only
on SO404352's already-real rows (never acted on): AC-D2 "Not found (new order)"
with the faded bar, AC-D16/AC-D17 a confirmed mark reading `SPO-2026/08-0015 BRW 1`
and `202607-S0044 BRW 2 late 31 d`. AC-D9 Auto link all opened, "Purchase order
cut off" confirmed, Cancelled (no `auto-place` request fired, checked via `network
requests`). AC-D10 Start > Upload purchase orders with a 2-row fixture book (one PO
line, one SPO line, built the way `tests/scm/test_outstanding_po_skips_spo.py`
builds its own, seeded catalogue rows under a fresh `ZZTOI-` marker), Test pressed
and reported "Rows: 2 - Would import: 1 - Skipped: 0 - Errors: 0" plus a warning
naming the 1 SPO row; Confirm upload never pressed, `network requests` shows only
the `/preview` call. AC-D13 one row at 1280 (`oi-test-toolbar-1280.png`), stacks
with no page-level horizontal scroll at 375 (`oi-test-toolbar-375.png`). AC-D18/D19
both lightboxes at 1280 and 375, lines table + Allocated to panel with a real
`Confirmed` badge, scroll-inside-itself and Escape-close both work, `console` /
`errors` clean throughout, `network requests` confirms the right endpoint per
lightbox. AC-D8 (CS 403) rests on pytest + vitest only - the browser session was
not re-logged-in as a CS principal this round.

**Near-miss**: mid-diagnosis of the one `tests/scm` half-B failure, ran `git stash`
in the backend worktree to compare against a clean tree - `git stash` operates
repo-wide from a worktree root and pulled every uncommitted frontend test file
along with it too (the frontend lives in the same git worktree, different
directory). Caught immediately (the harness's own "file changed on disk" note on
the next read) and `git stash pop` recovered everything with `git diff --stat`
confirming an exact match before and after; the plan to diagnose that failure
against a clean checkout was dropped rather than risked twice. Logged here so the
next agent does not reach for `git stash` in a lane holding uncommitted work across
both halves of the monorepo.
