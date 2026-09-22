# OI Request CS to reserve - round 2 browser verification evidence

Stack: FE http://localhost:3080 (Next dev, HMR), BE http://localhost:8080, DB `sorento_oireserve_stack`.
Worktree: `/Users/tehjayson/Documents/foundryx/sorento_crm-oi-reserve`.

**Environment note:** the worktree was told to be at HEAD `6af11c7fc`, but at the start of this
walk it was already at `64ea26cbb` plus uncommitted changes to
`sorento_crm_backend/app/schemas/project_order_inquiry.py` and
`sorento_crm_backend/app/services/order_inquiry_reserve_service.py` (confirmed via `git diff`:
security-review SF-9 fixes - `Decimal("nan")`/`"inf"` guards and a `.with_for_update()` row lock -
nothing touching the grid response fields). A live coder/reviewer was evidently still committing
to this exact worktree while this pass ran (Fast Refresh fired twice, backend restarted under
`--reload`). None of the failures below trace to those two files; they are noted for the record,
not as an excuse.

**OI-001072 state found:** on arrival, none of its ~110 lines (5 pages) carried an open or
reserved request - the "request #1 reserved / #2 open" starting state described in the brief was
not present on this clone. I created a fresh "Request CS to reserve" (tick rows -> Actions ->
Request CS to reserve) to exercise the flow, per the brief's fallback instruction.

## AC results

| AC | Result | Evidence |
| --- | --- | --- |
| AC-RS-61 (Reserve icon, no card/section) | PASS | `AC-RS-61-reserve-icon-lines.png`. Created a 2-row request on OI-001072 (SRTJC7206 L2032, C-FH14 L832); both rows immediately grew an aria-label="Reserve" icon-button (amber). No "Request #" card or "Earlier reserve requests" section anywhere on the page at any point in the walk - confirmed by grep across every snapshot taken. |
| AC-RS-53 (pool axis) | PASS | `AC-RS-53-55-dialog-pools.png`. Location combobox listed BRW, DC1, MWH, RESERVE, RSW, WH3 - every active own-company pool, no group warehouse (BRW-IB, the row's own location, is absent from the list as expected). |
| AC-RS-55 (default pool + recompute) | PASS | Default was BRW (the System Settings default at the time). Switching Location to WH3 and back to BRW re-triggered the Reserved-qty computation each time (value stayed 0 because this product had 0 available in every pool on this clone - the recompute *fired*, verified via re-snapshot after each change, just against zero stock). |
| AC-RS-8 (reason gating) | PASS | Reserved 5 of 10 (SRTJC7206): `Confirm reserved` stayed disabled until Reason was filled, then enabled. Reserved 264 of 264 (C-FH14, full match): `Confirm reserved` was enabled immediately with no reason required - `AC-RS-8-full-qty-no-reason.png`. |
| AC-RS-56 (POST reserve row, per-row/request state machine) | PASS for the row-answer + one-row-still-open-keeps-request-open shape; PARTIAL on "Taken/Remaining reflect it" - see DEFECT below | `AC-RS-8-56-reserved-confirmed.png`. Toast "Reserved" on each confirm; dialog updated to `Reserved N @ BRW` + `Unreserve`; icon stayed amber while only one of the two rows was answered, turned green (`text-emerald-600`) on both rows only once the second row was also answered - matches "stays requested with one row unanswered, turns reserved on the last answer" applied per-row via the shared `reserve_state` field. |
| AC-RS-60 (History order/content) | PASS | `AC-RS-60-63-history-tab.png`. Newest-first: `Reserved 5 @ BRW` (actor + reason) above `Requested 10 @ BRW` (actor); after the later unreserve, `Unreserved 2 @ BRW` (actor + note) sits above both - `AC-RS-58-unreserve-history.png`. Net reserved (5-2=3) matched the Reserve tab figure. |
| AC-RS-63 (date format) | PASS | Every timestamp rendered `22/09/2026, 4:19 PM` style (no `T`, no microseconds); every actor was a name ("Teh Jayson"), never a UUID. |
| AC-RS-58 (unreserve bounds + effect) | PASS | Qty 10 against net-reserved 5: 422, toast read *"SRTJC7206: unreserve quantity must be between 0 and 5 (the net reserved)."* - names the limit - `AC-RS-58-unreserve-above-net-refused.png`. Qty 2 + note: 200, toast "Unreserved", net dropped 5 -> 3, History gained the `Unreserved` line, no email side effects observed (no new network calls beyond the unreserve POST + refetch). |
| AC-RS-59 (Unlink leaves reserve untouched) | PASS | Selected the reserve-only SRTJC7206 row (no PO/SPO link) and ran bulk "Unlink selected". It resolved through the deferred-action endpoint (`GET pending-actions/current?entity_type=order_inquiry_row...` -> `last_outcome.status: "committed"`, action_key `order_inquiry_row.unlink`) with nothing to actually unlink (row had no doc links). Re-fetched the row straight after: `reserve_state: "reserved"`, `reserved_qty: "3"`, `links: []` - reserve fully intact. Did not have a second data point with a row carrying BOTH a live PO/SPO link and a reserve link at once (every row on OI-001072 that already had a PO/SPO link was already 100% covered, so "Request CS to reserve" was disabled for it) - the "removes the PO link only" half of this AC is untested on this clone. |
| AC-RS-24 (Cancel request from dialog header, countdown, deliberate lapse) | PASS, with one side finding | `AC-RS-24-cancel-request-countdown.png`. Created a fresh SRTW2000 request of my own (never touched OI-001072's original data), opened it, clicked "Cancel request" in the dialog header: toast "Reserve request cancelled" fired, the button became a plain "Cancel" (the reversible-countdown affordance). Let it lapse deliberately (per the brief). After it committed: the row's Reserve icon disappeared from the grid entirely and the dialog's own History tab read "No history yet." - i.e. cancelling an unanswered request deletes the request/row association outright rather than leaving a `cancelled` history line. This is a plausible design (nothing was ever answered, so there is nothing to audit) but it reads as a gap against AC-RS-60's literal wording ("History ... lists ... cancelled"), worth a ruling rather than a hard fail. |
| AC-RS-54 (Settings default-pool select) | PASS | `AC-RS-54-settings-default-pool.png`. System Management (via Users & Access -> Settings, `/user-management/settings`) shows "Reserve dialog default location" as a `SearchableSelect`-style combobox with a "Clear selection" affordance. Changed BRW -> DC1, Save -> "Settings updated successfully", reload confirmed DC1 persisted. Then Clear selection -> "Row's own site pool", Save -> "Settings updated successfully" again. Both clearable and save round-tripped through a reload. |
| AC-RS-62 (`?reserve=` deep link) | PASS | `AC-RS-62-deep-link-autoopen.png`. Created a fresh SRTW2000 request (id `1d8445b8-...`), then opened `http://localhost:3080/project-sales/order-inquiries/<id>?reserve=1d8445b8-...` directly (the one permitted deep-URL step). The `Reserve - SRTW2000` dialog auto-opened on that request's row pre-filled with the Reserve tab. Closing it: `get url` showed the `reserve` param gone, and the grid still carried the Reserve icon for that row afterward. |
| 375px viewport | PASS | `AC-RS-375px-dialog.png`. Reopened the (now-reserved) SRTJC7206 row's dialog at 375x812: tabs, "Reserved 3", and the Unreserve button all rendered without clipping or horizontal scroll. |

## Defect found

**Taken / Remaining grid columns do not update after a reserve, contradicting AC-RS-56.**

Reproduction:
1. On OI-001072's Lines tab, select an open ("To Buy") row and use Actions -> "Request CS to reserve".
2. Open the row's Reserve dialog, set Reserved below/at the requested qty (with a reason if short), Confirm.
3. Toast "Reserved" fires, the dialog correctly shows `Reserved N @ BRW`, and the icon eventually turns green once the whole request is answered.
4. The `GET /api/v1/project-sales/order-inquiries?...` response (confirmed on a hard `location.reload()`, not a stale cache) correctly carries the new figures - example captured live:
   - `SRTJC7206`: `reserve_state: "reserved"`, `reserved_qty: "3"`, `taken_from_po: "3"`, `remaining_open: "7"` (was requested 10).
   - `C-FH14`: `reserve_state: "reserved"`, `reserved_qty: "264"`, `taken_from_po: "264"`, `remaining_open: "0"` (full match).
5. The Lines DataGrid's own "Taken" and "Remaining" cells for both rows still read `0` and the original requested qty (`10` / `264`) - unchanged from before the reserve. The adjacent "State" text column *does* pick up the change correctly (`To Buy` -> `Partly On PO/SPO` / `On PO/SPO`), and the Reserve icon colour also updates correctly - only the two numeric columns are stale.

Screenshot: `DEFECT-taken-remaining-stale.png` (both rows visible: green Reserve icon + correct State text, but Taken/Remaining still at pre-reserve values). This looks like the grid's Taken/Remaining cell renderer is reading a different/cached field than `taken_from_po`/`remaining_open`, since the sibling State-text cell in the same row, same render, is correctly bound.

## Not independently verified

- AC-RS-59's "unlinking a row that holds a PO link and a reserve link removes the PO link only" - no row on OI-001072 offered both a live PO/SPO link and remaining open qty simultaneously to build that fixture; only the "reserve survives an Unlink on a reserve-only row" half was exercised.
- AC-RS-60's `cancelled` history-entry line - the cancel flow observed here deletes the row/request association rather than leaving a row to show it; see the AC-RS-24 note above.

## Console / network

No uncaught JS errors (`errors` was empty throughout). One pre-existing React warning unrelated to
this feature ("Each child in a list should have a unique key prop", `Demo1Layout` render - sidebar
chrome, not the reserve dialog or grid) appeared once after an HMR rebuild and did not reproduce on
a later reload. All reserve/unreserve/create-request calls returned the expected status codes
(201 create, 200 reserve/unreserve, 422 on the deliberate above-net unreserve).
