# Browser evidence - oi-worklist-one-header

Run date: 17 Sep 2026. Lane stack: FE `http://localhost:3080`, BE `http://localhost:8080`,
DB `sorento_oioh_stack` (15 Sep prod backup copy, already migrated - OI-000737 folded into
OI-000477 on SO314593). Coder HEAD at start of the walk: `d4a1bd681`; the coder kept pushing
review-round-2 commits during the walk (last seen `e080f68c4`), none touching the areas
exercised below (Filters popover, Columns menu, Was/Now tooltip).

Tool: `agent-browser@0.27.0`, session name `oi-one-header-tester` (isolated from the shared
daemon). Login via sidebar from `/`, never a deep URL.

## Data prep on the copy (`sorento_oioh_stack`)

1. Deleted the saved column preference for `tehjayson@gmail.com` on listing key
   `projects.projects.view::order-inquiry-worklist` (table `user_list_column_configs`), so
   AC-OH-01/62 show the true default.
2. SO314593 / B2154-NL (`so_line_id 0ecc19dc-f2fc-45e5-ba0d-4ae4de4f2488`) sat post-confirm
   from a 16 Sep run (a 220 ORDER row, a DELAY row, the migrated 182 row already flagged
   `redirected_to_pool`). To replay the AC-OH-60 pre-state:
   - Did **not** run the UI "Reset planning" action - read `planning_reset_service.py` first:
     it deletes every `order_inquiry_row` for the WHOLE order (all 22 lines), which would have
     destroyed the very migrated row (`9e398088-a3bf-4525-9063-b2f9d42cade3`) the next step
     needs to still exist. Running it would have contradicted the brief's own follow-up SQL
     ("for the migrated row id 9e398088..."), so I went straight to the SQL instead.
   - SQL (transaction, both statements together):
     `UPDATE projects.order_inquiry_rows SET redirected_to_pool=false, state='partly_linked',
     note=regexp_replace(note, '; SPO-2026/01-0143 received.*$', '') WHERE id='9e398088-...'`
     and `DELETE FROM projects.order_inquiry_rows WHERE so_line_id='0ecc19dc-...' AND id <>
     '9e398088-...' AND (supply_decision_id IS NOT NULL OR verb='DELAY')` - removed the DELAY
     row (`bc4e015e-...`) and the 220 ORDER row (`4b717523-...`).
   - Verified with a SELECT: only the migrated row remains for that line, `redirected_to_pool
     = f`, note stripped, qty 182, `Taken by PO/SPO` 158, `Remaining` 24 - matches "one sheet
     row linked 158 to a received SPO" from the AC.
   - The project mirror line (`projects.sales_order_lines` id `0ecc19dc-...`) already showed
     the stale qty/date (182 / 01/06/2026) while the core line (`sales_order_lines` id
     `cb5753c9-...`) already showed 220 / 01/03/2027 - the "mirror stale on qty and date"
     precondition the AC asks for was already present in the copy, untouched by me.
3. Confirmed via API-key check that `EXTERNAL_API_KEY` has no seeded row on this copy (known
   gotcha, `project_prod_copy_db_lacks_local_test_api_key.md`) - not needed since all
   verification went through the browser session, not curl.

## AC-OH-60 - crash fixed by the captain's data repair; the confirm-through-UI walk is still
## not completable for this specific line, for a reason unrelated to this lane's diff

Walked: Supply Chain > Project Demand > Fulfilment Planning > searched SO314593 > selected
the row > "Plan SO314593" (the actual planning board, distinct from the read-only SO
reconciliation dialog opened by the row's own "Open" button, which only shows a supply
composition preview with no Confirm action).

The planning board failed to load:

```
The planning board could not be loaded
(psycopg2.errors.InvalidParameterValue) cannot get array length of a scalar
[SQL: SELECT projects.so_supply_decisions.id ... FROM projects.so_supply_decisions
WHERE projects.so_supply_decisions.project_sales_order_id IN (%(project_sales_order_id_1_1)s::UUID) AND
projects.so_supply_decisions.state = %(state_1)s AND
projects.so_supply_decisions.undo_journal IS NOT NULL AND
jsonb_array_length(projects.so_supply_decisions.undo_journal) > %(jsonb_array_length_1)s AND
projects.so_supply_decisions.confirmed_at IS NOT NULL AND
projects.so_supply_decisions.company_id IN (%(company_id_1_1)s::UUID)]
```

Reproduced directly in psql (same predicate, same values) - `cannot get array length of a
scalar`. Root cause: `so_supply_decisions.undo_journal` for this order's only decision
(`ff18c368-008d-40e9-a1f1-2b6edf7ec2da`, revision 1) held the **JSON literal `null`**
(`undo_journal = 'null'::jsonb` was true, `undo_journal IS NULL` was false) rather than SQL
NULL. `_journalled_decision_clause()` in
`sorento_crm_backend/app/services/project_supply_undo_service.py:90-94` guards with
`SOSupplyDecision.undo_journal.isnot(None)` (an `IS NOT NULL` check), which does not exclude
a JSON `null` value, so `jsonb_array_length()` runs on it and Postgres raises. Captain
confirmed this is a defect from `#985` (`Core .values(undo_journal=None)` on a JSONB column
stores the JSON literal, not SQL NULL) and gets its own hotfix lane - not fixed here.

**Data repair (captain-authorized, scratch DB only):**
`update projects.so_supply_decisions set undo_journal = NULL where jsonb_typeof(undo_journal)
= 'null'` - 1 row affected on this copy. Re-ran the same predicate the board's own query uses
directly in psql afterwards: 0 rows, no error. Re-opened "Plan SO314593" in the browser - the
board now loads cleanly (screenshot `AC-OH-60-board-loads-after-undo-journal-fix.png`), no
console/network errors.

**Second blocker found while finishing the walk, not fixed, reported instead:** B2154-NL
(Line 1 on the board) still shows `Decided rev 1` / a disabled row checkbox / status
"Confirmed", because `so_supply_decisions` row `ff18c368` (the SAME 16 Sep decision, still
`state='active'`) still lists B2154-NL in its `line_snapshots` JSON array alongside 7 other
lines from that batch - my earlier data prep only deleted the line's `order_inquiry_rows`
(the downstream artifact), not the decision that produced them, since removing the whole
decision would also un-decide the other 7 lines the brief never asked me to touch. Opening
the row's "Amend" action does unlock its toggles, but "Save decision" stays disabled: the
`suggested` outcome (Buy 220) and the currently-`decided` outcome (also Buy 220, from
`ff18c368`) are identical, so there is nothing for Amend to save - unlike Line 10/12/13/14 on
the same board, which never had a decision at all and show a clean "Not decided" / "Save as
suggested" state.

Tried one further, narrowly-scoped repair to make the pre-state match: removed just the
B2154-NL entry from `ff18c368.line_snapshots` (`jsonb_agg(...) FILTER` style rebuild of the
array). This unhooked the "Decided rev 1" badge, but the row did not fall back to a clean
"Not decided" state the way Line 10 does - it rendered "Not recorded" in the Suggested column
and, once expanded, "DECISION Amended to nothing / 220 short / Buy 0" - a garbled, misleading
state, not the "propose Buy 220" the brief expects. Concluded a partial `line_snapshots` edit
is not how the app itself ever reaches "undecided" (the reset service's own supported shape
is deleting the WHOLE decision row, which was not an option here without touching the other 7
lines) - **reverted the edit** (re-appended the exact same JSON object, captured before
removing it) and confirmed the board is back to the clean, crash-free "Decided rev 1 /
Confirmed" state for all 8 already-decided lines, verified by reload.

**Observed:** after the captain's fix, the board loads; B2154-NL cannot be walked through a
fresh Confirm without either (a) a decision-level repair I could not do cleanly by hand, or
(b) accepting a change of scope to the other 7 lines sharing the same decision.
**Expected (AC-OH-60):** the board loads, B2154-NL can be Confirmed, producing one ORDER 220
row with Was/Now (182), the 182 row `used`/greyed, no DELAY row, one order inquiry number,
Raised by = migrator on the used row, the open SPO linked to the 220 row not the used one.

Screenshots: `AC-OH-60-BLOCKED-planning-board-crash.png` (the crash, pre-fix),
`AC-OH-60-board-loads-after-undo-journal-fix.png` (post-fix, board loads, Line 1 still shows
"Decided rev 1").

**Verdict: STILL NOT WALKED end to end.** The crash is fixed (not this lane's defect, per
captain). The remaining gap - B2154-NL's decision-level state, left over from the original
16 Sep confirm, not reachable by a row-level data-prep edit alone - needs either a coordinator
call on scope (touch the other 7 lines too, accept a different already-undecided line as the
walk's stand-in, or have the coder provide a clean per-line reset) before AC-OH-60's exact
worklist-row assertions can be captured. B2154-NL on `sorento_oioh_stack` currently sits with
only its migrated row (182, `partly_linked`, `redirected_to_pool=false`) and no ORDER/DELAY
rows, decision `ff18c368` restored to its original 8-line `line_snapshots` - the same,
stable, crash-free state as right after the captain's undo_journal fix.

## AC-OH-61 - DEFECT: no State filter exists in the Filters popover

Procurement > Supply Chain > Order Inquiries > searched `314593` > opened Filters. Read the
full field list off the DOM (`label` elements) with the popover open: Location, Agent, SO
month, PO number, SPO number, Linked, Confirmed, Supplier, Project, Raised by, Raised on.
**No "State" field.** The "Confirmed" field (options: Confirmed/Changed/Rejected) is `ack_state`,
not `state` - it has no Cancelled option. Grepped
`OrderInquiriesClient.tsx` for `state`/`Cancelled`: zero matches wired to a filter control (only
an unrelated `row.state !== 'cancelled'` guard on row selection). The backend already has the
capability (`order_inquiry_worklist_service.py` accepts a `state` query param and computes
`by_state[cancelled]` per AC-OH-51/52), but nothing in the FE reads or writes it.

**Observed:** Filters popover has no way to select State = Cancelled.
**Expected (AC-OH-61):** Filters > State = Cancelled lists the cancelled rows for the SO.

Screenshot: `AC-OH-61-DEFECT-filters-popover-no-state-field.png` (full field list visible with
the popover open).

**Verdict: FAIL.** Frontend piece of this AC is not implemented.

Per captain instruction, wrote the RED test-first contract for this in
`OrderInquiriesClient.test.tsx` (`describe('AC-OH-61: ...')`, 3 tests: label + option
labels/counts off `by_state`, selecting sends `state=` to the worklist call, a URL-seeded
value round-trips and clearing drops the param) - not implemented. All 3 fail for the right
reason (`Unable to find an element with the text: State`, not a setup bug); the other 42
tests in the file still pass. Committed as `test(scm): red vitest for the worklist State
filter (AC-OH-61)` (`d8e3c9a9a`).

## AC-OH-70 - PASS (the popover scrolls; "last field" wording has drifted, not a defect)

At a 1280x700 viewport, opened Filters: the popover's own inner content div
(`max-h-[60vh] space-y-3 overflow-y-auto`, confirmed via computed style: `maxHeight: 420px`,
`overflowY: auto`, `scrollHeight: 758`) visually shows only Location..Linked at first paint
(screenshot `AC-OH-70-filters-700h-clipped-before-scroll.png`), because the box is genuinely
taller than 420px of content. Scrolling that specific container (not the page - the page-level
`scroll` command scrolls the window, which does not reach a nested `overflow-y-auto` div)
reveals Confirmed, Supplier, Project, Raised by, and the true last field, **Raised on** (a date
input), fully visible and interactive at the bottom of the popover (screenshot
`AC-OH-70-filters-700h-raised-on-reachable-after-scroll.png`). Nothing clips; the popover
scrolls independently of the page.

Note for the plan/UAC: AC-OH-70's own text says "the last field (Confirmed)" - that was true at
the point the S7 commit (`621fb4f25`) landed, but later commits (Excel-parity, PO/SPO pairing
work) added Supplier/Project/Raised by/Raised on after Confirmed, so Confirmed is no longer the
last field. The scroll mechanism still reaches whatever the actual last field is, so the AC's
*intent* (nothing clips, everything reachable) is satisfied - only the field name in the AC text
is stale.

**Verdict: PASS.** Flagging the stale field name as a docs nit, not a defect.

## AC-OH-01 / AC-OH-62 - PASS

Columns menu on first load (no saved preference, per the data-prep step above): "Order
Inquiry" is unticked while every other column is ticked
(`AC-OH-01-AC-OH-62-columns-menu-order-inquiry-unticked-default.png`). Ticking it adds an
"Order inquiry" column showing `OI-000477` on every one of the 17 visible rows for SO314593
(`AC-OH-62-order-inquiry-column-shown-after-tick.png`) - also visual confirmation of R1/R5
(one header per SO: every row of this SO carries the same inquiry number). Unticked it again
afterwards per the brief's step 3 instruction.

**Verdict: PASS** for both ACs.

## AC-OH-02 - PASS

Clicked the (i) "Show what changed" affordance on the SRTWB245 row (qty 280, `previous_qty`
182 set, `redirected_to_pool` false - a different, unrelated line on the same SO that already
carries a Was/Now from the 16 Sep confirm). Dialog: "SRTWB245 / Changed / Changed 17/09/2026"
with a Qty row (Was 182, Now 280) and Date row (Was 01/03/2027, Now 01/03/2027) - the existing
Was/Now affordance, exactly as the AC describes (no new component).

Screenshot: `AC-OH-02-was-now-tooltip-srtwb245.png`.

**Verdict: PASS.**

## AC-OH-63 - PASS

1280px (viewport screenshot, not full-page - full-page capture produces a compositing
artifact where the sticky topbar double-paints over the page header, a screenshot-tool
quirk, not a real rendering bug): list usable, DataGrid horizontally scrollable within its
own container, nothing overlapping (`AC-OH-63-list-1280.png`).

375px: page reflows to a single column, summary cards wrap, Filters/Columns/Actions buttons
stack, the DataGrid keeps its own horizontal scroll for the wide table without clipping the
page (`AC-OH-63-list-375.png`).

Console/errors checked after every navigation and interaction in this run: no uncaught errors,
no unexpected console output beyond routine `[debug] JWT token extracted successfully` lines.

**Verdict: PASS.**

## Summary

| AC | Result |
| --- | --- |
| AC-OH-01 | PASS |
| AC-OH-02 | PASS |
| AC-OH-60 | NOT WALKED end to end - crash fixed (captain's `#985` data repair), a second, unrelated decision-level data-prep gap for B2154-NL specifically remains, reported for a scope call |
| AC-OH-61 | FAIL (no State filter in the FE); red vitest committed `d8e3c9a9a` for the coder |
| AC-OH-62 | PASS |
| AC-OH-63 | PASS |
| AC-OH-70 | PASS (AC text names a stale field, not a defect) |

Coder HEAD at end of walk: `e080f68c4` (review round 2, in progress - none of the commits
seen during this walk touched the Filters popover, Columns menu, or the undo-journal query).
