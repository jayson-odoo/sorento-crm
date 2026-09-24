# PLAN: fulfilment planning - Decide on the ticked lines, and one reason box in the expanded row

Status: DRAFT, awaiting owner grill (steps 1 to 3 of `/feature` done; step 4 prepared, see
"Grill questions" at the end). Track: full (expected diff over ~300 changed lines across FE +
tests; no migration, no auth/RBAC change, no new ingest surface). One lane, one branch, one PR.
Issues: #1216 (Decide), #1217 (discontinued gate + one reason box).
UAC: `fp-decide-and-one-reason-24sep-acceptance-criteria.md`.
Classification: CORE extension of the `projects` fulfilment board (no new module, no new table).

## What the owner asked

### #1216 (24 Sep 2026, screenshots of "Planning 1 sales orders together", list view, "Every contributing line")

> "Can add button: save as buy (to Joey), save as reserve (stock transfer), save as borrow
> (select other location). Meaning I tick what I want and press a save button in the
> fulfilment planning page, to enhance the user experience by reducing their chance of
> expanding rows."

> "For amendments, they just need to buy, reserve, or borrow. Usually it's full quantity. So we
> can just let them select the rows and have a call to action button at the top right of the
> Every contributing line section. One action call, maybe called **Decide**, with a dropdown of
> either buy, reserve, or borrow. Borrow can just select the location. This is for full
> quantity; if they want to do half-half partially then they can go into the expanded row to
> fill in. This is to ease their user experience."

### #1217 (24 Sep 2026, screenshots of the confirm banner and an expanded row)

Banner today: "CB6602 line 416, CKS7847 line 144, SRT385-10 line 224 buy a discontinued
product with no reason given, so this confirmation leaves them out. Amend them to give one."

> "I think we block the saving if the product is discontinued and they must enter a reason.
> Let's remove that gate. If the product is discontinued, have a section like a reason where
> they need to fill in the discontinued reason. Ideally our expanded row section should only
> have one text input; don't need to have two, which is kind of confusing. So first, remove
> the gate for discontinued products, and then make sure moving forward our expanded row
> section only has one text box input to input whatever reason."

## Journey (written first)

**Actor.** A CS planner (the person who plans supply for project sales orders; purchasing,
Joey's seat, only executes the Buy rows that Confirm raises on the order inquiry).

**Arrival.** Sales orders list, ticks one or more orders, presses Plan together. Lands on
"Planning N sales orders together", List view (the default), section "Every contributing
line": one row per contributing SO line, each with a Suggestion and a Verdict pill
(Suggested / Saved / Confirmed / Rejected / Suggestion changed / Change proposed).

**What the system already knows (never asked).** For every row: the open quantity, the
engine's suggestion (reserve rows with their warehouses, borrow candidates with free stock per
location, buy qty), whether the line is already confirmed (covered), whether the product is
discontinued, which locations can reserve for this line (own location, own group, pools) and
which other locations hold free stock of the item (borrow candidates). Buying routes itself:
Confirm raises the order inquiry row purchasing works from. Stock transfers for a Reserve or
Borrow at another location are proposed automatically on Confirm.

**Steps, one decision each.**

1. **Scan and tick.** The planner reads the list and ticks the rows that should all go the
   same way (for example nine rows that should simply be bought). Decision: which rows.
2. **Decide.** Presses **Decide** at the top right of the section and picks **Buy**,
   **Reserve** or **Borrow**. Decision: which way, at full quantity.
   - Buy: every ticked row becomes Buy the whole open quantity.
   - Reserve: every ticked row is covered in full from its own reserve ladder (the locations
     the engine already reserves from for that line), in the engine's order. No location is
     asked.
   - Borrow: the planner picks ONE other location from a searchable list of locations that
     hold free stock of at least one ticked row's item. Every ticked row borrows its whole
     open quantity from that location.
3. **Say why, only when it is needed.** When the pick differs from a row's suggestion or from
   its confirmed decision, or when the pick is Borrow, one Reason box appears before saving.
   One reason covers every ticked row in this one decision. Decision: the reason text.
   (Grill Q3, Q5.)
4. **Read the outcome.** One toast: how many rows were saved, and which were skipped and why
   (a row the chosen way cannot cover in full, for example "only 3 free at BRW-IB"). Saved
   rows untick and read Saved; skipped rows stay ticked so the planner can pick another way
   for them at once. No decision.
5. **Partial or unusual lines.** For a half-half split the planner expands that row as today.
   The expanded row now carries exactly ONE text box, **Reason**, which serves as the amend
   reason, the borrow reason and, when the product is discontinued and the line buys, the
   discontinued reason. Decision: the split, and the reason in one place.
6. **Confirm.** Presses Confirm as today. A discontinued line that buys with no reason is NOT
   left out any more: it confirms like any other line. The left-out banner still names lines
   left out for the other two causes (no planning record line, no reserve warehouse).
   Decision: confirm or not.

**What they hold at the end.** Every ticked line decided in two or three presses instead of
one expansion each; one reason per decision, stored where purchasing and the trail already
read it; a confirmation that includes the discontinued lines they meant to buy.

**What everyone else is told automatically.** Unchanged: Confirm raises or refreshes the
order inquiry rows (purchasing), proposes stock transfers for Reserve/Borrow at another
location (warehouse), and writes the decision trail.

## What exists today (measured, main at e6012f65)

FE paths are under `sorento_crm_frontend/app/(protected)/project-sales/`; `FP` =
`fulfilment-planning/components/`, `SH` = `_shared/`. BE paths under `sorento_crm_backend/`.

### The section, its selection strip, Save as suggested

- `FP/FulfilmentBoardListView.tsx` renders `PanelDataGrid` with `title="Every contributing
  line"` (:764-838), mounted from `FP/FulfilmentBoardPanel.tsx` (:2092) with `onDecide={decide}`
  and `onDecideMany={decideMany}`. Heading `Planning ${n} sales orders together` at Panel :1567.
- Selection: `rowSelection` local state in the list view (:234), keyed by `row.key` (the
  contribution key `${sales_order_id}|${line_no}|${item_code}|${bucket_key}`), checkbox column
  from `buildSelectColumn` (`components/ui/data-grid-select-column.tsx`), used at :306-317.
- Selectable rows: `enableRowSelection={(row) => canQuickSave(row.original, draft)}` (:774);
  `canQuickSave` (`SH/lib/boardAmend.ts:506-519`) refuses covered (Confirmed), unplannable,
  cancelled and already-drafted rows, with tooltips "This line is already confirmed. Amend it
  to change what was decided." / "This line cannot be decided here: its sales order states no
  fulfilment location." / "Already saved. Undo it before saving it again."
- The strip lives in the grid's `toolbar` prop (:776-826), after the Expand all / Collapse all
  icon buttons: Badge `${n} selected`, Button `Save as suggested (${n})`, ghost Button Clear.
- Save as suggested: `saveSelectedAsSuggested` (:239-242) -> Panel `decideMany` (:830-869),
  chunks of 5, each `decide(key, suggestedDecisionFor(contribution), {quiet: true})`, one toast
  `${saved} line(s) saved · ${toConfirm} to confirm`. There is NO bulk endpoint on the server.

### How a verdict is saved per row

- Panel `decide` (:743-812): optimistic draft update, then `useLineDraftMutation().save`
  (`SH/hooks/useFulfilmentPlanning.ts:493-543`) -> `putLineDraft`
  (`SH/services/fulfilmentPlanningService.ts:621-638`) ->
  `PUT /api/v1/project-sales/fulfilment-planning/lines/{key}/draft`, body `{decision, proposed}`.
  Undo = `DELETE` on the same path.
- BE: `fulfilment_planning.py:359` -> `project_line_draft_service.save_draft` (:233). The draft
  lives in `projects.so_supply_decision_drafts.decision` (JSONB, opaque to the server, one row
  per core line). Shape = FE `BoardDecision` (`SH/types/fulfilmentPlanning.types.ts:1976-2048`):
  `verdict` (approved | amended | rejected), `reserve_qty`, `reserve[]`, `borrow[]` (each with
  `reason`), `buy_qty`, `buy_reason`, `timely_spo_qty`, `reason`, `order_back`,
  `cited_document`, `suspected_system_issue`.
- On a Confirmed (covered) line: `save_draft` 409s `board_line_already_confirmed` for an
  `approved` verdict (:270-289), accepts `amended`, and accepts `rejected` only with a reason.
- Verdict column (`id: 'verdict'`, ListView :723-757): `BoardDecisionPill` + `BoardVerdictActions`
  (check = save as suggested, X = reject popover with its own "Why this differs *" textarea,
  Undo, pencil "Change decision" which opens the row).
- Confirm: `Confirm (${n})` (Panel :1816-1829) -> `POST /fulfilment-planning/confirm-all`
  (BE `fulfilment_planning.py:441`, `ProjectSupplyService.confirm_many`), body built by
  `confirmLinesFor` (`SH/lib/fulfilmentBoard.ts:269-281`), each line by `confirmLineFrom`
  (`boardAmend.ts:534-565`): `reason` -> `amend_reason`, `buy_reason` and `borrow[].reason`
  carried as they are.

### Where the discontinued gate is enforced

- **FE leaves the line out.** `lineFor` (`SH/lib/fulfilmentBoard.ts:339-482`) returns
  `'buy_reason_missing'` when the product is discontinued, buy > 0 and `buy_reason` is blank,
  in three branches (:383 amended, :417 approved on a covered line, :455 derived). `confirmLinesFor`
  drops any line that returns a reason string. `unpostableDecidedFor` (:610-631) feeds the
  banner (`board-left-out-banner`, Panel :1848-1891, text from `SH/lib/unpostableNotices.ts:71`),
  `UNPOSTABLE_REASONS` (Panel :2332) and the amber "N left out" toast (Panel :1315-1320).
  Shipped by #1085 (`PLAN-board-confirm-left-out.md`).
- **BE refuses the whole order.** `ProjectSupplyService._check_line`
  (`app/services/project_supply_service.py:5583-5587`): discontinued + buy > 0 + blank
  `buy_reason` -> "This product is discontinued. Say why it is still being bought before
  confirming." -> `SupplyLinesRefused` 422, nothing written. Carried-forward covered lines are
  not re-checked.
- **Other copies of the rule.** `SH/lib/supplyComposition.ts:376-377` blocker ("buying a
  discontinued product needs a reason", shared with the per-order sheet); `FP/SupplyLineCard.tsx`
  :163-166, :351 (per-order sheet, "Buying it takes a reason."); `FP/BoardTrailPopover.tsx`
  :317-321 chip title "Discontinued: a Buy for it needs a reason."; BE board explanation suffix
  "Discontinued: the buy needs a reason." (`project_fulfilment_board_service.py:4079-4080`).
- **Origin.** `PLAN-scm-front-planning.md` section 3.4 and grill ruling Q4: "Buying a
  discontinued product for committed customer demand is allowed, with a warning and required
  reason." This plan amends Q4 to "allowed, with a warning; the reason is optional".
- **Not this gate.** `PLAN-order-sheet-oi-reports-22sep.md` Lane E (PR #1148, open) is about
  the REORDER PLAN admitting a discontinued product with confirmed OI demand
  (`_planning_rows`); it does not touch the board or `_check_line`. No conflict, no ordering
  dependency.
- Tests pinning the gate: BE `tests/test_so_supply_confirmation.py:1185` (refused, 422) and
  :1205 (confirms with a reason), `tests/test_supply_partial_confirmation.py:552`,
  `tests/test_fulfilment_board.py:5408`; FE `fulfilmentBoard.test.ts`,
  `FulfilmentBoardPanel.test.tsx` (:1808, :3666), `BoardLineDecisionPanel.test.tsx`.

### How the reason inputs are wired and stored (expanded row)

`FP/BoardLineDecisionPanel.tsx` (mounted as the `so_number` column's `meta.expandedContent`)
carries up to THREE kinds of text input today, not two:

| Input | Where | Draft field | Confirm field | Frozen at |
| --- | --- | --- | --- | --- |
| "Why this differs" (asterisk when `amendNeedsReason`) | right side, :996 | `reason` | `amend_reason` | `line_snapshots[].amend_reason` |
| "Reason *" under Buy, only when `draft.is_discontinued` | Buy block, :930-949 | `buy_reason` | `buy_reason` | `line_snapshots[].buy_reason` |
| "Reason *" per borrow row | Borrow block, :764-851 | `borrow[i].reason` | `borrow[i].reason` | `so_line_allocations.reason`, component `cs_reason` |

Plus `BorrowAddDialog` asks a mandatory reason when a borrow is added (and, for a same-agent
donor, who authorised it, folded into the same stored reason). `amendNeedsReason`
(`SH/lib/fulfilmentBoard.ts:779`) requires the "Why this differs" reason whenever the
composition differs from the suggestion (or from the frozen decision on a covered line). BE
requires a borrow reason (`_check_borrow`, `project_supply_service.py:5912`) and an
`amend_reason` for a stock + buy mix (:5606-5622). No `discontinued_reason` column exists
anywhere; the discontinued reason IS `buy_reason`.

### Existing bulk precedent

`BoardCellBreakdownDialog` (grid view) has "Approve selected" / "Reject selected" (the latter
with a fixed reason "Rejected on the planning board."), and deliberately no bulk Amend
(`PLAN-fulfilment-planning-from-autocount-so.md`: "a single quantity applied to eleven
different owed quantities is not a decision anybody meant to make"). Decide respects that: it
never applies a QUANTITY, only a whole-line WAY; each row keeps its own open quantity.

The only `DropdownMenu` on the page is the gear ("Board actions", Panel :1694-1805). There is
no split button component in `components/ui`.

## Design

### D1 - Decide control (#1216)

- **Placement.** In the list view's selection strip (grid `toolbar`), after
  `Save as suggested (n)` and before Clear: a Button **Decide** with a chevron, opening a
  `DropdownMenu` (`align="end"`) with three items: **Buy**, **Reserve**, **Borrow**. It shows
  while at least one row is ticked, like the rest of the strip (Grill Q2). Toolbar already
  `flex-wrap`s at 375px.
- **Selectable rows.** `enableRowSelection` widens from `canQuickSave` to a new
  `canDecide(contribution)` = not unplannable and not cancelled. Confirmed and already-saved
  rows become tickable (the owner's case is amendments). `Save as suggested (n)` counts only
  the ticked rows `canQuickSave` accepts and hides at n = 0 (Grill Q1).
- **Composition, per ticked row, whole open quantity** (pure function
  `decideComposition(contribution, way, locationId?)` in `SH/lib/boardAmend.ts`, beside
  `suggestedDecisionFor`):
  - Buy: `reserve: []`, `borrow: []`, `timely_spo_qty: 0`, `buy_qty: open_qty`,
    `order_back: false`. Order back / Document cited stay in the expanded row (Grill Q8).
  - Reserve: fill `open_qty` from the row's reserve ladder sources (the same free-stock rows
    `ReserveAddDialog` offers, `qty_free_remaining > 0`), in the engine's own order, own
    location first; `buy_qty: 0`. If the ladder cannot cover the whole line, the row is
    SKIPPED with the free total stated (Grill Q4).
  - Borrow: one `borrow[]` component from the picked location's candidate on that row
    (`borrow_candidates`, free stock at another location, `source: other_location`) for the
    whole `open_qty`; `buy_qty: 0`. A row with no candidate at that location, or too little
    free there, is SKIPPED. Donor-project borrows stay in the expanded row (Grill Q6).
  - Rows contesting the same free stock claim it in the list's current sort order, top
    first; the running tally is kept across the ticked rows so the batch never
    over-claims (Grill Q7).
- **Verdict.** `approved` when the composition equals the row's suggestion (uncovered row)
  and the reason is not needed; otherwise `amended` with the one reason. On a Confirmed row it
  is always `amended` (the server refuses `approved` there), measured against the frozen
  decision (`amendNeedsReason`'s own baseline). A row whose frozen decision already equals the
  pick is skipped as "already decided that way" (Grill Q1).
- **The Decide dialog.** Buy or Reserve where every applicable row matches its suggestion:
  saves at once, no dialog. Otherwise (any row differs, or Borrow) a small `Dialog` titled
  `Decide ${n} lines: ${Way}` opens with: for Borrow only, a `SearchableSelect` of locations
  (options = locations that hold free stock for at least one ticked row, each labelled with
  the code and `covers ${k} of ${n}`); one Reason `Textarea`, required when any row differs
  or for Borrow; Save. One reason applies to every row in this decision (Grill Q3, Q5).
- **Save.** Reuses Panel `decideMany`'s loop (chunks of 5, `decide(key, decision,
  {quiet: true})`, per-row PUT, revert on failure). No new endpoint. One toast:
  `${saved} saved as ${Way}` plus `· ${skipped} skipped: <item line (why)>, ...` capped like
  `unpostableNotices` (5 names, then "and N more"). Saved rows untick; skipped and failed rows
  stay ticked.
- **Existing drafts.** A Saved or Rejected draft on a ticked row is overwritten (PUT is an
  upsert); Undo restores the suggestion as today (Grill Q9).
- **List view only.** The grid view's cell dialog keeps Approve / Reject selected unchanged.

### D2 - Discontinued gate removed (#1217, part 1)

- FE: `lineFor` stops returning `'buy_reason_missing'` in all three branches; the reason kind
  is deleted from `unpostableDecidedFor`, `UNPOSTABLE_REASONS` and `unpostableNotices`
  (the banner, the "left out" toast count and `focusLeftOutLine` stay for `no_mirror` and
  `no_reserve_warehouse`). `supplyComposition.ts` drops the discontinued blocker, so the
  per-order sheet (`SupplyLineCard`) stops blocking too (Grill Q11).
- BE: `_check_line` drops the discontinued refusal (:5583-5587). The frozen snapshot keeps
  `lifecycle_warning` ("This product is discontinued.") and `buy_reason` (possibly null).
- Copy: `BoardTrailPopover` chip keeps "Discontinued", title becomes "Discontinued"; the
  board explanation drops the "Discontinued: the buy needs a reason." suffix; `SupplyLineCard`
  keeps its discontinued warning without "Buying it takes a reason."
- `PLAN-scm-front-planning.md` Q4 gets a dated amendment line pointing here.

### D3 - One reason box in the expanded row (#1217, part 2)

- `BoardLineDecisionPanel` keeps ONE `Textarea`, label **Reason**, in the right column where
  "Why this differs" is today (id `line-reason-{key}`). The Buy block's discontinued
  "Reason *" and every borrow row's "Reason *" go. `BorrowAddDialog` drops its reason field;
  the same-agent "who authorised" field stays there (it names a person, not a reason) and is
  folded into the stored borrow reason as today (Grill Q10).
- When the line is discontinued and buys, a `Badge` "Discontinued" sits beside the Reason
  label (no explanatory sentence; PRINCIPLES "no feature explanations in the UI"). The box is
  NOT required for that (Grill Q12). It is required (asterisk, Save disabled) exactly when
  today's rules need a reason: `amendNeedsReason`, a borrow row the engine did not suggest
  (the server requires a borrow reason), or Reject.
- **Stored fields do not change** (no migration, no BE schema change). On save the one box
  fans out: `reason` = box; `buy_reason` = box when discontinued and `buy_qty > 0`, else
  unchanged (null); every `borrow[i].reason` = box when non-blank, else the engine's own
  suggested reason for a suggested borrow row. `confirmLineFrom` is unchanged, so Confirm
  sends `amend_reason`, `buy_reason` and `borrow[].reason` as before (Grill Q13).
- Seeding an existing draft or frozen decision: box = first non-blank of `reason`,
  `buy_reason`, the first `borrow[].reason` (older records with three different texts show
  the first; the others are still in the trail).
- The approving save path now carries the box too (today it drops `reason`), so a reason
  typed on a line equal to its suggestion is kept.
- `BoardTrailPopover` prints one "Reason" line when the stored texts are identical, instead
  of repeating it per field.
- The verdict column's Reject popover keeps its own reason box: it is not in the expanded row.

### Reuse, no new machinery

Decide is a FE composition function plus the existing per-row draft PUT. No bulk endpoint:
`decideMany` already does n PUTs in chunks of 5 for Save as suggested, which is the same
load. Trigger to build a bulk endpoint later: a measured board where a Decide over the
ticked rows takes longer than ~3 s end to end.

### No-motion list (DESIGN-LANGUAGE frequency gate)

- The Decide menu uses the existing `DropdownMenu` (`MENU_SPRING` in, `SURFACE_SPRING_EXIT`
  out); the Decide dialog uses the existing `Dialog` (`SURFACE_SPRING`). No new motion.
- Nothing else animates: no row flash on save, no dimming of ticked rows, no animated count in
  the strip, no transition on the Reason label's Discontinued badge, no motion on the rows
  that untick after save, no animation on the banner losing its discontinued sentence.
- Pressed states use `PRESSED_CLASS` on Decide and the dialog's Save, as every button does.

## Slices

- **S1 - Discontinued gate removed (BE + FE).** `_check_line` refusal gone; `lineFor` /
  `unpostable*` / `UNPOSTABLE_REASONS` / `unpostableNotices` / `supplyComposition` blocker gone;
  copy on the trail chip, board explanation and `SupplyLineCard`. Tests flip:
  `test_so_supply_confirmation.py:1185` becomes "confirms without a reason, OI row raised",
  banner tests drop the discontinued case. Smallest, ships the owner's "first, remove the gate".
- **S2 - One reason box (FE).** `BoardLineDecisionPanel` single Reason box + fan-out +
  seeding + Discontinued badge; `BorrowAddDialog` loses its reason; approving save carries the
  box; trail dedupe. Depends on S1 (the discontinued Reason input's asterisk is S1's rule).
- **S3 - Decide (FE).** `canDecide`, `decideComposition`, the strip button + menu + dialog, the
  claim tally, the toast, Save as suggested counting only its own rows. Depends on S2 (the
  Decide dialog's reason fans out through the same helper).
- **S4 - Lane end.** Browser evidence run (agent-browser, sidebar nav, 375px + 1280px),
  reviewer + kill test, PR checklist. `security-reviewer`: not run, the diff is outside its
  surface (no auth, RBAC, ingest, upload or company scoping change).

Phase 1 (FE first) builds the S1 FE half, S2 and S3 with no backend change: every write
already goes through the existing draft PUT, so no service mock is needed; the only
behaviour Phase 1 cannot show is a discontinued line with no reason confirming, which waits
for the S1 BE change in Phase 2. Phase 2: the tester writes the red tests from the UAC
before the coder makes them green.

## Rulings

(Left empty for the owner.)

## Grill questions

Each with a recommended answer and why. The owner rules; the answers above assume the
recommendation until then.

1. **What does Decide do to a row already Confirmed?** Recommend: it is tickable and Decide
   saves an `amended` draft against the frozen decision (the server already accepts
   `amended` on a covered line and refuses `approved`), reason required because the line is
   changing after confirmation; the row reads Change proposed/Saved until Confirm writes the
   new revision. A Confirmed row already decided exactly that way is skipped ("already
   decided that way"). Why: the owner's own words are "for amendments, they just need to buy,
   reserve, or borrow", and amendments are confirmed lines. Save as suggested keeps refusing
   Confirmed rows (it would 409).
2. **Does Decide show all the time or only with a selection?** Recommend: only while rows are
   ticked, inside the existing strip. Why: every bulk verb on this page and on the users list
   appears with the selection; a dead button at rest adds nothing.
3. **Is a reason required for a Decide that disagrees with the suggestion?** Recommend: yes,
   ONE reason in the Decide dialog covering every ticked row, and no dialog at all when the
   pick matches every row's suggestion (Buy or Reserve). Why: the expanded row already requires
   "why this differs" for any change from the suggestion (`amendNeedsReason`) and purchasing
   reads it; asking once per batch keeps the owner's two-press goal for the common case. The
   alternative, a fixed text like "Decided on the planning board", records nothing useful.
4. **Does Reserve need a location?** Recommend: no. Reserve fills the whole line from the
   row's own reserve ladder in the engine's order (own location, own group, pools); a row the
   ladder cannot cover in full is skipped and named with its free total. Why: the server only
   accepts reserves from that ladder (`_reserve_ladder_locations`), so a picker would offer
   choices that are either implied or refused; the stock transfer is proposed automatically on
   Confirm when the source is not the line's own location. The owner named a location only for
   Borrow.
5. **Borrow needs a reason on the server (`_check_borrow`). Does Decide ask for it?**
   Recommend: yes, the Decide dialog's one Reason box, required for Borrow. Why: the borrow
   reason is the donor-impact record (AC-B09/B10 of the front planning plan); dropping it is a
   separate ruling, not a UX change.
6. **Which locations does Decide > Borrow offer?** Recommend: other LOCATIONS with free stock
   (`other_location`) that are a borrow candidate for at least one ticked row, each labelled
   `covers k of n`. Borrowing from another project's hold (`other_project`, donor impact per
   donor SO) stays in the expanded row. Why: the owner said "Borrow can just select the
   location"; a donor project is not a location and its impact differs per donor.
7. **When ticked rows contest the same free stock, who gets it?** Recommend: the list's
   current sort order, top first, with a running tally; rows that no longer fit are skipped
   and named. Why: it is what the planner sees; the server still validates everything at
   Confirm.
8. **Does Decide > Buy set Order back?** Recommend: no, Buy is a plain Buy; Order back and
   Document cited stay in the expanded row. Why: order back needs a cited document per line.
9. **What happens to a row whose saved draft or suggestion disagrees with the pick?**
   Recommend: the pick wins and overwrites the saved or rejected draft (Undo restores the
   suggestion); a row whose suggestion differs from the pick is saved `amended` with the
   Decide reason; its pill reads Saved. Why: ticking a row and choosing a way is the planner's
   explicit decision.
10. **Does the Borrow add dialog keep its own reason field?** Recommend: no, the one box in
    the row is the reason; the same-agent "who authorised it" field stays in the dialog. Why:
    the owner wants one text input for reasons; "who authorised" is a name, and it is already
    folded into the stored reason.
11. **Does removing the gate also apply to the per-order supply sheet (`SupplyLineCard`)?**
    Recommend: yes. Why: the server rule is shared; keeping the sheet's blocker would make one
    screen refuse what the other confirms.
12. **Is the reason box required at all when the product is discontinued?** Recommend: no. A
    Discontinued badge sits beside the Reason label and the box is optional for that cause.
    Why: the owner said "remove that gate"; a required box that blocks Save is the gate moved
    from Confirm to Save. If the owner wants it required, the ruling to write is "required at
    Save, never at Confirm", and the badge gets the asterisk.
13. **What does the stored field become?** Recommend: nothing changes in storage. The one box
    fans out on save into `reason` (-> `amend_reason`), `buy_reason` (discontinued Buy) and
    `borrow[].reason`, so purchasing's OI, the trail, the transfer and every existing reader
    keep working with no migration. Why: simplest thing that works; one box is a UI fact, and
    the three fields are read by different consumers today. Trigger to collapse them into one
    column later: a reader that needs to tell the three apart stops existing.
14. **Does the Rejected verdict popover (verdict column) keep its separate reason box?**
    Recommend: yes. Why: it is not in the expanded row, and rejecting from the column without
    opening the row is the point of that popover.
15. **Should Decide also Confirm?** Recommend: no, Decide saves drafts like Save as suggested;
    Confirm stays the one commit. Why: Confirm is where the batch, the left-out banner and the
    OI rows happen, and it has its own deferred window.
16. **A row with a landed own arrival (`planning_change_buy_over_own_arrival`, the server
    409s a Buy over landed stock).** Recommend: Decide > Buy skips it with the server's own
    sentence when the board exposes the landed credit on the contribution (to verify in S3;
    if it does not, the Confirm refusal names it as today). Why: skipping at Decide is kinder
    than a 409 at Confirm, but it must not re-implement server arithmetic.
