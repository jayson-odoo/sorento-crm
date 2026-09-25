# PLAN - Order inquiry links: AutoCount is the source of truth, the cascade only suggests

Status: IN PROGRESS 25 Sep 2026. /feature steps 1 to 3 (journey, grill, UAC/plan) done - every
grill question answered by the owner on PR #1220 (see "Rulings" below). S1 to S5 built and
merged to this branch (S1 the stale-state repair, S2 the FE mock later reconciled against R11
to R13, S3/S4 the suggested-link model, S5 the conversion script with its dry run RUN against
the 23 Sep prod copy, `--apply` never run, section 7). S6 (reviewer + browser evidence) is under way: review round 1
addressed (PR comments 5820446777, 5820494222), the hand-test rulings R11 to R18 folded in,
review round 2 (comment 5825004622, this session) addressed, review round 3 (comment
5826588258) addressed - every Blocking and Should-fix item fixed, tester-first where a test
was named; Blocking 2 (S6 browser evidence, AC-LT-50/51) captured 25 Sep 2026 on stack :3080 at
9319d07b3: `evidence/oi-links-autocount-truth/s3-*.png`, `s4-*.png`, `index.md` (the +N badge
and the Auto link all toast not shown; a Link selected observation on OI-2609-0003 is flagged
in the index for review). Track: full (new table, migration, a change
to what the Buy card, stock debt and `scm.committed_v` count). Branch `fix/oi-links-24sep`, one
lane, one PR with the S1 repair (issue #1215 points 1, 2, 5) folded in. UAC:
`oi-links-autocount-truth-24sep-acceptance-criteria.md`. Domain: SCM, order inquiries.
Classification: CORE (the projects module's existing tables; no new module, no new
permission: the Link selected route reuses the grant `auto-place` already requires).

## 0. The owner's words (24 Sep 2026, issue #1215), verbatim

Point 3, on the closed PO linked to OI-2609-0755:

> "oh okay i see, but again, we should use AutoCount as source of truth of linking."

Point 4, on the suggested links:

> "the idea is the suggested link shouldn't be counted as real link and actually appearing in
> the PO or SPO column."

The ask behind point 4, from the issue body:

> "Our suggestion of linking from BRW, PO or SPO needs to be more suggestive. Our source of
> truth should come from AutoCount for now. If we suggest to link from PO or SPO we need to
> indicate it as suggestive and not really linking."

Delivery: "let's go on a fix together in 1 PR." The suggested-link model gets this plan and its
UAC on the branch before its code.

## 1. Journey

Held in full in the UAC's `Journey` section (J1 to J7). In one paragraph: purchasing opens
Order Inquiries; the PO and SPO columns and the State pill show only what AutoCount ties to the
sales order line, what a person linked, or what CS reserved; a row the cascade found a document
for shows it in its own Suggested column and still reads To buy; the document opens the same
lightbox, whose Lines tab carries the Allocated and Suggested facts on the grid itself (R13
retired the lightbox's own separate "Suggested for" panel); the buyer makes it real in AutoCount
(the next push links it) or, for a pool PO AutoCount never ties to a sales order, by ticking
the row and pressing Link selected, which re-runs the AutoCount book step for exactly those
rows and refreshes their suggestions - it recalculates against AutoCount, it never writes a
suggestion as a real link itself (R18); Confirm stays "I have read this row"; Auto link all
follows AutoCount and refreshes the suggested links. At the end, On PO/SPO means bought, To buy
means not bought, and every other screen and figure agrees because none of them ever reads a
suggested link.

## 2. What exists today (measured)

Code at main `e2769233`; data from the Diagnosis comment on #1215 (23 Sep 19:00 prod dump,
restored locally as `sorento_ai_automation_0923`, read only). Nothing below was re-measured on
data in this planning session: the sandbox has no database, so every count the design needs
that the Diagnosis does not already hold is an S5 dry-run output, not a guess (section 7).

### 2.1 One table, three kinds of writer, no marker that tells them apart

* `projects.order_inquiry_links` (`OrderInquiryLink`, `app/models/project_so.py:1128`) has
  exactly one target per row (PO line, SPO allocation, or CS reserve request row, CHECK
  `ck_order_inquiry_links_one_target`), `qty > 0`, `auto` (boolean, "written by the cascade
  rather than by a person clicking", `:1197-1199`), `linked_by`, `linked_at`, `claim_id`. No
  source or trigger column.
* The one link writer is `_write_link` (`project_order_inquiry_service.py:7538`): writes the
  link, `auto = bool(auto_trigger)`, the audit claim in `scm.order_link_claim`, and appends
  "Linked to X ...; auto: <trigger>" to the ROW note.
* Writers that reach it:
  * the cascade walk in `auto_place_for_products` (`:8453`, the write at `:8720-8732`) with
    candidates from `_candidates_for_row` (`:6506`); triggers `raise` (board Confirm),
    `worklist` (Auto link all and Link selected, route `:1466`, `redeal_drafts=True`,
    `include_awaiting=True`), `link_now`, `acknowledge`, `po_confirm`, `decision_confirm`
    (full list of doors in 2.5);
  * the book, `follow_book_for_rows` (`:2503`) and `follow_book_repairing` (`:2180`), plus the
    OI sheet importer's `pair_needs`; `auto = true`;
  * a person: Choose document / Link PO (`LinkDocumentDialog`, `place-on-po`, `manual`),
    `auto = false`;
  * CS reserve commit (`reserve_request_row_id` target, `auto = false`) and the other
    `auto = false` writers listed in 2.5 (board borrow `place_supply_borrow` `:7604`,
    planning-change reallocation and shift, container planner ticks).
* **The book step runs INSIDE every cascade pass first** (`:8594-8610`), called with the
  cascade's own trigger. So the note's `auto: worklist` does not tell a cascade guess from a
  book link, and `auto = true` covers both. The only reliable test of "the book names this
  target for this row's own line" is `_book_names_target_for_line` (`:2765`), already used by
  the re-deal to protect book links (`:8668-8680`).
* A draft is `_cascade_only` (`:6223`): every link on the row is `auto`. It replaced
  `ack_state` as the draft marker (`PLAN-oi-confirm-per-so.md` S1).

### 2.2 Every link counts as bought, whoever wrote it

* Row state: `refresh_link_state` (`:5869`) sums every link plus `bundled_qty` and
  `_coverage_state` (`:5925`) writes `raised` / `partly_linked` / `placed` (To buy / Partly on
  PO/SPO / On PO/SPO, `OrderInquiryVerbPill.tsx:89-98`). It also writes `po_ref`,
  `po_line_id`, `spo_ref` from the first non-reserve link.
* `scm.committed_v` (latest body: migration `525_committed_v_orderback`, confirmed leg around
  `:247-300`) nets `SUM(order_inquiry_links.qty)` per row and keeps only rows in `raised` /
  `partly_linked`. A cascade link therefore removes the row's demand from the reorder plan,
  while `scm.on_order_v` (migration 420, no link read) still counts the same PO's open balance
  as supply.
* Stock debt: `StockDebtService._holds` (`scm/stock_debt_service.py:637`) pins every link's
  document to the line as a hold, before anybody queues.
* Worklist cards: `_incoming_qty` / `_purchased_qty` (`order_inquiry_worklist_service.py:1056`,
  `:1067`) read the row's linked quantity by kind; the Buy card is what is left.
* Capacity for other rows: `_candidates_for_row` nets every OTHER link on a line from its
  `remaining`, and `scm.order_link_claim` dedicates the line to that sales order.
* Display: the worklist's PO (`orderInquiryWorklistColumns.tsx:1011`) and SPO (`:1070`)
  columns, the Lines tab, the lightbox's Allocated to (`_allocations_on`,
  `order_inquiry_worklist_service.py:2494`), the SCM sales order detail, the board's inquiry
  cell, the handover email, the export.
* The full reader inventory is in section 2.4.

### 2.3 The numbers the Diagnosis already holds (23 Sep copy)

| Fact | Value |
| --- | --- |
| Rows `placed` | 2,094 (120 with zero links, 103 of those covered by a companion bundle) |
| Rows `partly_linked` | 143 |
| Links on CLOSED PO lines | 250, all `auto = true`; split between "cascade linked while open" and "book named a closed line" not measured (needs `_book_names_target_for_line` per link: S5 dry run) |
| OI-2609-0755 / AP4844 | cascade link (`auto: raise`) to PO-2026/09-0023, made 22 Sep 09:43:55 UTC while the line was open, 0 received, no `from_so_line_ref`; the PO closed afterwards |
| PO-2026/05-0022 | three open lines, none with a `from_so_line_ref`: a pool purchase AutoCount will never tie to a sales order line |
| SPO-2026/09-0080 | 37 lines, `from_so_line_ref` empty on all, `from_po_number` present |

What this says for the design: most open POs and SPOs carry no sales order reference, so under
"AutoCount is the source of truth" most rows the cascade covers today have NO real link to
fall back on. The share is the first number S5's dry run prints.

### 2.4 Reader inventory (code survey, 24 Sep)

Every reader below reads `order_inquiry_links` and none reads `auto` to decide coverage. After
this plan each of them reads real links only, with no edit: that is the point of section 3.2.

| Area | Readers (file:line) | What it computes from links |
| --- | --- | --- |
| Row state | `refresh_link_state` :5869, `_coverage_state` :5925, `derive_bundles` :5939 | the State pill, `po_ref` / `spo_ref` |
| Reorder demand | `COMMITTED_V_SQL` `scm/demand.py:488` (legs :545, :610), `horizon_committed_select_sql` :652, `horizon_project_need_dates_sql` :888, `run_scope_oi_rows` :986, `reorder_runs.get_candidate_orders` :504 | demand net of linked qty |
| Demand drill | `demand_breakdown_service.demand_for_recommendation` :226 (legs :610, :722) | drill rows, `linked_qty` |
| Loading plan | `container_request_service._SPO_PLACED_ON_LINE_SQL` :456 | need net of SPO links |
| Stock debt | `stock_debt_service._holds` :637 | holds pinning a document to a line |
| Worklist | `_linked_qty` :367, `_UNLINKED_QTY` :512, `_incoming_qty` :1056, `_purchased_qty` :1067, `_kinds` :2736, `_stage_rows` :2660, `matrix` :2943, `_quantity_flow_by_so_line` :1841, `_allocations_on` :2494, `_serialize` :2128, the `linked=` filter and link search :327-353 | the three cards, Taken / Remaining, lightbox Allocated to, filters |
| Link display | `links_for_rows` :4730 (feeds the worklist, OI detail, export, `sales_order_service._line_links` :732, the board `_order_inquiries` :1773) | the PO / SPO cells, SO detail, board cell |
| Capacity | `_linked_by_target` :6266 (used by `_candidates_for_row` :6506, `link_candidate_products`, the importer's `_claimed_capacity`), `order_link_service._linked_by_target` :613, `placed_by_claim` :662 | room left on a document line |
| Board supply | `project_supply_service._supply_document_links` :6161 | a document's balance on the board |
| Container planner | `spo_conversion_service._project_coverage` :1167, `_linked_qty` :2438, `_own_state` :2577 | ORDER_BACK coverage, tick caps |
| Planning change | `planning_change_service._placed_links` :1458, `_waiting_rows` :1553, `_document_links_by_row` :3027 | line qty on documents, receivers |
| PO / SPO pages | `purchase_order_service._allocated_by_po` :309, `_allocations_for` :454, `list` :674; `procurement_service.get_document` :2654; `order_inquiry_header_service.related_documents` :404 | allocated qty, "SOs covered" |
| Undo | `project_supply_undo_service._grouped_refusals` :653 | links made after a confirm block its undo |
| Reserve | `order_inquiry_reserve_service._remaining` :122 | reservable remainder |

Frontend: the worklist's `documentsOf` / `DocumentsCell` (`orderInquiryWorklistColumns.tsx:177`,
`:334`) and PO / SPO columns (`:1011`, `:1070`), `OrderInquiryBackingDocumentsDialog.tsx`, the
Lines tab's `firstLinkOf` / `DocumentCell` (`orderInquiryHeaderLinesColumns.tsx:60`, `:64`),
`OrderInquiryDocumentDialog.tsx` Allocated to (`:149`), `SoLineLinksBody.tsx`, the board's
`boardOrderInquiryWord` (`supplyVocabulary.ts:897`), `kindTotals` (`orderInquiryKinds.ts`).
**No screen reads `link.auto`.** The draft mark (`DraftMark`, `:109`) reads the ROW's
`ack_state`.

### 2.5 Three facts that shape the design

* **"Link selected" is the cascade, not a manual link.** On the worklist
  (`OrderInquiriesClient.tsx`, `linkSelected`) and the OI detail (`OrderInquiryDetail.tsx:700`)
  it posts `auto-place` with `row_ids`, trigger `worklist`, `auto = true`. The only manual
  link is "Choose document" / "Link PO" (`LinkDocumentDialog.tsx`, `POST
  .../order-inquiry-rows/{row_id}/place-on-po`, `full_set`, `auto = false`).
* **The cascade has seven doors:** `worklist` (Auto link all, Link selected, the detail gear's
  Auto link), `link_now`, `acknowledge`, `po_confirm` (`purchase_order_service.py:1265`,
  `:1283`), `raise` (board confirm, `project_supply_service.py:7077`), `decision_confirm`
  (planning-change apply, `:7116`), and the displaced-holder re-offer inside
  `follow_book_for_rows` (`:2724`).
* **Other `auto = false` writers that are not a person's pick:** the board borrow
  (`place_supply_borrow`), planning-change reallocations (`_redeal_document`,
  `planning_change_service.py:3403`, `_pool_row_for` `:3302`), the planning-change link shift
  (`_shift_links_off_retired_lines` `:4009`, copies the old link's `auto`), the container
  planner's ticks (`spo_conversion_service._link_ticked_demand` `:2334`), the importer's
  `_move_received_links` (`:2954`). Because they write `auto = false`, no script can tell them
  from a manual link after the fact.
* **Name clash.** `OrderInquiryLink.suggestion` already exists on the wire and in the FE type
  (`orderInquiry.types.ts:204`): the S1b `reallocate` / `unlink` advice on a REAL link. This
  plan's concept is therefore called a **suggested link** everywhere (table, field, copy),
  never "suggestion", so the two cannot be confused in code or on screen.

### 2.6 Side findings from the survey (not this plan's scope)

* `stock_debt_service._holds` does not exclude reserve links; a reserve link falls into the
  `po:None` branch.
* `horizon_project_need_dates_sql` has no `ack_state` filter, unlike its sibling legs;
  `demand_breakdown_service`'s confirmed leg reads `verb = 'ORDER'` only and ignores
  `bundled_qty`; `_quantity_flow_by_so_line` ignores `bundled_qty` and `ack_state`.
* `follow_book_for_rows` re-offers displaced awaiting rows without `include_awaiting`
  (`:2724`), so they are not re-linked.

Each goes to `documentation/backlogs/backlog.md` when the lane opens its PR, not into this
lane.

## 3. Design

### 3.1 The rule

**A link is real only when AutoCount, a person, or a person-applied board decision put it
there. The cascade only suggests.**

| Writer | Today | After |
| --- | --- | --- |
| Book: `follow_book_for_rows`, `follow_book_repairing`, sheet importer `pair_needs` | real link, `auto = true` | real link, unchanged (D1, D3, D4 of `PLAN-oi-follow-book-chain.md` stand; G10) |
| Cascade walk inside `auto_place_for_products`, after its book step, from every door in 2.5 (`worklist`, `link_now`, `acknowledge`, `po_confirm`, `raise`, `decision_confirm`, re-offer) | real link, `auto = true` | **suggested link**, not an `order_inquiry_links` row |
| Choose document / Link PO (`LinkDocumentDialog`, `place-on-po`) | real link, `auto = false` | real link, unchanged (G3) |
| Link selected (N) | the cascade, `auto = true` | re-runs the AutoCount book step for the ticked rows only, then refreshes their suggestions the same way Auto link all does - never writes a suggestion as a real link (R18, supersedes G1) |
| CS reserve commit | real link (reserve target) | unchanged |
| Board borrow, planning-change reallocation and link shift, container planner ticks, importer `_move_received_links` | real link, `auto = false` | unchanged in this lane (G8) |

### 3.2 Why a separate table, not a flag on the link

A `suggested` flag on `order_inquiry_links` would put a filter on every reader in section 2.4:
the view, the horizon legs, the drill, the loading plan, stock debt, the cards, the lightbox,
the SO detail, the board, the PO page, the container planner, the capacity walk, the claims,
undo. Missing one is the exact defect the owner reported. A separate table means every
existing reader is correct by construction and only the new display reads suggested links.
Fewer moving parts wins (PRINCIPLES "Simplest thing that works").

Computing suggested links on read instead (no storage) was rejected: the cascade deals scarce
lines across thousands of rows in priority order (`_rank_raised_rows`), so a per-page
computation would offer the same units to several rows, and a page load would cost a full
pass (30 s company-wide for Auto link all on the prod copy, `PLAN-oi-follow-book-chain.md`
section 8).

### 3.3 The store

`projects.order_inquiry_suggested_links` (`OrderInquirySuggestedLink`, `CompanyScopedMixin`):
`id`, `company_id`, `row_id` (FK row, CASCADE), `po_line_id` (FK, CASCADE) or
`spo_allocation_id` (FK, CASCADE), CHECK exactly one, `document`, `qty > 0`, `trigger`,
`suggested_at`. Indexes on `row_id`, `po_line_id`, `spo_allocation_id`. No `claim_id`, no
`linked_by`, no reserve target (a CS reserve is always a person's act). A deleted document
line takes its suggested link with it (CASCADE, unlike a real link, which keeps its display):
a suggestion of a line that no longer exists means nothing.

### 3.4 Who writes and removes a suggested link

* **Written only by the cascade walk.** `auto_place_for_products` keeps its book step first
  (real links), then walks exactly as today; where it called `place_on_po_allocations(...,
  auto_trigger=trigger)` it calls a new `_write_suggested_links(row, takes, trigger)`. The
  per-row answer REPLACES the row's suggested links; an identical answer writes nothing
  (`_same_placement`, S4 of the draft-links plan, reused).
* **Capacity** (G2): a line's room for suggested links is `qty_ordered - qty_received - real
  links - suggested links already held by other rows`, dealt in the existing priority order,
  so two rows are never told to use the same unit. A suggested link never reduces the room a
  REAL link sees (`_linked_by_target` is not touched).
* **Real links always win.** After `_write_link`, the suggested links on the same target are
  trimmed, lowest priority first (latest `delivery_date`, then newest `suggested_at`), until
  they fit what is left. One query, same transaction.
* **Removed** when the row is wholly covered by real links, and when the row goes
  `cancelled`, `actioned`, `rejected` or `redirected_to_pool` (one helper,
  `_drop_suggested_links(rows)`, called from `refresh_link_state` for covered rows and from
  the state writers).
* **The draft machinery shrinks.** `redeal_drafts` exists to move cascade links; once the
  links table holds no cascade guesses, "re-deal" is the replace in the first bullet.
  `_unplace_drafts` and `_cascade_only` stay for legacy links until S5 has run on prod
  (section 8).
* **G5 guard, dated 25 Sep 2026 (review round 2 Blocking 3, no owner ruling needed - this
  preserves G5 rather than changing it).** Until this guard, `auto_place_for_products`
  still re-dealt a row's own `_cascade_only` real link when `redeal_drafts=True` (Auto
  link all, Link selected): a link no better answer covers is, since S3, always a LEGACY
  link from before S3 (the cascade itself writes no real link any more), and deleting it
  to write a suggestion in its place is exactly the blind conversion G5 ruled out ("the
  owner sees the delta first") - it would have moved an unknown number of the ~2,000
  legacy rows from On PO/SPO to To buy on the next press, ahead of S5's own reviewed
  delta. Fix: the walk's `drafts` is now always empty - no existing real link, book-named
  or not, is ever re-dealt - and only the row's own unlinked remainder is offered a
  suggestion. `redeal_drafts`, `_unplace_drafts` and `_cascade_only` are unchanged in
  every other respect (the state-widening to `placed` rows, and `_retire_uncovered_rows`'s
  own use of `_unplace_drafts`) and still leave via section 8's removal once S5 has
  applied and a query shows zero legacy links left. Test:
  `tests/test_oi_follow_book_chain.py::TestRedealNeverTakesALegacyRealLink`.

### 3.5 How a suggested link is shown

* Worklist and OI detail Lines tab: a **Suggested** column after SPO (shared
  `orderInquirySuggestedColumn()`). Cell: the document number only (opens the lightbox),
  a plain `+N` badge when the row holds more than one - no kind badge, no location, no
  qty, no late marker, and no amber `suggested` word or pill (R11/R12, owner rulings 24
  Sep 2026, superseding this section's original mock: "don't need to show this, just make
  sure when i open the SPO document i can see the line being highlighted" / "the suggested
  column is good enough"). `-` when the row carries none.
* PO and SPO columns, State pill, Taken / Remaining, Supplier, the three cards: real links
  only. A row with only a suggested link reads To buy with blank PO and SPO. Supplier stays
  blank on it (22 Sep ruling "NO default supplier on unlinked rows").
* Lightbox (`OrderInquiryDocumentDialog.tsx`): "Allocated to" lists real links. R13 (owner
  rulings, 24 Sep 2026) retired the separate "Suggested for" panel this section originally
  specified - the Lines tab grid is the WHOLE answer now: opening a suggested document from
  the Suggested cell highlights the exact suggested line in the SAME lines grid
  (`suggestedLineId`, the same highlight idiom a real link's line already uses), both able
  to show at once. Review round 2 Should fix 5: the panel's own dead `suggested_links` wire
  field on the PO/SPO detail payloads is removed (AC-LT-34, amended).
* Row payload: `suggested_links: [{kind, document, po_id, po_line_id, spo_allocation_id,
  location, qty, expected_date, late_days, trigger}]`, separate from `links`. The existing
  `links[].suggestion` (S1b reallocate / unlink) is untouched and keeps its name.
* Not shown anywhere else: SCM sales order detail, fulfilment board, PO detail placements,
  handover email, reorder plan, stock debt. Excel export: G9.

### 3.6 Confirm, Link selected, Auto link all, manual links

* **Confirm (N)** (`acknowledge_rows`): stamps the rows, then runs the cascade for the
  unlinked remainder as today, which now writes suggested links. It never turns a suggested
  link into a real one (G7).
* **Link selected (N)** (R18, 25 Sep 2026, supersedes G1's sentence below): same menu item,
  same place on the worklist and the OI detail, but it never turns a suggestion into a real
  link any more. It is the SAME `auto-place` call "Auto link all" uses, `row_ids` naming
  exactly the ticked rows and nothing else - no separate route. Pressing it re-runs the
  AutoCount book step for the ticked rows only (`follow_book_for_rows`, writing only what
  AutoCount names, `auto = true`), then refreshes
  those rows' suggestions through the cascade the same way Auto link all does after its own
  book step. The result and toast state how many rows AutoCount linked (`book_linked_rows`),
  how many still hold a suggestion (`suggested_rows`), and how many of the ticked rows
  actually changed (`changed_rows`, new: book-linked this pass, or given a different
  suggestion than the one they held coming in - the figure that says whether recalculating
  against AutoCount caught a mistake). Enabled state reads the ticked rows only, whatever
  they hold; there is no whole-OI fallback for it the way Auto link has one. Grant:
  unchanged (the one `auto-place` already needs). Nit, review round 2 (25 Sep 2026): the
  book link this press writes still stamps `linked_by`/`actioned_by` with whoever pressed
  the button, exactly as every other door does (`_write_link`, unchanged) - no screen
  renders `linked_by_name` on a book-named link, so nobody reads it as the user's own
  choice either way, and there is nothing to fix in code, only in this sentence.
  ~~Superseded sentence (G1, no longer true): "For each ticked row it refreshes the row's
  suggested links (a cascade pass scoped to the row) and writes them as real links through
  `place_on_po_allocations` in the buyer's name (`auto = false`, `linked_by` the user, note
  "Linked as suggested by <name>"), then deletes them and refreshes the state. A row with
  nothing suggested is reported, not linked. Route: `POST /order-inquiries/link-suggested
  {row_ids}`" - this route is removed; `auto-place` with `row_ids` is now Link selected's
  own route, not a separate meaning for "any other caller".~~
* **Auto link all** (G4): unchanged route and date; runs the book step (real links) then the
  cascade (suggested links); the result gains `book_linked_rows` and `suggested_rows`, and the
  toast names both. The detail page gear's Auto link does the same for one header.
* **Choose document / Link PO**, **Unlink**, **Unlink all**, **Reject**: unchanged; they act
  on real links. Reject and Unlink all also drop the row's suggested links.

### 3.7 What "On PO/SPO" means afterwards

`placed` / `partly_linked` / `raised` keep their formula (`_coverage_state`) and their stored
values; only the input changes. On PO/SPO = AutoCount ties the row to a document, or a person
(or a person-applied board decision, or CS reserve) put it there, for the whole quantity
(bundle included). To buy = nobody has. The Buy card, `committed_v` and stock debt change
meaning the same way without a line of code in them: a row with only a suggested link is
demand nobody has bought for (G6).

### 3.8 The existing links on prod

A conversion script, not a migration, because the classification needs the ORM helper
`_book_names_target_for_line` and the owner decides after seeing the dry run (G5).
`scripts/convert_oi_cascade_links.py`, `--dry-run` default, per company, keyset pages, ORM
only. Every link on a row in `raised` / `partly_linked` / `placed` falls in one class:

| Class | Test | `--apply` does |
| --- | --- | --- |
| (a) book | `auto` and `_book_names_target_for_line(core line, target)` | nothing |
| (b) cascade, open target | `auto`, not book, target open with room | becomes a suggested link (same target, qty, trigger `converted`); link and its claim removed through `_remove_links` |
| (c) cascade, received or closed target | `auto`, not book, target closed, received or retired | removed through `_remove_links`, note "Link to <doc> removed: suggested by the cascade, not named by AutoCount (24 Sep ruling)" |
| (d) not auto | `auto = false`, no reserve target (manual, borrow, reallocation, shift, container tick, moved received) | nothing |
| (e) CS reserve | `reserve_request_row_id` set | nothing |

`actioned` and `cancelled` rows are never touched. Every touched row goes through
`refresh_link_state` once. The dry run prints the count per class, per state change
(`placed -> raised` and so on), and the To buy quantity delta, which is the number the owner
decides on. The 250 links on closed PO lines fall in (a) or (c); the dry run splits them.
Runs on the prod copy locally first (never the cloud), then on prod by the owner via `docker
cp` + `docker exec`, as `fold_oi_date_notices.py` did.

### 3.9 Migration and backfill

One migration: create `projects.order_inquiry_suggested_links` (revision id at most 32
characters, e.g. `oisl_0001_suggested_links`, re-parented onto main's head with
`./scripts/alembic-reparent.sh` before the PR). No change to `scm.committed_v`, no change to
`order_inquiry_links`. Backfill of existing rows = the S5 script (DoD item 2); the table starts
empty and the first Auto link all after deploy fills it for every uncovered row.

## 4. Slices

S1 is the coder's (issue #1215 points 1, 2 and 5: stale state repair script plus self-heal,
lightbox line identity and Allocated column, Lines tab PO via SPO) and is already under way on
this branch. The suggested-link model starts at S2 and waits for the grill.

| Slice | Phase | Holds | ACs |
| --- | --- | --- | --- |
| S2 | 1, FE mock | Suggested column (worklist + Lines tab), lightbox "Suggested for" panel (retired by R13 - see 3.5), Link selected wording and result, Auto link all toast, service contract comment | AC-LT-01 to 08 |
| S3 | 2, BE | migration, model, `_write_suggested_links`, capacity, trim on real link, drop on cover or state change, the cascade walk writes suggested links | AC-LT-10 to 22 |
| S4 | 2, BE + wire | `suggested_links` on the row payload, `link-suggested` route (retired by R18 - see 3.6), auto-place counts, readers pinned, mocks swapped | AC-LT-30 to 40 |
| S5 | 2, script | conversion script, dry run on the 23 Sep copy, counts pasted into section 7 | AC-LT-41 to 45 |
| S6 | 3 | browser evidence, reviewer + kill test; security-reviewer not expected (no auth, RBAC, ingest, upload or scoping change; the new route reuses the `auto-place` grant), said so in the PR | AC-LT-50, 51 |

### S2 evidence (24 Sep 2026)

Real-integration pass against a from-scratch stack in the coder's own sandbox (Postgres +
Redis, `scripts/bootstrap_env.py`, every module enabled, one Super Admin login) - never a
deep URL, sidebar clicks from `/`: Dashboards -> Procurement -> Supply Chain -> Order
Inquiries -> Lines -> List. The Suggested column renders right after SPO in the exact
column order (`PO`, `SPO`, `Suggested`, `Location`), `console`/`errors` clean at both
1280x900 and 375x812, no horizontal page scroll. The sandbox database carries zero order
inquiry rows (this lane adds no seed data), so the screen is verified in its empty state
only - screenshots: `evidence/oi-links-autocount-truth/s2-worklist-lines-suggested-column-
1280.png`, `...-375.png`.

The POPULATED cell (amber `suggested` word, kind badge, `late N d`, the `+N` pill, the
lightbox's "Suggested for" panel and its own empty state, and the Lines tab's shared column
def) is verified by direct component rendering instead - `suggested_links` is a Phase 1
mock field the real backend does not answer until S3/S4, so no live network call can
populate it. AC-LT-01, AC-LT-03, AC-LT-04 (populated and empty), AC-LT-07 and AC-LT-08 all
passed against `orderInquiryWorklistColumns.tsx` and `OrderInquiryDocumentDialog.tsx`
directly (React Testing Library, `@tanstack/react-table`, a stub `QueryClient`) in a
disposable, uncommitted harness, then discarded - Phase 2's tester writes the ACs' real,
committed test suite once S3/S4 give the field live data. AC-LT-05/06 (Link selected's new
count, its toast, and Auto link all's toast) are proven the same way `OrderInquiriesClient.
test.tsx` already proves the rest of the toolbar: fixture rows carrying `suggested_links`,
the service call mocked, the toast text read off `linkSuggestedOutcomeText`/`linkOutcomeText`
directly - both fall back to today's wording when the backend answers neither
`suggested_links` nor `book_linked_rows`/`suggested_rows`, so production is unaffected until
S3/S4 land.

### Testing seams (agree before Phase 2)

* Pytest on Postgres via `tests/_pg_fixture.py`; reuse `_seed_so_line`, `_po_line`,
  `_spo_line` from `tests/test_ingest_documents_v5_so_po_links.py` and the settle harness in
  `tests/test_order_inquiry_draft_links.py`.
* Service seam: `auto_place_for_products` and `follow_book_for_rows` directly. Route seams:
  `POST /order-inquiries/auto-place` (Link selected's own route too, since R18 -
  `link-suggested` never shipped as a separate route),
  `GET /order-inquiries`, `GET /order-inquiries/po/{id}`, `GET /order-inquiries/spo/{n}`,
  `POST /scm/purchase-orders/bulk-confirm`, the board confirm.
* Suites that assert "the cascade writes a link" today go red on purpose. Each is rewritten
  with the reversal recorded beside it (draft-links precedent, section 14), never deleted: at
  least `test_order_inquiry_draft_links.py`, `test_order_inquiry_handshake*.py`,
  `test_order_inquiry_links.py`, `test_order_inquiry_place_on_po.py`,
  `test_supply_inquiry_handoff.py`, `test_planning_change_apply_on_board.py`. The tester lists
  them with `grep -l "auto_place_for_products\|link_now\|auto-place\|bulk_confirm"` before
  writing reds.
* One agent on the backend test database at a time.

## 5. No-motion list

Nothing below changes, animates or moves:

* `order_inquiry_links` schema, `_write_link` (bar the trim call after it),
  `refresh_link_state`'s formula, `_coverage_state`, the stored state values and their labels.
* `scm.committed_v`, `scm.on_order_v`, the horizon legs, `demand_breakdown_service`, the
  loading plan, `StockDebtService`, the worklist card arithmetic, the container planner, the
  PO page, undo: they already read real links only.
* The book: `follow_book_for_rows`, `follow_book_repairing`, `pair_needs`, displacement (D3),
  the ingest hooks and their caps.
* Choose document / Link PO, Unlink, Unlink all, Reject, Confirm's stamp, the `received`,
  `used`, `reallocate` and `unlink` marks on real links, the draft mark (row `ack_state`).
* The Supplier column (real links only, 22 Sep ruling).
* The fulfilment board, the SCM sales order detail, the handover email.
* No new animation. The Suggested cell appears with the row; nothing fades, slides or pulses.
  The lightbox's new panel renders with the dialog.

## 6. What is deliberately not built

* No `suggested` flag on `order_inquiry_links` (section 3.2).
* No source or trigger column on `order_inquiry_links`: after S5, `auto = true` on a link
  means the book. Trigger to add one: a fourth automatic writer of real links.
* No per-row accept button on the grid: Link selected is bulk from Actions, like every other
  row action (R8, 28 Aug).
* No suggested link on the SCM sales order detail or the board. Trigger: CS asking to see what
  purchasing is likely to use.
* No notification of new suggested links.

## 7. Open measurements (S5 dry run answers them, not this plan)

* Links per class (a) to (e), company-wide and on the 250 closed-line links.
* Rows whose state would change, by transition, and the To buy quantity delta.
* The share of `auto` links the book names at all, which tells the owner how much of today's
  On PO/SPO is AutoCount and how much is the cascade.

**Dry run done, 25 Sep 2026** (script at `3abf41549`, run locally with no `--apply` against
the 23 Sep 19:00 prod copy `sorento_ai_automation_0923`, restored from the dump with no alembic
run: the dry run reads only `order_inquiry_links` and its targets, so the missing
`projects.order_inquiry_suggested_links` table was not needed and no throwaway clone was made;
the copy holds 6,772 links, 2,427 of them on rows in a link state, one company). Verified after
the run: link count unchanged, nothing written (AC-LT-45).

| Class | Count | Notes |
| --- | --- | --- |
| (a) book | 1,818 | 74.9 percent of the 2,427 links on linkable rows; the book names most of today's On PO/SPO |
| (b) cascade, open target | 157 | becomes a suggested link on `--apply` (e.g. OI-2609-0289 SRTWB7292 on SPO-2026/09-0044, OI-2609-0015 SRTPW0035-CR on 202607-S0081) |
| (c) cascade, closed/received/retired target | 440 | removed on `--apply` (e.g. OI-2609-0015 CB6633 on 202608-S0091, OI-2609-0023 C-FHSS14 on SPO-2026/09-0036) |
| (d) not auto | 10 | all on OI-2609-0010, 0011, 0013 (manual SPO links from the 20 Sep sheet import) |
| (e) CS reserve | 2 | OI-2609-0007 CKS819 and CSK14A, Reserved @ BRW |

| State transition | Rows | Notes |
| --- | --- | --- |
| placed -> raised | 319 | |
| placed -> partly_linked | 35 | |
| partly_linked -> raised | 0 | |

Rows whose state would change: 354. To buy quantity delta: 17,490 units (the sum of the (b) and
(c) link quantities the rows would stop counting as covered). The first 20 example rows per class
are in the PR #1220 dry-run comment of 25 Sep 2026.

Dry-run command (run locally against the restored 23 Sep prod copy, never the cloud):

```
venv/bin/python scripts/convert_oi_cascade_links.py
```

## 8. Follow-ups with their trigger

* Remove `redeal_drafts` / `_unplace_drafts` and re-read `_cascade_only`'s callers
  (`refresh_for_decision`, `_retire_uncovered_rows`), which today treat a book link as a draft
  too, once S5 has applied on prod and a query shows zero class (b) or (c) links left.
* A "Has suggested link" filter on the worklist: when purchasing asks to list only those rows.
* Section 2.6 side findings: to the backlog with the PR.

## Rulings

Owner rulings on the grill questions (24 Sep 2026, verbatim; PR #1220 comment
https://github.com/jayson-odoo/sorento-crm/pull/1220#issuecomment-5817947313):

**R1 (G1).** "okay, yeah correct we always refer to autocount now" - recommendation stands.

**R2 (G2).** "yeah" - recommendation stands.

**R3 (G3).** "yeah correct, always follow autocount" - recommendation stands.

**R4 (G4).** Not answered yet; the recommendation stands (Auto link all keeps its name, follows
AutoCount first, then refreshes suggestions) until the owner says otherwise.

**R5 (G5).** "okay" - recommendation stands.

**R6 (G6).** "wdym, a row is not considered bought if it already linked right?" - clarification
pending; the reading in force: a row with a REAL link counts as bought, a row with only a
suggestion does not, which is the owner's earlier ruling that a suggested link is not a real
link.

**R7 (G7).** "yeap" - recommendation stands.

**R8 (G8).** "ok" - recommendation stands.

**R9 (G9).** "ok" - recommendation stands.

**R10 (G10).** "yeah correct" - recommendation stands.

S2 onward builds to these rulings; G4 and G6 wording is being confirmed in chat before the
lane's review.

Owner rulings from the hand test on stack C (25 Sep 2026, verbatim; PR #1220):

**R15** (comment https://github.com/jayson-odoo/sorento-crm/pull/1220#issuecomment-5823949694,
SPO lightbox), **R16** (same comment, the jump-to-line button) and **R17** (same comment, the
via-SPO PO cell): recorded here as out of scope on 25 Sep 2026, but in fact landed on this
branch that same day (hand test round 1, PR comments 5824495599 and 5824637604) rather than in
a separate lane. Review round 2 (25 Sep 2026) found and fixed one gap each: R16's second Go to
press after paging away (Should fix 1), the Go to control's own primitive (Should fix 2), and
R17's via-SPO PO number resolved on the server instead of a client scan (Should fix 3).

**R18** (comment https://github.com/jayson-odoo/sorento-crm/pull/1220#issuecomment-5824001234,
supersedes G1's "Link selected" answer). On hand-test step 4 ("Tick rows with a Suggested
value, press Link selected. Suggested cell empties, PO/SPO cell fills, State goes On PO/SPO;
linked_by = your name"):

> "for this, what does it mean, link selected now converts suggested cell to PO/SPO cell? no,
> we shouldn't do that, the user should always go to autocount to do linking, the link selected
> is to recalculate with autocount linkage in case of mistake in the automation"

Reading in force, replacing G1's "Link selected" answer: Link selected (N) never writes a link
from a suggestion. It re-runs the AutoCount book step for the ticked rows only (the existing
`follow_book_for_rows` path, writing only what AutoCount names, `auto = true`, in AutoCount's
own name, never the user's), then refreshes those rows' suggestions through the cascade the
same way Auto link all does after its own book step. `POST /order-inquiries/link-suggested` is
removed; Link selected is the existing `auto-place` route scoped by `row_ids`, reusing the
`auto-place` grant - no new route. Section 3.6 carries the implementation detail.

Open question for the owner, not yet answered: does "the user should always go to autocount to
do linking" also retire the manual Choose document / Link PO by-hand actions (G3 said a manual
link by purchasing stays real, in the buyer's name)? Until answered, G3 stands unchanged and
only Link selected changes.

**G5 guard, 25 Sep 2026 (review round 2 Blocking 3).** No owner ruling needed - this preserves
G5 rather than reopening it. The reviewer found that `auto_place_for_products` was still
re-dealing a row's own real cascade link when called with `redeal_drafts=True` (Auto link all,
Link selected): since S3 the cascade writes no real link at all, so any such link is a LEGACY
one from before S3, and re-dealing it deletes the real link and writes only a suggestion in its
place - the blind conversion G5 already ruled out. Section 3.4 carries the fix and the test.

## Grill questions

Each with a recommended answer and why. The ACs marked `(G<n>)` follow the answer.

**G1. Where is a suggested link shown, and how does it become a real link?**
Recommended: its own Suggested column after SPO (worklist and Lines tab) with the amber word
`suggested`, and a "Suggested for" panel in the lightbox. It becomes real in two ways: (1) the
buyer ties the PO line to the sales order in AutoCount and the next push links it (the primary
path, the only one that makes AutoCount agree); ~~(2) the buyer ticks the row and presses Link
selected, which writes the suggested links as real links in the buyer's name.~~ **Superseded by
R18 (25 Sep 2026):** Link selected never writes a suggestion as a real link - see the Rulings
section and plan section 3.6. Pool purchases such as PO-2026/05-0022 and SPO-2026/09-0080 that
AutoCount will never name for a row stay suggested until AutoCount does name them, or until the
open question on manual Choose document / Link PO under R18 is answered. Why the column and the
first path still stand: pool purchases carry no sales order reference, so the buyer still needs
to see the suggestion and Link selected is still the button that recalculates it against
AutoCount - it just no longer promises the recalculation itself is a link.

**G2. Does a suggested link hold capacity against other rows?**
Recommended: against other suggested links yes, dealt in the existing priority order, so two
rows are never told to use the same unit; against real links never, and a real link trims the
suggested links on its line. No `scm.order_link_claim` is written for one. Why: without the
first half the column would offer one PO's 10 units to 30 rows; without the second, a guess
would block AutoCount's own answer.

**G3. Does a link purchasing makes by hand (Choose document / Link PO, or Link selected under
G1) count as real?**
Recommended: yes (`auto = false`, the buyer's name on it), and AutoCount still replaces it
when the book names the document for another sales order (D3, 19 Sep). Why: it is a person's
decision, which the owner's ruling contrasts with a suggestion; and it is the only way to link
a pool PO that AutoCount never ties to a sales order.

**G4. What does Auto link all become?**
Recommended: same menu item, same cut off date, two effects: follow AutoCount for every open
row in scope (real links), then refresh the suggested links for the rest; the toast reads "N
linked from AutoCount, M suggested, K after the cut off". Keep the label, or rename it "Follow
AutoCount and suggest" if the owner wants the label to stop promising links it now only
suggests. Why: the press still links (the book), and one press for both keeps the Actions menu
as it is.

**G5. What happens to the existing cascade links on prod, including the 250 on closed PO
lines?**
Recommended: the S5 script, dry run first on the prod copy, then the owner applies it:
book-named links stay; cascade links on open documents become suggested links; cascade links
on received or closed documents are removed with a note; every `auto = false` link and every
CS reserve is untouched; actioned and cancelled rows are never touched. The 250 split between
book (stays) and cascade (removed) in the dry run's output. Why: leaving them keeps the screen
saying On PO/SPO for guesses the owner ruled are not links; deleting them blind would move an
unknown number of rows to To buy at once, so the owner sees the delta first.

**G6. Do stock debt, the Buy card and the reorder plan change meaning?**
Recommended: yes, on purpose: all three count a row as bought only when it has a real link.
The Buy card grows by the rows the conversion moves to To buy; `committed_v` counts their
quantity as demand again, so the reorder plan may recommend buying for them, netted against
the same open POs through `scm.on_order_v` (today a cascade link removes the demand while the
PO's open balance still counts as supply, so the plan reads that PO twice). No code changes in
those readers. Why: it is what "shouldn't be counted as real link" says, and it ends the double
reading. The dry run's To buy delta is shown before apply.

**G7. Does Confirm turn the suggested links on the rows it confirms into real links?**
Recommended: no. Confirm stays "purchasing has read this instruction"; linking is Link
selected or AutoCount. Why: a tick meant as "seen" silently turning guesses into links is the
thing the owner asked to stop.

**G8. The other automatic writers that store `auto = false` today (board borrow, planning
change reallocation and link shift, container planner ticks, the importer's received-link
move): real or suggested?**
Recommended: real, unchanged in this lane. Each is written when a person applies a decision
(board Confirm, planning change Apply, container planner ticks, a sheet upload), and the board
and the container planner depend on them as placements. Why: they are decisions carried out,
not guesses; and since they already store `auto = false`, moving them would need a new source
marker first. Trigger to revisit: the owner calling one of them a guess.

**G9. Do suggested links appear in the Excel export and the handover email?**
Recommended: export yes, in its own "Suggested" column (purchasing works the sheet offline);
handover email no (it tells CS what is bought). Why: the export mirrors the grid; the email is
a promise to CS.

**G10. A book link to a CLOSED line (ruling 18 Sep) stays real?**
Recommended: yes. AutoCount named it; the `received` mark already tells purchasing the goods
have landed, and the replan at settle redirects it (`PLAN-oi-replan-received-links.md`). Why:
"AutoCount is the source of truth" is the same ruling from the other side.
