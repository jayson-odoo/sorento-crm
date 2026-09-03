# PLAN: Fulfilment planning feedback batch, 2 Sep (BRW first, per-line walk, saved decisions, upload speed)

Status: IN REVIEW - S1 to S5 are all in PR #553 (the ONE final PR, captain 2 Sep), every slice delivered. S1 DONE; S2 Phase 1 + Phase 2 DONE (ladder v8 live on the lane); S3 and S3b Phase 1 + Phase 2 DONE, plus a first-pill-truncation fix (3 Sep); S4 Phase 1 + Phase 2 DONE (3 Sep - `projects.so_supply_decision_drafts`, the two draft routes and the confirm-time promotion are live on the lane, the Phase 1 mock is deleted); S5 DONE (folded in from #546). Code review round 3 fix batch (3 Sep, two coordinator messages) folded in: B1/B2/C1/S1-S3/N1-N7/C4-C8 and nits - `stale` rewritten to judge the LINE's own facts rather than the proposal (S1), the pill/Undo-all race fixes (B1/C1), the availability echo fix (B2), 422 line validation (S3), the `changed` count (C4), ladder v8 wiring gaps (C5/C8) and import-failure audit accuracy (C6). Code review round 4 folded in: C2 - a saved decision is now keyed by the CORE sales order line rather than by the board's line number, because that number is positional on any order whose lines are not all mirrored (see S4's deviation note) - and C3 - the board's proof now reads the walk's own share and own-bin ledgers, so it stops offering a line stock an earlier line of the same walk already took. Captain's 3 Sep testing round folded in: D1 (the stock drill's five-pool net, see R-K), D2 (Available for Project outside a site pool, see R-K), D3 (the expanded ledger's own header sticks under the outer one - tried, reverted 3 Sep, see R-K) and D4 (the Save button stays Saved, see S4). Fix round 5 folded in: D5's own last gap - the per-order sheet can now confirm the engine's own pool-share split too, not only the board: a site pool's own `pool_allowances` and `pools_net` now reach `SupplyLine` the way the board's cell already states them on its locations (B2). B1 (a re-save the server REJECTS no longer renders as Saved - every "clean" state change in `BoardLineDecisionPanel.save()` now waits for the write to actually land; D6 already names a different fix, "two readers for one five-pool net" - not reused) and Q1 (`import_jobs.error` now stores the exception summary even off a 5,000-char traceback - the full text still reaches the server log, only the INPUT to the summariser was truncated before). S2 (a group row's Available for Project reads its own Available rather than "Not stated"), S3 (`_resolve_core_line` scoped to the record that HOLDS the core order, matching `_mirror_addressing`) and S4 (the Total row's Available column agrees with Available for Project outside a pool) also land this round. Fix round 6 folded in: D7 Buy follows the remainder of the line, so a reserve edit no longer freezes `buy_qty` short of the open quantity (`af739fff1`); D8 the expanded ledger's own sticky header was tried again and reverted a second time, captain 3 Sep (`ecff560b7`); D9 the expanded ledger's Total quantity is the signed net of its own rows on a group or site pool reading, rather than the S/O-only sum that disagreed with the running balance (`b8515bdde`). Fix round 7 folded in: B-1 the Buy switch is now STATE seeded once from the opening draft, not derived from the numbers, so clearing or zeroing a reserve box no longer flips it on and unmounts the Reserve section mid-edit; S-1 `ReserveAddDialog`'s opening quantity excludes the derived Buy from the remainder it is capped against, so Add-location no longer falls back to a bin's whole free stock on an already-composed line; N-2 the ledger Total's code comment cites the real AC-2.6c rather than an AC id from a different plan; N-3 the upload-activity error line wraps with `break-words`, not `break-all`. Fix round 8 folded in: D10 the sales order page's Lines tab now shows a SAVED (unconfirmed) decision too, not only a confirmed one - `SalesOrderService._saved_lines`/`_saved_components` read `projects.so_supply_decision_drafts` by CORE line and convert the draft's `BoardDecision` JSON into the board's own component vocabulary, and the Decided/Decision columns render a Saved pill and the saver's name until Confirm replaces it with Rev N; an approval saved with no typed composition (`{verdict: "approved"}`, the shape `BoardLineDecisionPanel.save()` posts when nothing was amended) has none of the three kinds this reads and prints Decided "-" beside the pill, which is the true state of SO419370 line 1 on the dev DB used to verify this round - not the "Buy 3" the brief assumed. D13 folded in (3 Sep, R-M): another ownership group's free pile is now capped by that group's WHOLE open book, so an oversold group is never read as a donor of free stock - `supply_assignment.group_book_positions` is the new pure reader, `_other_group_free_at_own_date` applies the cap and returns the groups it refused, step 1's sentence states the PILE and the date instead of the take, the `use` option row prints the refusal, and the Suggestion card pill names the lending group the way the options row already did. D14 folded in (captain, 3 Sep): quick save as suggested and per-line Undo on the fulfilment board, frontend-only against the existing draft write path - a planner can now tick several untouched rows in the list, or select-all / "Save all suggested" in a cell's Contributing lines tab, and save the engine's own composition on all of them in one press (`suggestedDecisionFor`, `_shared/lib/boardAmend.ts`, wraps `decisionFromAmendDraft(suggestionDraftFrom(contribution), '')` exactly as `BoardLineDecisionPanel`'s own untouched Save does), and a single saved row can be undone in place (`onDecide(key, null)`) without the board-wide "Undo all" or its confirmation dialog, since one line's undo is reversible with another quick save. Delta review round folded in (3 Sep): R-M's cap is now spent ONCE per lending group across the whole walk and across one confirmation's lines - it was applied per unit over a bin-keyed ledger, so two units whose dates brought different bins of one group into view were each handed the whole spare book and both Confirms passed (AC-2.12c); the cell dialog's bulk quick save no longer overwrites an amended draft (an already saved row is not selectable there, matching the list view) and "Approve selected" now carries the suggested composition D11 fixed, so the duplicate "Save as suggested (N)" button is gone; `save_draft` keeps a stored `proposed` when a re-save omits it. ASYMMETRY, for the captain to confirm: the board-wide "Undo all" keeps its confirmation dialog and the per-line Undo has none, on the reading that one line's undo is reversible with another quick save while the board-wide one is not. Next review round pending.
Captain rulings: 2 Sep 2026 user test on SO419208 / SO419370 / SO418324 (screenshots on the session)
Probe: `scratchpad/probe_brw_first.md` (read-only, worktree `.claude/worktrees/scm-brw-first`, branch `probe/scm-brw-first` off `origin/main cf255833d`)
Lane: engine lane `.claude/worktrees/scm-fulfilment-2sep` branch `feat/scm-fulfilment-feedback-2sep` FE :3080 BE :8080 (S1, S2, then S3, S3b, S4); import lane `.claude/worktrees/scm-upload-2sep` branch `feat/scm-upload-speed-2sep` BE :8090, no FE server (S5). Both off origin/main. Own `.env` per lane (API_PORT, NEXTAUTH_URL, FASTAPI_INTERNAL_URL), venv symlinked to the primary checkout, node_modules cloned from it.
UAC: `scm-fulfilment-feedback-2sep-acceptance-criteria.md` (same folder)

## Why

Users planned three real orders on 2 Sep and came back with six asks. Every ask was measured
against `origin/main` code and the prod-copy DB (24 Aug) before this plan was written.

Verified facts this plan stands on:

- The ladder walk (`app/services/scm/front_planning_engine.py:669-838`, `walk_line`) is
  hard-wired control flow: use, order_borrow, supply_borrow, pool, buy. The pool step offers
  `max(five-pool net, 0)` (`_draw_pool`, `pool_reserve_capacity`) and is skipped entirely for
  a dealer hot-selling product. A step covers the whole unit or gives nothing (R10/R33).
- Ladder v6 (#365) plans an order's lines for one product and one date as ONE unit. SO419208
  lines 2 (1305) and 3 (135) are one unit of 1440; on hand 145 cannot cover 1440 whole, so the
  unit reads Buy 1440 while 135 sits at BRW-BB.
- Pile attribution order (`ProjectSupplyService._pile_order`, `project_supply_service.py:213`)
  is rank score, date, SO number, line number. Inside one SO on one date, line 2 (1305) is
  served before line 3 (135).
- Save decision (`BoardLineDecisionPanel.tsx:198-213`) writes React state only
  (`FulfilmentBoardPanel.tsx:197` `useState<BoardDraft>`). The ONLY persistence is Confirm,
  `POST /project-sales/fulfilment-planning/confirm-all`, into `so_supply_decisions`
  (`app/models/project_so.py:1157-1162`, state `active | superseded | challenged`, no draft).
  No localStorage. Navigating away loses every saved line.
- The Reserve section of the decision panel edits quantities of rows the engine seeded; there
  is no "add location" control (Borrow has `BorrowAddDialog`). The backend
  `ConfirmReserveComponent` (`app/schemas/project_supply.py:290`) accepts any warehouse, so
  the manual "take from BRW" is a frontend gap only.
- Outstanding SO upload: `outstanding_import_service.apply()` runs about one SELECT per
  changed line (`_closed_line` per ADDED row at `:2318`, a primary-key re-fetch per CLOSED /
  changed row at `:2272`, `:2400`, `:2413`) inside ONE transaction that
  `_run_scm_upload_job` commits only at the end (`app/tasks/import_tasks.py:3524`). The file
  that died after an hour was the completed full book 2020 to Sep 2026, 82,257 rows.
- Progress card frozen at 0: the job writes `processed_rows=0` at start and the real count
  only at completion; `ImportOutcome.flush` writes outcome rows every 1,000 on its own
  session and never touches the job row. That is why the outcomes page shows 10,000 while
  the activity card shows 0 / 22,111.
- `spo_allocations` has three writers (`scm_upload` occurrence line numbers,
  `scm_spo_history` file line numbers, manual packing list with `source_system NULL`), each
  deduping only inside its own `source_system`; `scm.on_order_v` sums every open row.
- Fulfilment settings already live on the priority policy row
  (`app/services/scm/priority.py:189` `FULFILMENT_SETTINGS_DEFAULTS`, `fulfilment_settings`),
  read by the engine through `ProjectSupplyService._fulfilment_settings()`. The two new
  numbers join that row; no new table.

## Captain rulings (the contract)

- R-A. **BRW first, for every product.** The site pool of the asking bin (BRW for BRW-IB and
  BRW-BB) is asked BEFORE own locations. The dealer hot-selling gate that removed the pool
  entirely is retired; the share rule below is what keeps stock for dealers.
- R-B. **Share rule, two windows, both configurable (pile base, ruled 2 Sep).** The site
  pool keeps `pool_share_pct` (default 50) of its free pile for dealers; a project line may
  take up to the other half. A line due within `immediate_window_days` (default 30) takes
  `min(line qty, pool free x (100 - share) / 100, max(pools_net, 0))` from the pool and the
  remainder walks the ladder. A line due later takes the WHOLE line from the pool only when
  the line fits inside that same allowance, otherwise the pool gives nothing (there is time
  to buy). SRTWB241 qty 3 with 47 free takes all 3; a 650 line with 900 free takes 450 and
  walks 200. "Half of the line" was considered and rejected: it splits a line of 3 into 1 + 2.
- R-C. **Split, never mix.** The pool share is its own sub-unit; the remainder walks the
  existing ladder whole or nothing (own locations, borrow on hand, borrow incoming, buy).
  R10/R33 stand for the remainder. The user still sees ONE contributing line whose
  Sourced-from cell lists both parts ("BRW 325 · Buy 325").
  **The CONFIRM's carve-out is deliberately wider than the walk (captain, 2 Sep):** it
  admits a Reserve at ANY site pool of the line's chain, inside that pool's own allowance
  and inside the one five-pool net, beside a Buy - because S3 lets a planner add a pool
  location to Reserve by hand (R-G) and a composition the product invites must confirm. The
  ENGINE's own R-L step stays whole-or-nothing, so the walk never proposes another site's
  part share beside a Buy.
- R-D. **Five-pool net stays the bound.** The pool never lends beyond
  `max(pools_net, 0)`; the site pool's own free pile says WHERE, the net says HOW MUCH.
  A dealer order booked at DC1 with no DC1 stock is served from BRW, so BRW's own free is
  not free.
- R-E. **Per-line walk inside the unit, smallest first.** The unit (same order, product,
  date) stays one board cell, but its contributing lines walk one at a time in ascending
  quantity, each sharing the piles the previous one left. One contributing line is never
  half covered, except by R-B's immediate share. Supersedes the v6 "one date, one quantity"
  walk; v6's "lend a donor once" stays.
- R-F. **Save decision persists on the server and answers.** A saved line survives leaving
  the page, another device, and another planner. Confirm promotes saved lines; Undo removes
  them. The row answers the click (pill, toast) within the interaction, per DESIGN-LANGUAGE.
- R-G. **A planner can add a reserve location.** Any location with free stock, the site
  pool included, can be added to Reserve by hand; the server's on-hand check stays the
  guard.
- R-H. **Upload commits per document and reports live.** Minutes, not hours; the card
  counts up while the job runs. Completed books are welcome on the SO and PO channels.
- R-I. **Dropped (markup 2 Sep: "this one don't need handling").** SPO duplicates get no
  slice; the three-writer finding stays recorded under Why for the day it matters.
- R-J. **Sourced-from is pills, not prose.** One pill per component ("BRW 325", "Buy
  325", "Own 23 BRW-IB"); the cell shows as many as its width fits and folds the rest into
  a "+N" pill; clicking any pill, "+N" included, opens the composition with each part's
  location, quantity, kind and the option row it came from. A wide column shows every pill.
- R-K. **The BRW allowance is visible in the lightbox as "Available for Project" (markup
  2 Sep).** The Stock tab gains an "Available for Project" column on EVERY site pool row and
  on the site pool subtotal = Available minus the kept share, capped by the five-pool net
  (BRW 47 free reads 23). The Suggestion card is pills only (markup round 2: "no
  information overload"), no sub-line. The expanded ledger's running column is client-side
  `Balance after` (`StockDocumentsPanel.tsx:107-235`: on hand rows first, then S/O minus,
  SPO plus, Hold minus, sorted by date, supply before demand). Under a SITE POOL section
  that column becomes `Available for Project` = floor(Balance after x (100 - share) / 100)
  capped by the five-pool net (markup round 4); group sections keep Balance after. The pool
  summary row keeps Available (dealers) and gains Available for Project. The five-pool net
  must reach the Stock tab (today it lives only on the board's `BoardCellLocation.net`).
  **One net, one reader (D1, captain 3 Sep):** the ledger's cap comes from `stock-detail`,
  which read it off `ProjectSupplyService.netting()` - a reader whose pile span is the
  products the REQUEST has asked about, and a drill-down asks about none, so every pool
  netted 0 and the ledger printed Available for Project 0 on every row under a subtotal
  reading 71. It now states the net of the SAME position its own membership came from.
  **A row with no dealer share prints its Available (D2, captain 3 Sep):** on `own`,
  `group` and `other_group` rows and on the GROUP subtotal, Available for Project IS
  Available (the same signed figure, negative included) - nothing is kept back outside a
  site pool - and the Total row's is the signed sum of the group and site pool subtotals.
  The column is never blank and never a dash: "-" read as missing data.
  **D3 sticky ledger header: tried, reverted 3 Sep (captain: confusing, header covered
  rows).**

- R-L. **SUPERSEDED 3 Sep by R-N (`PLAN-scm-pool-chain-first.md`): step 0 now walks the whole
  pool chain, so the spill below has nothing left to find and is deleted. What R-L ruled about
  the OTHER pools' allowances still stands; only its TRIGGER is retired.** Other site pools
  still supply the remainder (ruled 2 Sep, "B, the current behaviour"). Step 0 asks the asking bin's own site pool. When own locations and both
  borrows cannot cover the remainder whole, the OTHER site pools are asked, in the v7.1 draw
  order (by on hand), each under the same allowance rule (its own Available minus the kept
  share, all bounded by the one five-pool net), whole or nothing. A DC1-IB line of 300 with
  DC1's pool empty, own group 110, and BRW sparing 400 reads "BRW 300", not "Buy 300".
  The share ledger is keyed by (product, pool); the net ledger stays one pile.

- R-M. **Another ownership group's free pile is capped by that group's WHOLE open book
  (ruled 3 Sep 2026, from a production cell).** SO419417's SRTWT7443 line - 4 due 5 October
  at BRW-BB - was proposed "Use own location: 4 from BRW-IB. BRW-IB has 4 free outside the
  BB group, and free stock is owed to nobody". On that day BRW-IB held 2,237 on hand against
  2,684 of open IB demand (1,708 due on or before 5 October, 976 after), so IB was 447 short
  on its own book; BB itself was oversold by 5,450 and the BRW pool read Available -91.
  The date-bounded reading `free_piles_at` makes only subtracts demand due ON OR BEFORE the
  asker's date, so an oversold group read as a donor of free stock.

  So for each candidate bin of ANOTHER group, free = `min(existing date-bounded free,
  max(group book position, 0))`, where the group book position is that group's on hand plus
  the supply the assignment counts (events dated on or after `as_of`; an overdue document
  stays uncounted per R31), less ALL of its open demand, less any confirmed hold another
  group has already taken out of it - spread over the group's bins in the draw order they
  already come in. **A group whose book is short gives NOTHING**, and the walk continues:
  pool share, borrow from a later order (donor named, impact shown), buy. Own-group draws
  are unchanged - they already stop at the group's own short.

  The sentence states the PILE and the day it was measured on, never the take: "BRW-IB has
  529 free outside the BB group at 5 Oct 2026, none of it owed to a later IB order". Where
  the group is short the `use` option row reads 0 with the refusal: "IB group is 447 short
  on its own book, nothing to spare".

  The Suggestion card pill and the summary cards read an other-group source with the same
  words the board's options row already used ("Use IB group stock", "Use incoming from IB
  group"); "Use own location" stays for own-group sources.

  **ONE BOOK, SPENT ONCE (delta review, 3 Sep).** The budget belongs to the GROUP and to the
  WHOLE walk, not to a unit: it is seeded into the walk's own offer ledger the first time any
  unit reads the group and drawn down by what each unit composed off it. Applied per unit it
  was handed out twice - a unit due 1 October seeing the group's floor and a unit due 20
  October seeing an arrival at another of its bins each got the whole of it, and because the
  confirm-time recheck seeds capacity per (product, location) from each unit's own capped
  read, both Confirms passed and the lending group ended short on its own book. Confirm now
  carries the same bound through `_CapacityLedger` under the group's key, so the second line
  is refused in the wording an exhausted bin already gets. An exhausted BUDGET says nothing
  extra on the option row: only a SHORT book is a refusal a planner can act on.


## Slices

### S1 - policy fields (migration, settings UI)

- `priority_policy.immediate_window_days INTEGER NOT NULL DEFAULT 30` and
  `priority_policy.pool_share_pct INTEGER NOT NULL DEFAULT 50` (migration number = next free
  at implementation; 456 to 458 are claimed by #490 / #491 / #493).
- `FULFILMENT_SETTINGS_DEFAULTS`, `fulfilment_settings()`, `save_fulfilment_priority`, and
  the existing `GET/PUT /scm/policies/fulfilment-priority` route (the one `transfer_days`
  rides; no new endpoint), Policies page inputs beside Transfer days: "Immediate window
  (days)" and "Pool share (%)", bounded 0 to 365 and 0 to 100. Phase 1 shipped 2 Sep
  (lane commit 9686f0f53); Phase 2 must also update `FulfilmentPriorityPanel.test.tsx` and
  `scmPolicyService.test.ts` exact-payload assertions.

### S2 - engine v8: BRW share step + per-line walk (the change users asked for)

- `walk_line` gains step 0 `pool_share`: `allowance = min(floor(site pool AVAILABLE x
  (100 - share) / 100), max(pools_net, 0))`, `share_qty = min(open_qty, allowance)` inside
  the window; beyond the window `share_qty = open_qty` if `open_qty <= allowance` else 0.
  When `share_qty >= open_qty` the step covers the line whole (chosen `pool_share`).
  Otherwise the walk runs on `open_qty - share_qty` with the pool step removed (the pile
  already answered) and the result is `pool share + remainder`. Beyond-window and
  beyond-coverage bail (step 0 today) stays in front.
- **Amended in implementation (2 Sep, S2 Phase 2), three points:**
  (a) the share's base is the pool's **Available** (`on hand - SO + SPO`), not its free
  pile - that is the figure R-K's own AC-2.6b prints ("Available 590 ... Available for
  Project = min(590 x 50 %, five-pool net)") and the figure the expanded ledger's running
  column is a share of, so one base keeps the walk and the lightbox on one number; the
  pool's FREE pile still bounds WHERE the units come from, exactly as `_draw_pool` always
  did. (b) the allowance is a **running ledger per product across the walk**, not a fresh
  reading per line: the share is a share of the PILE, and without the ledger a pool of 20
  was offered as 10 to one line and 10 to the next and lent all of itself. (c) the
  whole-line rule at CONFIRM gains one carve-out for exactly this composition (a Reserve at
  a site pool, inside the allowance, beside a Buy), or the engine's own v8 proposals could
  not be confirmed.
- Options table: five rows in walk order become `Use BRW stock` (share or whole, with the
  quantity it can give), `Use our locations`, `Borrow on hand from a later order`,
  `Borrow incoming from a later order`, `Buy`. The pool borrow half (R34) stays inside the
  first row as today.
- Per-line walk: `_proposals_for` / the board's unit walk iterate the unit's contributing
  lines in ascending `qty`, then line number, feeding each the piles left by the previous
  one. Two ledgers were needed for that and are new: the unit's OWN ownership-group pile
  (kept per bin AND per floor/water, or the second line is offered a floor the first
  emptied) and the pool share above. The unit cell shows the sum; each contributing line shows its own composition.
  `_pile_order` gains `qty` ascending between date and SO number so the Stock tab's
  running Available reads the same order (135 then 1305).
- Lightbox (R-K): `stock-detail` returns `available_for_project` per site pool row and on
  the site pool subtotal (the same allowance the walk used, so the two never disagree);
  Stock tab column "Available for Project" after Available; no Suggestion sub-line.
- `LADDER_VERSION = "v8"` both sides. Tests: rewrite the step-order assertion in
  `test_ladder_v7_borrow.py:1392`, re-bless `front_planning_golden.py` (AC-L2 becomes "site
  pool share before the group"), add the six walks in the UAC as new golden cases.
- Reorder engine untouched: the pool's reserved share reaches it the same way a pool draw
  does today (a `so_supply_decisions` reserve at the pool warehouse).

### S3 - Reserve add-location (manual BRW)

- `BoardLineDecisionPanel` Reserve section gains "Add location", the same dialog shape as
  `BorrowAddDialog`: locations with free stock for the product, pool and other groups
  included, each with its free quantity; picking one seeds an editable Reserve row.
- Server: no change (`ConfirmReserveComponent` already accepts any warehouse and
  `_check_reserve_against_on_hand` guards it). Add one test that a pool warehouse is
  accepted in Reserve.

### S3b - Sourced-from pills with overflow (R-J)

- New primitive `components/common/PillOverflow.tsx`: takes pills + a renderer for the
  popover, measures its own width (ResizeObserver, no fixed count), renders the pills that
  fit and one "+N" pill for the rest; keyboard reachable; the popover is the SCM lightbox
  shell's small variant. Foundation, not per-cell: the board's Sourced-from cell, the
  Contributing lines Sourced-from column, and the Stock tab's Taken cell all adopt it.
- Pill wording = kind + qty + location, ordered as the composition is ordered (share first).
- Column resize (DataGrid `columnsResizable`) reflows the pills live.
- N7 (code review round 3): pills carry no `title` attribute - a departure from the DataGrid
  truncate+`title` convention elsewhere in this codebase, deliberate here because the popover
  IS the disclosure R-J itself asks for ("clicking any pill ... opens the composition"); a
  second, competing disclosure (a browser tooltip) on the same element would answer the same
  question a worse way.
- N4 (code review round 3, accepted, no code): the "+N" pill wrapping to its own row when
  pill 0 does not leave room beside it grows the column's own row height by roughly 20px.
  Accepted as the trade `flex-wrap` makes for "a quantity is never truncated" (S3b fix,
  AC-3b.4) - the alternative was capping pill 0's own text, which is the thing this fix
  exists to stop.

### S4 - saved decisions (server draft + response)

- Save decision is PERSISTED (superseded by the Deviation below, which puts it in its own
  table rather than a `draft` state on `so_supply_decisions`) = `PUT
  /fulfilment-planning/lines/{contribution_key}/draft` (upsert, one row per contribution
  key, `saved_by`, `saved_at`); Undo = DELETE. Confirm promotes the keys it confirms (the
  same write as today, and it DELETES their drafts in that transaction). The "reading the
  draft when the body carries no composition" half is not built and is not needed:
  `confirmLinesFor` composes every line it posts, from the saved decision or from the
  engine's own suggestion, so the body never reaches the server without a composition.
  Board GET returns drafts in `contributions[].draft` and the panel seeds `draft` state
  from them on load.
- Feedback: pill goes `Suggested` to `Saved` on the row (plain "Saved", markup 2 Sep; the
  saver's name lives in the popover), the button shows a check state and KEEPS it, disabled,
  until the line is edited again (D4, captain 3 Sep: the old 600 ms flash read as the save
  reverting - "shows saved then jumps back"), a sonner toast
  "Line 3 saved · 4 to confirm", the header counter updates as today.
  Leaving with unsaved edits in an OPEN panel keeps the existing `UnsavedDecisionPrompt`.
- Drafts are shared, not per user (one planning team; a second planner sees the same saved
  lines and the pill names who saved).

**Phase 1 note (3 Sep).** The FE was built against the contract above, no backend change:
`BoardContribution.draft?: BoardLineDraft | null`
(`BoardLineDraft = { decision: BoardDecision; saved_by: string; saved_at: string; stale?:
boolean }` - `stale` is an ADDITION to the contract stated above, S4/AC-4.4's own predicate,
below); `_shared/services/fulfilmentPlanningService.ts` gains `putLineDraft` /
`deleteLineDraft`, routed through a NEW `_shared/lib/fulfilmentS4Mock.ts` overlay behind one
`S4_MOCK` flag (the `fulfilmentV8Mock.ts`/S2 Phase 1 shape: a module-level map,
`getPlanningBoard` stamps every response with it); `useFulfilmentPlanning.ts` gains
`useLineDraftMutation()` (`{ save, remove }`, invalidates `PLANNING_BOARD_KEY` only, no
success toast - the toast is `FulfilmentBoardPanel`'s own, off the FRESH draft).
`FulfilmentBoardPanel.tsx`'s `decide()` is now async and optimistic: local `setDraft` first,
then the mutation, reverted on error; a NEW `confirmSummaryFor` (extracted out of the panel's
own `confirmSummary` into `_shared/lib/fulfilmentBoard.ts`) lets the save toast read
"N to confirm" off the draft it JUST wrote rather than a stale render. `BoardDecisionPill.tsx`
collapses `approved`/`amended` into one verdict, `saved` ("Saved" - the composition is in the
expanded row already), and reads the saver from a small `Popover` (`BoardRankPopover.tsx`'s
shape) showing "Saved by \<name\> · \<absolute timestamp\>" (`formatDateTimeInMalaysia`, NOT a
relative label - this codebase's own `describeLastActivity` states why one screen over: a
relative stamp "changes meaning depending on when the page happened to be loaded", so the
brief's "relative time" wording is not followed here). `BoardLineDecisionPanel.tsx`'s Save
button shows a `CheckCircle2` state after `onDecide` resolves and holds it, disabled, while
the line is untouched (D4). "Undo all" (the only
existing clear path - a per-key Undo control does not exist in this UI) now calls
`decide(key, null)` per key instead of a bare local `setDraft({})`, so a discarded draft is
actually deleted server-side and does not re-seed on the next board read.

`stale` (AC-4.4, "a line saved but then re-suggested by a new upload"): `matchesSuggestion`
as named in the brief compares a composition against `contribution.proposed`'s CURRENT,
LIVE value - applying it directly to a saved decision is always false the instant an
amendment is saved (an amendment differs from the suggestion BY DEFINITION) and always false
for an approval (which carries no frozen composition to compare), so neither reading detects
drift. `fulfilmentS4Mock.ts` instead keeps a JSON-stringified snapshot of
`contribution.proposed` alongside the draft AT SAVE TIME and compares it to the CURRENT
`contribution.proposed` on every board read; `lineFor` (`fulfilmentBoard.ts`) excludes a
stale line from `confirmLinesFor`/`plannedLineCount`/`confirmSummaryFor` the same way it
excludes a rejected one. Phase 2's real drafts table needs the equivalent: a snapshot column
on the row, taken at save time, compared against a fresh `propose_line` call on GET.

**Deviation (3 Sep).** Drafts live in a NEW table `so_supply_decision_drafts`, keyed by the
contribution key (sales order id, line no, item code, bucket key), carrying the composition
as JSONB, `saved_by`, `saved_at`, and a `proposed_snapshot` JSONB column for the `stale`
comparison above - NOT `so_supply_decisions`, because that table is one row per ORDER
REVISION (`revision_no` and `line_snapshots` NOT NULL, one-active partial index per
`(pso_id)`): a per-line draft on it would either loosen the NOT NULLs for a row that is not a
revision, or fabricate a revision number and a snapshot for a decision that has not been
confirmed - both weaken a constraint the confirmed audit trail depends on. Confirm deletes
the drafts it promotes in the same transaction that writes the new revision.

**Phase 2 as built (3 Sep).** Migration `461_so_supply_decision_drafts`, model
`SOSupplyDecisionDraft` (`app/models/project_so.py`), service
`app/services/project_line_draft_service.py`, routes `PUT` / `DELETE
/fulfilment-planning/lines/{contribution_key}/draft` on the EDIT permission, `draft` on
`BoardContribution` (schema + `_contribution()` + `_attach_drafts()`), and the promotion
delete inside `ProjectSupplyService._write_decision`. Three departures from the deviation
above, each because the code says otherwise:

- **The order column is the CORE sales order** (`sales_orders.id`), not the planning mirror:
  `_Row.key` is built from `str(order.id)` where `order` is a core `SalesOrder`, and a line
  whose order nobody has adopted still has a key and is still saveable. Confirm reaches it
  through `order.so_id`.
- **Identity is the CORE SALES ORDER LINE, and every part of the key is stored display**
  (`core_line_id`, NOT NULL, FK to `sales_order_lines` ON DELETE CASCADE, unique per
  `(company_id, core_line_id)`; revised at code review round 4, C2, from the round-3 key of
  `(company_id, sales_order_id, line_no, item_code)`). NONE of the key's four parts is
  durable. `bucket_key` is derived from the board's GRANULARITY as well as the line's date
  (`bucket_key_for`), so the same line is `2026-09-07` at week and `2026-09-09` at day, and
  a planner switching the view would have watched every saved line disappear. `line_no` is
  worse: `FulfilmentBoardService._line_numbers` falls back to the POSITIONAL index for the
  WHOLE order whenever any of its board rows lacks a mirror line, so (a) a re-upload that
  moves an earlier line's required date renumbers every line after it and the draft stopped
  attaching, and (b) on such an order the mirror numbers the same physical line differently
  again - and `_write_decision` deleted the promoted drafts by the MIRROR's `line_no`, so
  nothing matched and the draft survived its own confirmation to re-attach beside the frozen
  decision. `sales_order_id`, `line_no`, `item_code` and `bucket_key` are kept as stored
  lookup and display columns, re-stamped on every save: they are what the line was CALLED,
  never what it is.
- **The `proposed` snapshot is sent by the CLIENT on the PUT** (`{decision, proposed}`),
  rather than recomputed on the server. A proposal depends on which orders share the board
  (`compose_lines` draws the shared piles down once for the whole walk), on its granularity
  and on its `as_of`; a snapshot the server built for the one order would differ from the
  board in front of the planner, so every save on a multi-order board would come back stale
  the moment it was made. `stale` itself is still computed SERVER-side on every board read,
  comparing that snapshot with what `_allocate` has just proposed, on kind + quantity +
  location only (the reason sentence is prose the engine rewords).

Two smaller notes. The save takes the EDIT permission and NOT the per-project
`_assert_can_act_on` Confirm applies: that check refuses a planner who is not the project's
own salesperson, and AC-4.5 needs a second planner to be able to save over the first; a draft
claims no stock, and Confirm still applies the full check to what it posts. And `DELETE` on a
line nobody saved answers 404, which `deleteLineDraft` treats as "already gone" - "Undo all"
walks every key in the panel's map, and a `?batch=` board pre-marks lines locally that were
never PUT.

**S1 rewrite (code review round 3, 3 Sep, captain ruling): staleness is judged on the LINE's
own facts, never on the proposal.** The "Phase 2 as built" `proposed` snapshot above was
itself the bug: the proposal depends on which orders share the board, its granularity and its
window (`_allocate` draws the shared piles in board order), so comparing PROPOSED snapshots
flipped `stale` falsely the moment a planner opened a different view of the exact same
line - a save made on a multi-order week board came back "Suggestion changed" the instant it
was re-read on a single-order day board, with nothing about the line itself different. Fixed:
the PUT body carries no `proposed` any more (`{decision}` only); the server snapshots, at
save time, the LINE's own `open_qty` and `required_date` (resolved off the sales order the
key names, the same resolution S3 needs anyway) into a `line_snapshot` JSONB column
(`SOSupplyDecisionDraft.line_snapshot`, renamed from `proposed_snapshot` - hand-altered on
the dev DB with `ALTER TABLE projects.so_supply_decision_drafts RENAME COLUMN
proposed_snapshot TO line_snapshot;`, the table having been hand-created there too).
`is_stale` compares that snapshot against the row's CURRENT `qty` / `required_date` on every
board read (`_attach_drafts`). A contribution with no proposal at all is never stale on that
account, because this predicate never looks at one. Also fixed in the same round: S3 refuses
a save whose key names no real line under the caller's company (422, never a 500 with raw DB
text), and N2 adds an explicit company predicate to `_row_for`.

### S5 - upload speed and live progress

- Prod trace (2 Sep, the 2023-2024 completed book): `_closed_line` ran once per row with
  `NOT IN (<every settled id so far>)`; the list reached 13,519 ids, so each later row shipped
  a 13,519-parameter statement. Rows times settled ids is quadratic; Postgres dropped the
  connection. The fix below removes both the per-row query and the exclude list on the wire.
- `apply()`: preload every existing line for the file's documents in one query keyed by id
  (the diff already knows the ids), preload closed lines grouped by
  `(header_id, product_id)` once and match in Python (same predicate `_closed_line` uses),
  drop the per-row re-fetches. Commit per document batch (500 documents), publishing
  `processed_rows` at each commit; a crash mid-run keeps the documents already committed and
  the outcome rows say where it stopped.
- `ImportOutcome.flush` bumps the job's `processed_rows` on every buffer flush (every
  importer that uses it inherits the live card).
- No refusal, no redirect (markup round 3: "none of our file uploads distinguish
  outstanding or completed, both types are welcome, this applies to PO as well"). The
  Outstanding SO and PO uploads accept a completed book; delivered rows settle their lines
  through the same prefetch, and the 82,257-row completed book must complete in minutes.

### S6 - dropped

SPO duplicates: no slice (R-I). Issue #544 closed 2 Sep.

## Order

S1, S2 (one lane, engine), then S3 + S4 (board lane), S5 (import lane). S2 is the only slice that changes numbers on existing decisions; the probe's 38 of 79
SO381895 lines are the expected shape.

## What this supersedes

- Ladder v4 section 1d "dealer hot-selling excludes the pool" (R-A).
- Ladder v6 "one date, one quantity" walk (R-E); the board cell is still one unit.
- Ladder v7 R1 "pool LAST" (R-A). R34 pool borrow, R10/R33 whole-or-nothing for the
  remainder, and the five-pool net (v4 1d) all stand.
- Ladder v4's other-group free reading, and v7.1's date-bounded restatement of it (R-M): a
  bin's free pile at the asker's date is no longer, on its own, what another group may lend.
  It is now the LOWER of that pile and the lending group's whole open-book position. R40's
  two halves both stand - the walk still never DRAWS across a group, and the ladder still
  OFFERS - only the size of the offer changed.
