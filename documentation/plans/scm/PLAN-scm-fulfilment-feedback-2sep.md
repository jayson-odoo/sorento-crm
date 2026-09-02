# PLAN: Fulfilment planning feedback batch, 2 Sep (BRW first, per-line walk, saved decisions, upload speed)

Status: IN PROGRESS - S1, S2 (#553 draft, review round 1), S5 (#546 ready, to be folded into #553); one final PR carries S1 to S5 (captain, 2 Sep) ("yessir, correct ... let's go"). S1 DONE; S2 Phase 1 + Phase 2 DONE (ladder v8 live on the lane, PR open, Phase 3 review outstanding); S3, S3b, S4, S5 outstanding.
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

- R-L. **Other site pools still supply the remainder (ruled 2 Sep, "B, the current
  behaviour").** Step 0 asks the asking bin's own site pool. When own locations and both
  borrows cannot cover the remainder whole, the OTHER site pools are asked, in the v7.1 draw
  order (by on hand), each under the same allowance rule (its own Available minus the kept
  share, all bounded by the one five-pool net), whole or nothing. A DC1-IB line of 300 with
  DC1's pool empty, own group 110, and BRW sparing 400 reads "BRW 300", not "Buy 300".
  The share ledger is keyed by (product, pool); the net ledger stays one pile.

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

### S4 - saved decisions (server draft + response)

- `so_supply_decisions.state` gains `draft`. Save decision = `PUT
  /fulfilment-planning/lines/{contribution_key}/draft` (upsert, one row per contribution
  key, `saved_by`, `saved_at`); Undo = DELETE. Confirm promotes `draft` to `active` for the
  keys it confirms (same write as today, reading the draft when the body carries no
  composition). Board GET returns drafts in `contributions[].draft` and the panel seeds
  `draft` state from them on load.
- Feedback: pill goes `Suggested` to `Saved` on the row (plain "Saved", markup 2 Sep; the
  saver's name lives in the popover), the button shows a 600 ms check state, a sonner toast
  "Line 3 saved · 4 to confirm", the header counter updates as today.
  Leaving with unsaved edits in an OPEN panel keeps the existing `UnsavedDecisionPrompt`.
- Drafts are shared, not per user (one planning team; a second planner sees the same saved
  lines and the pill names who saved).

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
