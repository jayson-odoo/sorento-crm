# UAC: fulfilment planning - Decide on the ticked lines, and one reason box

Plan: `PLAN-fp-decide-and-one-reason-24sep.md`. Issues #1216, #1217.
Status: APPROVED 24 Sep 2026, rulings R1 to R14 folded (AC-1, AC-3, AC-4, AC-6 to AC-12, AC-16,
AC-17 rewritten; AC-51 to AC-55 added). The Decide item list (AC-4) is R14's ruled set, no
longer conditional. R12 drops the agent and the "covers k of n" suffix from the donor order and
location picker rows (AC-11, AC-48).

Tags: `[BE]` pytest, `[FE]` vitest, `[E2E]` agent-browser evidence run (no new Playwright
spec), `[T]` test-only guard / regression, `[UX]` measurable layout, motion or state.

## Journey

Actor: CS planner on "Planning N sales orders together", List view, section "Every
contributing line".

- **J1 Scan and tick** - ticks the rows that should all go the same way.
- **J2 Decide** - presses Decide (top right of the section, always there, greyed with nothing
  ticked), picks As suggested, Use own location, Borrow from another order, Borrow other
  location, Use BRW or Buy; whole open quantity per row; the two Borrows ask one donor order or
  one location.
- **J3 Say why, only when needed** - one Reason for the batch when the pick differs from a
  row's suggestion or confirmed decision, or for Borrow.
- **J4 Read the outcome** - one toast: saved count, skipped count with the first few named;
  nothing blocks the batch, no error dialog; saved rows untick, skipped rows stay ticked.
- **J5 Partial lines** - expands a row; exactly one Reason box, which is also the borrow and
  the discontinued reason.
- **J6 Confirm** - a discontinued Buy with no reason confirms; the left-out banner remains for
  its other two causes.

## Phase 1 - frontend (S1 FE half, S2, S3)

### Decide control (J1, J2, J4)

- **AC-1 [FE] (J1) (R4)** Given the list view with no row ticked, then Decide renders,
  disabled, with the tooltip "Tick the lines to decide", and neither a selected Badge nor Clear
  renders. When one row is ticked, then Decide is enabled and the strip reads `1 selected`,
  Decide, Clear, in that order.
- **AC-2 [FE] (J1)** Given a Confirmed row and a Saved row, then both rows' checkboxes are
  enabled; an unplannable row and a cancelled row stay disabled with today's tooltips.
- **AC-3 [FE] (J1) (R1)** No button labelled `Save as suggested` renders in the strip, with or
  without ticked rows. Given 3 ticked rows of which 1 is Confirmed and 1 is Saved, when Decide >
  As suggested is picked, then exactly 1 PUT is sent (the row `canQuickSave` accepts, verdict
  `approved`, body = `suggestedDecisionFor`), no dialog opens, and the toast counts 2 skipped
  ("already confirmed", "already saved").
- **AC-4 [FE] (J2) (R1, R2, R8)** Given rows ticked, when Decide is pressed, then a menu opens
  with exactly these items in this order: As suggested, a separator, Use own location, Borrow
  from another order, Borrow other location, Use BRW, Buy. The labels equal
  `supplyVocabulary.LABELS` for their kinds; no item reads Reserve, Use incoming or Borrow
  incoming.
- **AC-5 [FE] (J2)** `decideComposition(row, 'buy')` returns `reserve: []`, `borrow: []`,
  `timely_spo_qty: '0'`, `buy_qty = open_qty`, `order_back: false` for a row whose suggestion
  was Reserve, one whose suggestion was Borrow and one whose suggestion counted incoming SPO.
- **AC-6 [FE] (J2) (R2, R6)** `decideComposition(row, 'own')` on a row whose `own` / `group`
  reserve sources hold at least `open_qty` free fills `reserve[]` from those rows only, in the
  engine's order, summing to `open_qty`, `buy_qty: '0'`, and never draws a `site_pool` row; on a
  row whose own location holds less, it returns a skip reading `only <free> free at own
  location`.
- **AC-7 [FE] (J2) (R2, R6)** `decideComposition(row, 'shared')` fills `reserve[]` from the
  `site_pool` rows only, within `poolShareLimitsOf`, summing to `open_qty`; short of the line it
  returns a skip reading `only <free> free at BRW`.
- **AC-8 [FE] (J2) (R8)** `decideComposition(row, 'borrow_order', donorSo)` on a row whose
  `borrow_candidates` include `donorSo` with free >= `open_qty` returns one `borrow[]` component
  from that donor line for `open_qty`, `buy_qty: '0'`; a row with no candidate on `donorSo` or
  too little returns a skip naming the donor and its free quantity.
- **AC-9 [FE] (J2)** `decideComposition(row, 'borrow_other', loc)` on a row whose
  `other_location` candidates include `loc` with free >= `open_qty` returns one `borrow[]`
  component at `loc`, `source: 'other_location'`, qty `open_qty`, `buy_qty: '0'`; otherwise a
  skip naming the free quantity at `loc`.
- **AC-10 [FE] (J2) (R9)** Given two ticked rows of the same item whose picked location (or
  donor order) holds enough for only the first in list order, when saved, then the top row is
  saved and the second is skipped (running tally), and the order follows the list's current
  sort.
- **AC-11 [FE] (J2) (R8, R12)** Given Decide > Borrow from another order, then a dialog titled
  `Decide n lines: Borrow from another order` opens with one required `SearchableSelect`
  labelled Donor order, options = donor orders offered on at least one ticked row, each
  labelled with the SO number only (no agent, no "covers k of n" suffix), sorted by k
  descending though k is not shown. Given Decide > Borrow other location, then the select is
  labelled Location, options = other locations with free stock for at least one ticked row,
  each labelled with the location code only, sorted by k descending though k is not shown.
- **AC-12 [FE] (J3) (R5, R7)** Given every ticked row's suggestion is Buy, when Decide > Buy is
  picked, then no dialog opens and the rows save at once with verdict `approved`. Given at
  least one ticked row whose suggestion differs, when Use own location, Use BRW or Buy is
  picked, then the dialog opens with one Reason box and no picker, and Save stays disabled
  until the box is non-blank. Given either Borrow, then the Reason box is required regardless
  of the suggestion, and Save stays disabled until the picker has a value and the reason is
  non-blank. The dialog's Save reads `Save k lines`, k = the rows the current pick covers.
- **AC-13 [FE] (J3)** Given the dialog saved with reason "project handover", then every row
  saved as `amended` carries `reason: 'project handover'`, every borrow component carries
  `reason: 'project handover'`, and a discontinued row saved as Buy carries
  `buy_reason: 'project handover'`.
- **AC-14 [FE] (J2)** Given a ticked Confirmed row, when Decide > Buy is saved with a reason,
  then its PUT body has `verdict: 'amended'` (never `approved`); given a Confirmed row whose
  frozen decision already buys the whole line, then it is skipped as "already decided that way".
- **AC-15 [FE] (J2)** Given a ticked row with a Saved or Rejected draft, when Decide saves,
  then one PUT replaces that draft and the pill reads Saved.
- **AC-16 [FE] (J4) (R10)** Given 9 ticked rows of which 2 are skipped, when Decide saves,
  then one toast reads `7 saved as <Label> · 2 skipped: <item> line <n> (<why>), ...` with at
  most 3 names then `and N more`; the 7 rows untick; the 2 stay ticked. No dialog, alert or
  banner opens.
- **AC-17 [FE] (J4) (R10)** Given one row's PUT fails with a 409, then that row's draft
  reverts, it stays ticked, it is counted among the skipped with the server's sentence, and the
  remaining rows are still sent and keep their saves. Given every row is skipped, then no PUT
  is sent and the toast reads `0 saved · n skipped: ...` in the neutral tone.
- **AC-51 [FE] (J2) (R10, Q16)** Given a ticked row whose suggestion carries a Reserve with
  `source: 'own_arrival'`, when Decide > Buy saves, then that row is skipped with why
  `stock already landed for it` and no PUT is sent for it.
- **AC-52 [FE] (J2) (R3)** Given a ticked Confirmed row whose frozen decision already reserves
  the whole line from its own location, when Decide > Use own location saves, then it is
  skipped as `already decided that way`.
- **AC-53 [FE] (J2) (R8)** Given Decide > Borrow from another order on a donor that shares the
  lines' own sales agent, then the dialog also asks "Who authorised it" (required) and the
  saved borrow reason folds the name in as `BorrowAddDialog` does today; for any other donor
  that field does not render.
- **AC-18 [FE] (J2)** Decide issues one `PUT .../lines/{key}/draft` per saved row, in chunks
  of at most 5 in flight, and calls no other endpoint.

### Discontinued gate, FE half (J6)

- **AC-19 [FE] (J6)** `lineFor` on a discontinued line with `buy_qty > 0` and blank
  `buy_reason` returns a confirm line (not `'buy_reason_missing'`) in each of its three
  branches (amended, approved on a covered line, derived).
- **AC-20 [FE] (J6)** Given such a line decided, then `confirmLinesFor` includes it, the
  Confirm count includes it, and the left-out banner does not render for it.
- **AC-21 [FE] (J6)** Given one line left out for `no_mirror` and one discontinued Buy with no
  reason, then the banner names only the `no_mirror` line; the string "discontinued product
  with no reason given" appears nowhere in the rendered page.
- **AC-22 [FE] (J6)** `supplyComposition` raises no blocker for a discontinued Buy with no
  reason; the per-order sheet (`SupplyLineCard`) still shows its discontinued warning and no
  longer says it takes a reason.
- **AC-23 [FE] (J6)** The trail chip reads "Discontinued" and its title no longer says a Buy
  needs a reason.

### One reason box (J5)

- **AC-24 [FE] (J5)** Given an expanded row on a discontinued product with an added borrow row,
  then the panel renders exactly ONE `textarea` (the Reason box, id `line-reason-{key}`);
  the Buy block and every borrow row render no text input for a reason.
- **AC-25 [FE] (J5)** Given a discontinued line that buys, then a "Discontinued" badge renders
  beside the Reason label, the box has no asterisk for that cause, and Save decision is
  enabled with the box blank (when nothing else needs a reason).
- **AC-26 [FE] (J5)** Given a composition that differs from the suggestion
  (`amendNeedsReason` true), then the box shows an asterisk and Save decision is disabled
  until it is non-blank (unchanged rule, one box).
- **AC-27 [FE] (J5)** Given a borrow row added by hand and the box blank, then Save decision is
  disabled; with "stock held for handover" typed, the PUT body carries
  `reason`, and the borrow row's `reason`, both equal to that text.
- **AC-28 [FE] (J5)** Given a discontinued line whose draft equals the suggestion (approving
  save) with "project order" typed, then the PUT body carries `buy_reason: 'project order'`
  and `reason: 'project order'`, and after save the box still reads "project order".
- **AC-29 [FE] (J5)** Given a suggested borrow row and the box blank, when saved, then the
  borrow row keeps the engine's suggested reason; with text typed, the typed text replaces it.
- **AC-30 [FE] (J5)** Given an existing draft with `reason` blank, `buy_reason: 'A'` and a
  borrow reason `'B'`, when the row opens, then the box reads `A`.
- **AC-31 [FE] (J5)** `BorrowAddDialog` renders no reason field; for a same-agent donor it
  still asks who authorised it, and the added borrow row's stored reason folds that name in as
  today.
- **AC-32 [FE] (J5)** Reject in the expanded row uses the same box: Reject is disabled with the
  box blank and sends `{verdict: 'rejected', reason: <box>}`. The verdict column's Reject
  popover keeps its own reason box unchanged.
- **AC-33 [FE] (J5)** The trail prints one "Reason" line when `amend_reason`, `buy_reason` and
  the borrow reasons are the same text.

### UX (J1 to J5)

- **AC-34 [UX] (J2)** At 375px the selection strip wraps (no horizontal page scroll) and
  Decide, its menu and the Decide dialog's Save are reachable; at 1280px Decide sits on the
  section's top right, after the selected Badge and before Clear.
- **AC-54 [UX] (J1) (R4)** The disabled Decide uses the Button's own disabled style (no custom
  grey), keeps its size so the strip does not shift when the first row is ticked, and its
  tooltip is reachable by keyboard focus.
- **AC-55 [UX] (J2)** The Decide dialog holds at most: one picker (Borrows only), one Reason
  box, the conditional "Who authorised it" field, Cancel and Save. No explanatory sentence
  renders in the menu or the dialog.
- **AC-35 [UX] (J2)** Decide's menu opens on the existing `DropdownMenu` presets and the dialog
  on the existing `Dialog` presets; no new animation, no `transition-all`, reduced motion
  collapses both as today.
- **AC-36 [UX] (J2)** The donor order and location selects are `SearchableSelect`s (required, so
  not clearable); no raw `select`.
- **AC-37 [UX] (J4)** No-motion list holds: no row flash on save, no dimming of ticked rows,
  no animated count, no transition on the Discontinued badge or on rows unticking.
- **AC-38 [UX] (J2)** No UUID renders in the dialog, the menu or the toast (locations by
  code, donor orders by SO number, rows by item code and line number).

## Phase 2 - backend (S1 BE half) and wiring

- **AC-39 [BE] (J6)** `ProjectSupplyService.confirm` on a line whose product is discontinued,
  `buy_qty > 0`, `buy_reason` absent: returns 200, writes the decision revision, and raises the
  OI Buy row (`inquiry_rows_created == 1`). Replaces the 422 expectation at
  `tests/test_so_supply_confirmation.py:1185`.
- **AC-40 [BE] (J6)** The frozen snapshot of that line keeps
  `lifecycle_warning == "This product is discontinued."` and `buy_reason is None`.
- **AC-41 [BE] (J6)** The same line with `buy_reason: 'project order'` still freezes the reason
  (existing :1205 test unchanged).
- **AC-42 [BE] (J6)** `confirm-all` over two orders, one carrying a discontinued Buy with no
  reason: both orders return `ok: true`.
- **AC-43 [BE] (J6)** The board payload's explanation for a discontinued item no longer ends
  with "Discontinued: the buy needs a reason."; `item_flags.discontinued` stays true
  (`tests/test_fulfilment_board.py:5408` updated).
- **AC-44 [T] (J6)** The borrow-reason rule is untouched: a borrow component with a blank
  reason is still refused at Confirm (`_check_borrow`), and the stock + buy mix still needs an
  `amend_reason`.
- **AC-45 [T] (J2)** `save_draft` still 409s an `approved` draft on a covered line and accepts
  `amended` (existing `test_fulfilment_line_draft_route.py` cases unchanged), which is the
  contract AC-14 relies on.
- **AC-46 [T] (J6)** A covered discontinued line carried forward by a later confirm still
  survives (`tests/test_supply_partial_confirmation.py:552` unchanged).

## Phase 3 - lane end

- **AC-47 [E2E] (J1 to J4)** Sidebar nav from `/` to a board with at least 3 lines: Decide
  greyed with nothing ticked; tick 3, Decide > Buy, reason if asked, Save; the 3 pills read Saved; Confirm; the lines read
  Confirmed and the OI detail shows the Buy rows. Screenshots at 375px and 1280px.
- **AC-48 [E2E] (J2)** Decide > Borrow other location (or Borrow from another order, whichever
  the seeded board offers) on 2 ticked lines: the picker lists location codes only (or SO
  numbers only), no agent and no "covers k of n" text;
  save; the expanded row shows one borrow component at that location for the whole quantity
  and the Reason box holds the batch reason.
- **AC-49 [E2E] (J6)** A discontinued line bought with the Reason box blank confirms with no
  banner; the confirm toast states no "left out" count.
- **AC-50 [E2E] (J5)** An expanded row on a discontinued product with a borrow shows exactly
  one text box.
