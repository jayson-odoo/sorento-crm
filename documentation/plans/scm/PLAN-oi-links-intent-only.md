# PLAN: the planning side never changes an Order Inquiry document link, it records intent

Status: in progress, small fix track by diff shape (no migration, no auth, no ingest; the
diff is code + tests + docs), on `crew/redeal-closed-po-intent-only` (off PR #1369's
branch, rebased onto main after #1369 merges). Lane REDEAL-CLOSED-PO follow-up.
UAC: `oi-links-intent-only-acceptance-criteria.md` (beside this file).

## The ruling (owner, 29 Sep 2026, verbatim)

> "shrinking a line shouldn't trim its own PO link, the quantity change is still at the
> autocount side by the purchasing, a cancelled line shouldn't directly hand its PO link
> to its sibling, new buy shouldn't get draft PO links also, the PO link is based on
> autocount linkage as source of truth"

Read with the two earlier rulings of the same day (PR #1369): "confirm only records the
intent, and purchasing makes every link change in AutoCount, then synced back to order
inquiries", and "from fulfilment planning, [it] is kind of requesting it to be delayed
while the link is intact, then only purchasing will do the adjustment in the linkage".

The rule: **a planning action (fulfilment board Confirm, planning-change Apply) never
writes, moves, trims or removes a PO or SPO link on an Order Inquiry row. It records the
intent on the row's note and on the batch row's result. Purchasing changes the link in
AutoCount; the sync (`follow_book_for_rows`, `follow_book_repairing`, the importer) is the
writer.** A person's own act at Order Inquiries (Choose document, Unlink, Reject, Unlink
all, the container planner's ticks, CS reserve) is not a planning action and stands
(G3 of `PLAN-oi-links-autocount-truth-24sep.md`).

## Inventory: every writer of `order_inquiry_links` (29 Sep 2026, this branch)

Line numbers on `crew/redeal-closed-po` at 41a1cc0c. `OI` is
`app/services/project_order_inquiry_service.py`, `PC` is
`app/services/planning_change_service.py`.

### Planning-side, changed by this lane (intent only)

| # | Writer | What it did | After |
| --- | --- | --- | --- |
| 1 | `OI._settle_row_in_place` :1704 | need reduced to 0: row cancelled AND every link removed | row cancelled, links stay; note says the document stays linked for purchasing |
| 1 | `OI._settle_row_in_place` :1732 to :1757 (AC-P3-8) | linked > need: latest-arrival link trimmed or removed until linked <= need | no trim; `row.qty` is the new need, links stand; note names the over-linked quantity for purchasing |
| 1 | `OI._redirect_row_if_received` :2134 to :2136 (AC-RL-11) | a row with a received link had its still-OPEN links removed before the redirect | open links stay; the redirect, its note and the fresh row are unchanged |
| 2 | `PC._shift_links_off_retired_lines` :3935, :3939, :3983 (AC-P3-6) | a cancelled line's link repointed or split onto a same-order survivor; the leftover removed | nothing moves; one notice per link naming the cancelled line, the document, the quantity and the survivor purchasing may choose in AutoCount |
| 3 | `project_supply_service.auto_place_for_confirmed_products` :7095 (G2 cascade, door `decision_confirm`) | since PR #1220 (S3) the cascade walk writes SUGGESTED links only (`OI._write_suggested_links` :9514); its book step :9286 writes what AutoCount names | already intent-only for the walk; pinned by a test in this lane, no code change |
| D7 | `PC._release_spo_share` :3308, :3311 | a released SPO share's link deleted or trimmed at apply | link stays; the notice records the release for purchasing (same principle, SPO documents are AutoCount documents too) |

### Sync-side (AutoCount is the writer), unchanged

| Writer | Line |
| --- | --- |
| `OI.follow_book_for_rows` (book links, `auto = true`) | :2789 |
| `OI.follow_book_repairing` (AutoCount moved or removed a document: unlink the displaced row, re-offer the named row) | :2432, :2455 |
| `OI._displace_other_line_holders` (AutoCount states the document is for another sales order) | :3057, :3059 |
| `project_order_inquiry_import_service._move_received_links` (OI sheet import), `pair_needs` | :2954 to :2958, :3199 |

### A person's own act at Order Inquiries or the planner, unchanged

| Writer | Line |
| --- | --- |
| Choose document / Link PO: `OI.place_on_po` :8464, `OI.place_on_po_allocations` :8484, `_place_on_po_set` :8637 (`_write_link` :7936) | route `api/v1/projects/order_inquiries.py` :1468, :1491 |
| Unlink `OI.unplace` :9973, Unlink all `OI.unplace_rows` :10015, Reject `OI._stamp_rejected` :6006 | |
| Auto link all / Link selected legacy re-deal `OI._unplace_drafts` :9598 (scheduled for removal, `PLAN-oi-links-autocount-truth-24sep.md` section 8) | |
| Container planner ticks `scm/spo_conversion_service._link_ticked_demand` :2427 | |
| CS reserve `order_inquiry_reserve_service` :858 to :910 (reserve target, not a document) | |
| Undo of a board confirm `project_supply_undo_reconstruct_service` :437 (removes the rows the confirm raised, links with them) | |

### Board-side writers NOT changed by this lane, raised to the owner (crew-ask on the PR)

| Writer | Line | What it does |
| --- | --- | --- |
| `OI.place_supply_borrow` | :8266 | board Confirm step 3 links an ORDER_BACK row to the SPO or PO the ladder borrowed from |
| `OI.release_supply_borrow` | :8305 | a superseded borrow trims or removes that link |
| `OI.retire_supply_borrow_rows` | :8403 | retires ORDER_BACK rows and their links when the borrow leaves the revision |
| `OI._retire_uncovered_rows` | :3746 | a revision that drops a line cancels its still-raised rows; cascade-only legacy links come down with them (`_unplace_drafts`) |

These are the board's own supply-borrow bookkeeping (stock debt and the container planner
read them as placements), not a re-deal. Recommendation: leave them until the owner rules;
if the ruling is "intent only" they get their own lane with the stock-debt readers.

## The change

`OI._settle_row_in_place`:

- `need <= 0`: the row is cancelled and its note gains
  `<documents> stays linked; purchasing adjusts it in AutoCount` after "the book left
  nothing to buy"; `_remove_links` is not called; `_dispatch_changed_with_links` and the
  handover record are unchanged.
- `linked > need`: no trim. `row.qty = need`; `refresh_link_state` reads the row `placed`
  (linked >= qty). The note gains `<qty> over-linked on <documents> stays for purchasing to
  adjust in AutoCount`. `_unlinked_need` already clamps at zero.
- `_redirect_row_if_received`: the `open_links` removal is dropped; everything else
  (`redirected_to_pool`, the note, the cached received links, the fresh row) stands.

`PC._shift_links_off_retired_lines` becomes a recorder: for every cancelled row's link on
a line NOT left for rule 6 it appends to `released_documents`
`<SO> line <n>: <qty> of <doc> stays linked on the cancelled line; purchasing moves it in
AutoCount (<survivor words or "nothing else on this order needs it">), the next sync
brings the new link to Order Inquiries`. No link is repointed, split or removed; no
survivor note; `executed_reallocations` is never written by it. Rule 6 lines keep being
recorded by `_record_redeal_intent` (PR #1369).

`PC._release_spo_share`: records `<SO> line <n>: <qty> of <SPO> stays linked; purchasing
releases it in AutoCount` on `released_documents` and touches no link. The composed label
("Release SPO ... unallocated for purchasing") is unchanged.

`auto_place_for_confirmed_products`: no change; a test pins that a planning-change apply
writes no real link on a fresh Buy row (suggested links only).

## Tests (red first)

`tests/scm/test_planning_change_links_intent_only.py`: AC-IO-1 to AC-IO-6. Rewritten to
the ruling: `tests/scm/test_planning_change_reallocation.py` (the survivor-shift tests),
`tests/test_planning_changes.py` (the SO397450 advance shape, the qty-up no-decision
shape), `tests/test_planning_change_apply_on_board.py`, `test_planning_change_diff_parity.py`
where they asserted a trim, an unlink or a shift. Every reversal is recorded beside the
test, never deleted.

## Out of scope

The board-side borrow writers above (asked), the manual and sync writers (stand by
ruling), `_unplace_drafts` (its own removal is already scheduled).
