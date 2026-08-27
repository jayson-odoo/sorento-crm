# PLAN - Order Inquiries: draft links up front, one Confirm, Outstanding PO/SPO

Status: **PHASE 1 DONE** 2026-08-27 (frontend against the section 5 contract, browser-verified on the lane at 1280 and 375; three tagged `PHASE2:` fallbacks listed in section 6). Was: **GO** 2026-08-27 (captain: "proceed, govern phases 1 to 3 till completion"). Rulings R1 to R11 in section 2, R10 = keep. Lane: `.claude/worktrees/scm-oi-draft`, branch `feat/scm-oi-draft-links` off origin/main `a8dda501a`. UAC: `scm-oi-draft-links-acceptance-criteria.md`. Builds on `PLAN-scm-oi-handshake.md` (ack_state, cascade at acknowledge, link horizon) and reverses ONE of its rulings on purpose: the cascade runs again at raise, but what it writes is a draft until purchasing confirms. Page: `/project-sales/order-inquiries`. Lane: this checkout `feat/scm-planning-inline-decisions` is busy with the board; this work wants its own branch off main once #348 is in (main head `a8dda501a`).

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

## 6. Order of work (one PR, three phases per PRINCIPLES.md)

1. Phase 1 FE against mocks: toolbar (Actions / Start), column rename + draft icon + location + late days + Not found, Confirmed column, State column and filter removed, default To confirm chip, lightbox for PO and SPO, bulk reject dialog, Auto link all dialog with the date. Browser check at 1280 and 375 with mocked rows. **DONE.** Three fallbacks are tagged `PHASE2:` in the code and must go when their half of section 5 lands: (a) `orderInquiryService.worklistParams` rewrites `ack=to_confirm` to `awaiting` because the backend's filter is a closed set of the four stored states (section 5.2); (b) `orderInquiryWorklist.lateDaysOf` computes the day count from `expected_date` minus the row's date when `late_days` is absent (section 5.1); (c) `orderInquiryService.rejectOrderInquiryRows` loops the per-row endpoint until `POST /order-inquiries/reject` exists (section 5.6). Not fallbacks but not observable yet either: the draft icon (no unconfirmed row carries a link until the raise-time cascade of section 5.5), the lightbox's Allocated to panel (reads "No allocations yet" until section 5.1) and the SPO lightbox body (404s to a friendly empty state until section 5's new route). One shared-component fix was needed on the way: `DataGridListToolbar`'s left cluster had no `grow`, so it was sized at its own basis and wrapped Columns and Refresh onto a second row at 1280 with ~300px of empty toolbar beside them; AC-D13 cannot hold without it, and every other listing gets the same repair.
2. Phase 2 BE test-first in this order: (a) `late_days` + SPO location fallback + `to_confirm`; (b) re-deal + raise-time cascade; (c) reject drops links + batch reject; (d) SPO intake from the outstanding book; (e) SPO detail + PO allocations on the detail. Then wire the FE.
3. Phase 3 `/code-review`, DoD gate, browser evidence on SO404352 (the captain's screenshots) and SO381895.

## 7. Tests

pytest: board confirm raises rows WITH draft links (inverts the handshake test "links NOTHING", rewrite it); draft reads off the row (no column); Confirm keeps the drafts and fills the remainder; Reject unplaces links and frees PO remaining; Auto link all re-deals drafts, never a confirmed row's link; PO confirm cascade re-deals drafts; `to_confirm` filter and facet; `late_days`; SPO location fallback; batch reject with one reason; outstanding book with SPO rows writes open allocations, a second book without them closes them, unknown location keeps the line; SPO detail endpoint; every new field on the wire from list, export and SO detail. vitest: toolbar menus and counts, column readings (draft / confirmed / not found / late N d / location before line label), default chip, lightbox open from PO and SPO, bulk reject dialog validation, Auto link all dialog carries the date.

## 8. Out of scope

Renaming `ack_state` or the permission slug; a link state column; moving SPO documents between tables; the R10 history drop (separate script, needs its own go); any change to the reorder plan's demand rule; the board's decision UI (own plan, `PLAN-scm-planning-inline-decisions.md`).

## 9. Phase 1 (frontend), 27 Aug, commit `512debbb3`

Built against the section 5 contract with four `// PHASE2:` fallbacks (ack `to_confirm` rewritten to `awaiting`, `lateDaysOf` computed client-side, bulk reject looping the per-row endpoint, `toConfirmCount` summed client-side), all removed in Phase 2. Deleted: `OrderInquiryPoDetailPopover`, `OrderInquiryRejectAction`, `OrderInquiryUploadMenu` (+ tests). `OrderInquiryRowActions` kept: the per-project page still mounts it. One shared-component change: `DataGridListToolbar`'s left cluster gained `grow` (it sat at its own 424px basis beside 721px of free space, which is why Columns + refresh wrapped on every listing).

Browser evidence (:3050, sidebar, session `scm-oi-draft-p1`, screenshots `mockups/oi-p1-*.png`): AC-D12 default `?ack=to_confirm` with the chip, cleared state round-trips as `?ack=all`; AC-D13 one row at 1280, no sideways scroll at 375; AC-D14 both menus with counts disabling at 0; AC-D15 headers, State column + filter gone; AC-D16 SRTSC07 reads `SPO-2026/08-0015 BRW 1`; AC-D17 `late 31 d`; AC-D2 "Not found (new order)"; AC-D18 PO lightbox at 1280 and 375; AC-D19 SPO lightbox empty state until Phase 2; D6 empty reason refused, no request sent. Draft icon not walkable yet: no unconfirmed row carries a link until the raise-time cascade lands.
