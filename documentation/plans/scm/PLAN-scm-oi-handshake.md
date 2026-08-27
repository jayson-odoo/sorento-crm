# PLAN - Order inquiry handshake: CS raises, purchasing acknowledges, links follow the acknowledgement

Status: **BUILT + REVIEWED** 2026-08-27 on `feat/scm-uat-oi-handshake` (stacked on part 3, #332), migration `428_order_inquiry_ack_state`. Review and tester fixes applied the same day (section 7 carries each one): the carried-line acknowledgement, the server-side refusals, Link now waiting for the book, the slug under `projects.*` with named grants. 26 pytest in `tests/test_order_inquiry_handshake.py`, 14 in `..._edges.py` (no xfail left), 8 in `test_order_inquiry_upload_jobs.py`; browser evidence below. Build before the Friday UAT walk. Lane `.claude/worktrees/scm-uat` (FE :3080, BE :8080), one PR stacked on part 3 (`feat/scm-uat-so-change`). UAC: `scm-oi-handshake-acceptance-criteria.md`. Friday stations 4 and 6 in `PLAN-scm-friday-uat-journey.md` change when this lands.

## 0. What the captain asked (27 Aug)

CS (Eling's team) approves on the fulfilment board and the rows flow to Order Inquiries. Before purchasing (Joey) has looked at a row, CS must be free to change it. Once Joey has acknowledged it, a change must be visible to her as a change. Links (PO / SPO) are purchasing's: nothing auto-links when a row is raised; links happen when Joey acknowledges, and she may batch-acknowledge. She may reject a row with a reason (the pattern used elsewhere). She uploads the PO and SPO books from the Order Inquiries page, stays there, links from there, and has a button to open the PO page to check.

## 1. Rulings (captain, 27 Aug)

| Question | Ruling |
| --- | --- |
| Reorder planning's project demand | reads ACKNOWLEDGED rows only (and rows changed after acknowledgement); awaiting rows are a count on the plan page, never demand |
| Amend after acknowledgement | row updated IN PLACE with the previous value carried (part 3's settle-in-place), links kept, `ack = changed`; Joey re-acknowledges or rejects from her own page. Planning changes (the batch) stays for SO BOOK changes only |
| Reject | row withdrawn from netting; the board cell shows "Rejected by <name>: <reason>", the line is undecided again, CS re-decides |
| Existing rows | no backfill: the feature is not live; every existing row starts `awaiting` |
| Who may acknowledge / reject | a permission under purchasing (Joey's role); CS cannot acknowledge its own rows |
| When | before Friday |

## 2. Model

Two columns on the row, never merged: `state` (supply: raised / placed / partly_linked / cancelled / withdrawn, exists) and `ack_state` (handshake, new).

`ack_state`: `awaiting` (default) -> `acknowledged` | `rejected` | `changed` (was acknowledged, CS amended; back to `acknowledged` on re-acknowledge).

Columns on `projects.order_inquiry_rows` (one migration, `down_revision` = lane head `427_sales_agents_class_backfill`, id <= 32 chars): `ack_state VARCHAR(16) NOT NULL DEFAULT 'awaiting'`, `acknowledged_by` (users.id, nullable), `acknowledged_at`, `rejected_by`, `rejected_at`, `rejected_reason TEXT`, `changed_at`. Previous value on a change: whatever part 3's settle-in-place already carries (reuse, do not add a second copy). The row's schema declares every one of them (`response_model` drops undeclared fields).

## 3. Behaviour

| Event | Actor | Effect |
| --- | --- | --- |
| Board Approve / Confirm | CS | rows raised `awaiting`; **no cascade**: `_auto_place_after_confirm` leaves `supply.confirm` |
| CS Order Inquiry FORM import | CS | the sheet's rows are raised `awaiting` like any other instruction and `rows_linked` is 0 by design - the form is CS telling purchasing what is needed, and nothing links until purchasing has read it |
| Amend before acknowledgement | CS | settle-in-place (part 3), stays `awaiting`, silent; supersede path raises the new rows `awaiting` |
| Acknowledge (one or many) | purchasing | `acknowledged` + who/when; the cascade runs for exactly those rows |
| Reject with reason | purchasing | reason required; `rejected` + who/when/reason; row leaves `committed_v` and the plan's demand; the line's decision is uncovered (`supply.confirm`'s `uncover_line_ids` seam) so the board shows it undecided with the reason |
| Amend after acknowledgement | CS | settle-in-place, previous value carried, links kept, `ack_state = changed`; a supersede of an acknowledged row raises its new rows `changed` too |
| Re-acknowledge a changed row | purchasing | `acknowledged`, cascade for the unlinked remainder |
| Upload PO / SPO book on the OI page | purchasing | the reorder page's `UploadDataMenu` / upload dialogs mounted on the OI toolbar (same components, same worker jobs); on completion the drawer offers **Link now** and **Open purchase orders** |
| Link now | purchasing | the cascade over acknowledged / changed unlinked rows of the products the upload touched |
| PO confirm cascade (exists) | system | acknowledged / changed rows only |
| Existing Auto-link on the OI page | purchasing | acknowledged / changed rows only |

Netting: `committed_v` and the S13b demand leg exclude `rejected`; the reorder plan's project demand counts `acknowledged` and `changed` only; the plan page shows "N awaiting acknowledgement" as a count chip (no sentence).

## 4. Screens

- **Order Inquiries (list + schedule):** an Acknowledgement filter (SearchableSelect, clearable: Awaiting / Acknowledged / Changed / Rejected); a column "Acknowledged" reading the name and time, "Awaiting", "Changed <date>" or "Rejected: <reason>" (truncate + title); row checkboxes with a bulk bar: **Acknowledge (N)**; per row **Reject** opening the reason dialog (reuse `scm/reorder/components/BulkRejectDialog.tsx`'s shape); a **Changed** row shows the same Was / Now table part 3 draws on the board. Upload button on the toolbar.
- **Fulfilment board:** a rejected line's cell is undecided and carries "Rejected by <name>: <reason>"; the decision strip counts it under nothing decided.
- **Reorder planning:** count chip "N awaiting acknowledgement" beside the existing header badges.
- Permission slug `projects.order_inquiries.acknowledge` gates Acknowledge, Reject, Link now, the upload button and the upload-job read; CS sees the column and the filter, not the actions. Granted two ways in migration 428 and both are needed: derived from every role holding `projects.order_inquiry.action`, and named outright for the roles `Purchasing` and `Purchasing Manager Role` - on the live copy the derived sweep reaches Admin alone, so on its own it would hide the feature from the person it was built for.

## 5. Order of work (one PR)

1. Migration + model + schema + `ack_state` on the worklist read (filter, facet count) - test first.
2. Acknowledge (batch) + reject endpoints, permission, cascade moved out of `supply.confirm` and into acknowledge / Link now / PO confirm - test first.
3. Netting and plan demand exclusions, awaiting count - test first.
4. Settle-in-place sets `changed`; supersede inherits it; board reject flag via `uncover_line_ids`.
5. FE: filter, column, bulk bar, reject dialog, Was / Now on changed rows, upload menu + Link now + Open purchase orders, board flag, plan chip.
6. Browser evidence on SO381895, then the Friday sheet's stations 4 and 6 rewritten.

## 6. Tests

pytest: acknowledge one / many, 403 for a CS user, cascade runs only at acknowledge (a board confirm leaves rows unlinked), reject requires a reason (422), rejected row absent from `committed_v` and the plan demand, board line undecided with the reason, amend before ack silent, amend after ack -> `changed` with the previous value and links kept, supersede inherits `changed`, PO confirm cascade skips awaiting rows, Link now scoped to the uploaded products, every new column on the wire. vitest: filter, column states, bulk bar count, reject dialog validation, upload menu mount and the two buttons, board flag, plan chip.


## 7. What shipped, and where it differs from the paragraphs above

- **`committed_v` and the PLAN read different rules, deliberately, and section 3 already
  said so.** The view drops a REJECTED row and keeps an awaiting one - the quantity is
  still owed to the customer, and the board, the dashboard and the demand drill all read
  the view. The narrower rule (acknowledged and changed only) lives in
  `demand.horizon_committed_select_sql`, which `reorder_run_service._planning_rows` now
  reads on EVERY run rather than only a horizoned one. One SELECT holds both rules; the
  alternative was a branch that could answer differently on two runs of one plan.
- **The awaiting count is LIVE, not frozen into `run_log`.** It rides `ReorderRunSummary`
  beside the frozen counts because that is what the plan page already reads, and it drops
  as the buyer acknowledges - a number still claiming six after they had cleared them
  would send them looking for two that do not exist.
- **A reject uncovers through a new method, not by relaxing a caller.**
  `ProjectSupplyService.uncover_lines` writes a revision carrying every line but the
  rejected one, and falls back to `supersede_for_material_change` when the active revision
  covered only that line (a revision covering nothing reads on the board as a decision).
  `confirm` now accepts a payload naming no line WHEN `uncover_line_ids` names one, which
  is the seam part 3 built and had no caller for on its own.
- **The new revision is attributed to whoever took the ORIGINAL decision**, never to the
  buyer who rejected a row: it is CS's own decision minus one line, and stamping
  purchasing on it would make every order-inquiry row of that order read as raised by the
  person who refused one of them.
- **The board reads the refusal off the LINE, not off the line's newest row.** A line
  routinely carries several rows (an order back beside the order, an amendment's own), so
  the last-writer-wins rule that picks the current instruction frequently would not pick
  the rejected one - and the cell would then go back to undecided saying nothing. Measured
  live on SO381895: the rejected ORDER BACK of 10 is the middle of three rows on its line.
- **Only two upload entries, and the second is called what its dialog is called.** The PO
  book is `OutstandingUploadDialog kind="purchase-orders"`; the PO and SPO book is the
  PURCHASE HISTORY channel (`po_history_service` is what files an `SPO-` document into
  `spo_allocations`, section K), whose dialog is titled "Upload purchase history" - so the
  menu says that and names the captain's own words for the file underneath. The sales-order
  book is deliberately absent: it is CS's document.
- **Link now and Open purchase orders are offered on the PAGE, not inside the upload
  activity drawer, and they wait for the WORKER.** The drawer is a shared component every
  upload in the system reports through, and a per-feature pair of buttons inside it would
  be a feature's opinion in a shared surface. The page shows them when the job this page
  queued reaches a terminal state - it follows the job through the drawer's own feed
  (`useUploadActivity`, one poll already running for every upload in the system) rather
  than starting a second watcher. They used to appear when the request was ACCEPTED, which
  invited the buyer to link against a book nobody had read yet.
- **Both buttons carry what the upload actually wrote**, read off the finished job:
  `GET /order-inquiries/upload-jobs/{job_id}`, gated on the acknowledge grant. Each channel
  states its own answer on its own result (`product_ids` beside the `scope_documents` the
  outstanding book already carried; `product_ids` / `documents` on the history book) and
  one reader lifts them off `result.upload` - nothing recomputes "what did that upload
  touch", because a second derivation would be free to disagree with the importer. Link now
  sends those product ids (it sent `{}`, so one book re-dealt every open instruction in the
  company); Open purchase orders sends those document numbers to the purchase-order list's
  new `documents` filter, which says how many it is showing and gives the rest back in one
  press. A book naming more documents than the endpoint lists opens the unfiltered list:
  fifty of two hundred shown as if they were all of them is worse than no filter.
- **The row checkbox refuses a CANCELLED or ACTIONED row** as well as an acknowledged or
  rejected one, AND SO DOES THE SERVER. Acknowledging an instruction nobody is doing takes
  on work that does not exist, and the cascade behind the press would link nothing for it -
  found in the browser, where the first press took on three cancelled rows. The review
  round made both halves true: `acknowledge_rows` refuses a row whose supply state is not
  open (a batch carrying one is refused whole), `reject_row` accepts only a row still owed,
  and the checkbox's predicate moved to the TABLE's own `enableRowSelection`, where
  `row.getCanSelect()` actually reads it - as a column-level option it was silently ignored
  and every row ticked.
- **A CARRIED line keeps its acknowledgement.** A confirmation naming one line carries the
  others, and a carried line's still-raised row is cancelled and re-raised under the new
  revision; the handshake for the new row was read AFTER that cancel, off every superseded
  row the line had ever carried, so untouched acknowledged rows read "Changed today" with
  no Was and no Now. It is read before the cancel now, off live rows only: carried inherits
  it verbatim, a line this revision names is promoted to `changed` from acknowledged or
  changed alone, and a refused line raises a fresh awaiting row.
- **The previous value is two COLUMNS, not a sentence to parse.** `previous_qty` /
  `previous_delivery_date`, written by the settle-in-place beside the note it already
  wrote. The screen parsed that note back into figures and read the comma in "Was 10, no
  previous delivery date" as part of the quantity.
- **A refusal hides once CS answers it** (captain, review round): the board cell drops the
  "Rejected by" flag when an active revision covering the line was confirmed after the
  rejection. A flag that outlived the answer reads as an open refusal on a line somebody
  had already dealt with.
- **No backfill, as ruled** - which on the dev copy means SO381895's existing rows read
  Awaiting while three of them are already Linked from the lane's earlier work. That pair
  is impossible for a row raised from here on and is worth saying out loud on the sheet.

## 8. Browser evidence (AC-H15), lane :3080 / :8080, 27 Aug

Navigated by sidebar from `/` (Supply Chain > Project Demand > Order Inquiries), viewport
1280x1200, session `scm-uat-handshake`.

- **AC-H1** SO381895's rows all read `Awaiting`. Unlinking the SRTWC8605-SC-RL 20 row
  (purchasing's own Unlink) returns it to `Raised` / `Awaiting` / `Not linked`, which is
  the shape a fresh raise now produces.
- **AC-H2** Ticking it and pressing `Acknowledge (1)` -> `POST /order-inquiries/acknowledge`
  200, the row reads `Acknowledged Jayson Personal 27/08/2026, 1:56 am` and Linked to fills
  in with `20 of 20 PO 202607-S0039 BRW 14, PO 202607-S0070 BRW 6` without a reload. A
  three-row press earlier read `Acknowledge (3)` and stamped all three.
- **AC-H5** Reject on the SRTWCX7405-RL-S-PJ ORDER BACK row: submitting with no reason is
  refused in the dialog ("A reason is required to reject"); with a reason the row reads
  `Rejected Jayson Personal: Factory closed until November`.
- **AC-H6** The order's active revision was superseded by the uncover (no active decision
  left, because revision 4 covered only that line), and the board cell for
  SRTWCX7405-RL-S-PJ now reads `Rejected by Jayson Personal: Factory closed until November`
  beside a fresh proposal.
- **AC-H8** A settle-in-place on the acknowledged row (driven through
  `ProjectSupplyService.confirm(..., settle_in_place_line_ids=)`, the way part 3's own
  evidence was) moved its date 10/08/2026 -> 20/08/2026: the row reads `Changed
  27/08/2026` with the Was / Now table (Qty 20 -> 20, Date 10/08/2026 -> 20/08/2026), keeps
  its links, and the Acknowledgement = Changed filter finds exactly it. Ticking it and
  pressing Acknowledge returns it to Acknowledged, so it leaves that filter.
- **AC-H4** The filter offers Awaiting / Acknowledged / Changed / Rejected with counts
  ("Changed (1)") and is clearable; `?ack=changed` travels in the URL.
- **AC-H12** The toolbar Upload offers "Upload purchase orders" and "Upload purchase
  history"; the second opens the same `Upload purchase history` dialog the reorder page
  mounts.
- **AC-H13 NOT walked live.** Link now and Open purchase orders appear once an upload this
  page queued is accepted, and no purchase-order book fixture small enough to import
  against the shared dev database was to hand. The buttons hang off the same `onQueued`
  seam the reorder and purchase-order pages use; the tester should walk it with a real
  book.

## 9. Browser evidence, review round (AC-H13 and B1), lane :3080 / :8080, 27 Aug

Session `scm-uat-handshake-fixes`, sidebar nav from `/`, viewport 1280x1200. The tester's
own fixture, `ZZTOI-po-book-ac-h13.xlsx`, re-cut with both quantities bumped (22 / 12) so
the book states a real change rather than a re-import of what is already held.

- **AC-H13, the wait.** Upload > Upload purchase orders > Test ("Rows: 2 - Would import: 2
  - Skipped: 0 - Errors: 0") > Confirm upload. The drawer shows
  `ZZTOI-po-book-ac-h13-r2.xlsx Processing just now`, and the page offers NOTHING: no Link
  now, no Open purchase orders, and no request to `/order-inquiries/upload-jobs/...` at all.
- **AC-H13, the landing.** The moment the job is terminal the alert reads **"The book has
  been read"** and the page asks the job what it wrote:
  `GET /api/v1/project-sales/order-inquiries/upload-jobs/<job> 200`.
- **AC-H13, Link now.** The press posts
  `{"product_ids":["6bbefc18-...","7a3f336f-..."]}` - exactly the two products the upload
  wrote (SRTWC8605-SC-RL, SRTWCX7405-RL-S-PJ), read off the job. It linked nothing, which
  is the truth on this database: every row of those two products is already fully linked,
  cancelled or rejected. The alert dismisses itself on the success.
- **AC-H13, Open purchase orders.** The button carried
  `/scm/purchase-orders?documents=ZZTOI-PO-0001`; the list requested
  `GET /api/v1/scm/purchase-orders?page=1&limit=25&outstanding=true&documents=ZZTOI-PO-0001`,
  showed ONE row, and said "Showing the 1 purchase order from one upload." next to **Show
  all**, which gives the other 13,000 back in one press.
- **B1, the carried line.** SO415898: two rows (line 1, 248; line 3, 512) ticked on the OI
  page and taken on with **Acknowledge (2)** at 3:57 am. Then the board (Fulfilment
  Planning > Plan SO415898 > List): one line approved, **Confirm 1 line** -> revision 2.
  Both lines' rows were re-raised at 4:03 am under revision 2, and both read
  **"Acknowledged Jayson Personal 27/08/2026, 3:57 am"** - the original stamp, no Changed
  badge, no Was / Now. Before the fix every one of them would have read "Changed
  27/08/2026" with no acknowledger. The order's third row (SRTSH22611, a genuine new
  raise) reads Awaiting beside them, which is what says the two states still differ.
- No console errors, no page errors, no horizontal overflow at 375px.

**The lane worker could not run that import.** It forked before `OrderInquiryRow` grew
`previous_qty`, so its work horse imports today's `order_inquiry_worklist_service` against
yesterday's model class and dies on import (`AttributeError: type object 'OrderInquiryRow'
has no attribute 'previous_qty'`, and RQ records it as a bare failure with no traceback on
the job). That is the "worker has no reload" rule reached through a MODEL rather than
through `app/tasks/*`, and it wants a worker restart on any machine that takes this branch.
The queued job was run in a one-off process with the same task function and the same
arguments, so everything downstream of it above is the real code path.

**What was done to the dev database** (the brief's ask): the migration was applied through
`Operations`/`MigrationContext` without touching `alembic_version` (the lane convention);
its grant sweep was re-run separately, because it was written after the columns had already
been applied. On SO381895: the SRTWC8605-SC-RL 20 row was unlinked and re-acknowledged (it
holds the same two links it did), its line's delivery date moved 10/08 -> 20/08 by the
settle above and the order gained revision 5; the SRTWCX7405-RL-S-PJ ORDER BACK of 10 is
rejected with "Factory closed until November" and revision 4 is superseded. Three cancelled
rows were acknowledged by mistake during the walk and were reset to `awaiting`.

**Review round, 27 Aug.** Migration 428's two new columns (`previous_qty`,
`previous_delivery_date`) were applied through `Operations`/`MigrationContext` without
touching `alembic_version`, and its grant sweep was re-run: the permission row was renamed
to `projects.order_inquiries.acknowledge`, the stale `project_sales.*` row and its one
grant were deleted, and the slug now sits with **Admin, Purchasing and Purchasing Manager
Role**. On the data: purchase order `ZZTOI-PO-0001` (the tester's fixture) was re-imported
at 22 / 12 rather than 20 / 10; SO415898's two SRTSA625A rows were acknowledged and the
order gained revision 2 from the board walk above (its rows re-raised, no links to move).

## 10. Captain's walk, 27 Aug (lane :3080): follow-ups, not built

- **Link horizon.** Auto-link at acknowledge, Link now after an upload, and the manual
  Link PO / Link SPO all take whatever open document can cover the row, whatever the row's
  delivery date. A far-future order (the captain: "a 2030 SO") then eats a PO's quantity
  that a nearer order needed. Wanted: before any link is made, a prompt for the latest SO
  delivery date to link up to (default the horizon the reorder plan uses); rows due after
  it are left Not linked and counted, never linked. One control, shared by the three paths.
- **Rejected rows on the board.** A reject bounces the line to CS, but only the Order
  Inquiries page (Acknowledgement = Rejected) shows it; the fulfilment board carries no
  badge or count. CS finds out by going to look.
- **UAT redo.** `scripts/uat_reset_so_planning.py --so <SO> [--rewind-book] [--apply]`
  puts one order back to never-planned on a dev copy (inquiries, links, claims,
  allocations, transfers, decisions, planning-change rows; `--rewind-book` restores the
  lines a batch moved from that batch's own `from_json`). Dry run by default.

## 11. Link horizon and the rejected bounce (captain, 27 Aug, "go" at 15:40)

Status: **built on `feat/scm-link-horizon`, reworked on `feat/scm-link-horizon-r2` after
review (B1, B2, S1 to S5), not browser-verified.** pytest and vitest green (the one
standing red on this dev copy, `test_every_new_field_reaches_the_list_the_row_and_the_export`,
predates this branch); a tester still owes the browser walk of AC-LH1 to AC-LH5 and
AC-RB1/AC-RB2.

**Link horizon.** Every path that links an order-inquiry row to a document (auto-link at
acknowledge, Link now after an upload, the manual Link PO / Link SPO dialog, the PO-confirm
cascade) takes a `link_up_to` date: rows whose delivery date is AFTER it are left Not linked
and are not counted toward the document. The Order Inquiries page carries the date beside
Acknowledge and Link selected (a date input, default = today + the reorder plan's horizon
days, remembered per browser); the Link dialog shows the same date at its top; a PO confirm
uses the plan's horizon. A row with no delivery date is inside the horizon.

- AC-LH1 GIVEN two acknowledged rows of one product, due 2026-10-01 and 2030-01-01, one open
  PO line of 100, `link_up_to = 2026-12-31` WHEN Acknowledge runs THEN the 2026 row links,
  the 2030 row stays Not linked, the PO line keeps its remainder.
- AC-LH2 Same rows WHEN Link selected runs with both ticked THEN the same result and the
  result banner says "1 linked, 1 after <date>".
- AC-LH3 The manual Link dialog on the 2030 row opens with the candidate list and a notice
  "Due after <date>"; a hand-take is still allowed.
- AC-LH4 A row with no delivery date links.
- AC-LH5 The date travels in the URL (`?link_up_to=`) and is what the page's buttons send.

**Rejected on the board.** A fulfilment-board cell whose line has a rejected order-inquiry
row shows a "Rejected" badge with the reason on hover, and the strip's decision cards count
rejected lines ("2 rejected") so CS sees the bounce without visiting Order Inquiries.

- AC-RB1 GIVEN a rejected row on line 24 THEN the SRTWCX7405-RL-S-PJ cell reads "Rejected"
  and the badge's title is "Rejected by <name>: <reason>".
- AC-RB2 The count clears once CS re-decides the line and a new row is raised.

### What was built, and where it differs from the paragraphs above

Rewritten 27 Aug after the review round (B1, B2, S1 to S5). Where a bullet says "the first
round", that is what shipped on `feat/scm-link-horizon` and what the fix changed.

- **The default is the reorder RUN's own horizon, not the policy's coverage date (S2).**
  The paragraph above says "default = today + the reorder plan's horizon days"; there is no
  horizon-days setting in the codebase and never was. The first round therefore read
  `scm.priority_policy.reorder_coverage_until`, which was WRONG in a way the tests could
  not see: that field is the ladder's BUY-NOW line - "a line required AFTER this date is
  proposed Buy now" (`app/models/scm.py`, `front_planning_engine`) - so the rows beyond it
  are exactly the ones the engine ordered bought, and using it as the link horizon meant
  the purchase order raised FOR those rows could never be linked BACK to them. The two
  dates say opposite things about the same rows. `scm.priority.plan_link_horizon` now reads
  the LATEST COMPLETED `scm.reorder_run.plan_horizon_date` ("Plan until", the date the run's
  own netting stopped at). `reorder_coverage_until` is untouched, doing its own job. NULL
  (no completed run, or a run that named no horizon) means no horizon is in force - a fresh
  install has never been asked how far out it plans, and a guessed date would refuse links
  nobody asked to have refused.
- **A purchase-order confirm links under the horizon of the run IT was drafted off (S2).**
  A draft may sit for days while a later run plans further out, and linking it under the
  newer horizon would hand the buy to rows the run that ordered it never counted.
  `bulk_confirm` reads its own lines' `source_ref` back to the run
  (`_plan_run_for_source_refs`: a location-grain line names its `scm.reorder_recommendation`
  id, a product-grain line names a member rec id or `"{order_summary_row id}:{warehouse
  id}"`, and both tables carry `run_id`), and falls back to the latest completed run for a
  purchase order nobody drafted from a plan.
- **A caller that names no date still gets the plan's - and a caller may now say "no
  horizon" out loud (S1).** The first round had two answers where there are three, so the
  buyer's empty date box travelled as silence and came back as the plan's own date: once a
  run named a horizon, the page could not link a far-future row at all. Requests carry
  `link_horizon: "date" | "plan" | "none"` beside `link_up_to`; OMITTED is inferred (the
  date when one is given, the plan when not), which is what keeps the CS form's own pass,
  the board confirm, the PO-confirm cascade and the MCP meaning exactly what they always
  did. `"date"` with no date is a 422 rather than a quiet reinterpretation. No magic string
  ever rides in a date field.
- **The count rides the response, so the banner has both halves.** `after_horizon`, the
  `link_up_to` it was measured against, and (S1) `link_horizon` - `"none"` when nothing was
  held back for a date at all - are on `AcknowledgeResult` and `AutoPlaceResult`;
  `link_up_to_default` is on the worklist summary, which is what the page's date input
  starts at. All of them are declared on the schemas: `response_model` drops what it has not
  been told about, and each has a test that asserts it over the wire.
- **The page's date is URL-first, and CLEARING it sticks (S1).** `?link_up_to=` beats this
  browser's memory, which beats the plan default, and the plan default is taken ONCE. The
  first round then lost the clear: emptying the box REMOVED the storage key, so the next
  visit read "never chosen" and the plan default seeded straight back over the choice.
  Storage now holds an explicit `none` marker, the page holds a `horizonCleared` flag beside
  the date, and the seeding effect refuses to run against it.
- **Auto-link presses under the same date, and shows it (B2).** The worklist's Auto-link
  dialog sent `{}` - the one press that reaches every open row in the company was the one
  press that ignored the date sat on its own toolbar, and nothing on the confirmation said
  so. It takes the page's horizon now, prints `Link up to <date>` (or `No horizon`) in the
  dialog body the way the manual Link dialog does, and sends it. One helper,
  `linkHorizonRequest`, builds the fragment for all four presses - Acknowledge, Link
  selected, Link now, Auto-link - so no two can mean different things by the same box.
- **The manual Link dialog was left as override.** It shows the date and flags a row due
  past it, and takes the hand-made link anyway (AC-LH3) - the same carve-out `manual`
  already makes for a purchase order that is not yet active.
- **The rejected bounce was HALF built already.** `_order_inquiries` on the board service
  has carried `ack_state` / `rejected_reason` / `rejected_by_name` per line since the
  handshake shipped, and it already clears them once CS decides the line again - which is
  AC-RB2's own rule. What was missing was the reading: the cell printed the whole sentence
  into a 150px column, so it was a truncated fragment of somebody's words. It is a
  **Rejected badge with the sentence in its title** now, and the strip carries "N rejected"
  beside the cards (`rejectedLineCount`, counted per LINE - a cell holds several).
- **`_groups_in_deficit` had a boundary that hid the ordinary case** (captain's item 4). A
  purchase order raised off the plan buys exactly what the plan said the group was short, so
  the group lands on `group_net + remaining == 0` - and "at or below zero is deficit" then
  refused that group its own buy: the rows that sized it stayed raised, the PO-confirm
  cascade offered them nothing and the Link dialog listed nothing. Ruled and built: a group
  is offered at zero, AND a group holding an acknowledged unlinked row of the product may
  reach its own purchase order, because that row is the demand the order was bought for.
- **That second exemption is per ROW, not per product (B1).** The first round subtracted it
  inside `_groups_in_deficit`, which lifted the whole PRODUCT out of the deficit set - and
  candidates are only RANKED by location, never filtered by it, so a row at any other group
  walked first simply helped itself to the exempt group's line while that group's own
  backlog stayed unpromised. `_candidates_for_row` now subtracts
  `_exempt_groups_for_row(row, product)`: the group is lifted only for a row that is itself
  acknowledged, still unlinked, and resolves to that group.
- **The listing flag follows both halves of the ruling (B1 follow-on).**
  `link_candidate_products` promises "the SAME group-deficit rule the walk does" and did not
  keep it: it asked for `net + remaining > 0` (so it hid the Link at the zero boundary the
  plan lands on every time) and knew nothing of the acknowledged-row exemption. It reads
  `>= 0` and honours the exemption now. It is answered per PRODUCT, which is all a
  listing-wide flag has to go on - it cannot tell the exempt group's own row from a
  neighbour's, so it errs towards offering and the dialog stays the exact answer.
- **The awaiting-row read is memoised per product (S3).** It costs up to three uncached
  queries and the cascade asks it once per row; `_rows_awaiting_a_link` answers per product
  and remembers on the instance, the same shape `_netting` already uses. The
  `_groups_in_deficit` docstring's claim that it "costs no query beyond the netting read" was
  false while the exemption lived there, and is true again now.
- **The ladder-v4 tests keep BOTH scenarios (S4).** The first round moved three asking rows
  from `BRW-IB` to the pool to keep them green, which hid the rule change. The pool variants
  stay (they are what keeps the deficit rule itself under test - core sales-order demand at
  a group nobody acknowledged an instruction for), and the original `BRW-IB` scenario is
  back beside each of them with the new expected outcome.
- **The handshake suites pin the default rather than reading the live one (S5).**
  `tests/test_order_inquiry_handshake.py`'s `world` fixture runs on the shared prod-copy,
  which carries real planning runs, so "the latest completed run" was whatever somebody last
  planned. The fixture seeds one completed run finishing now and naming NO horizon, and the
  two AC-LH5 tests write a date onto that same run.
