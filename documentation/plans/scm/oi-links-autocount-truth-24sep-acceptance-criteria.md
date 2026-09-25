# UAC - Order inquiry links: AutoCount is the source of truth, the cascade only suggests

Plan: `PLAN-oi-links-autocount-truth-24sep.md`. Issue #1215, points 3 and 4. Status: IN
PROGRESS 26 Sep 2026 - every grill question answered by the owner (plan section "Rulings"),
S1 to S5 built and merged, S6 (review + browser evidence) under way, review round 2 addressed.
An AC tagged `(Gn)` holds under the recommended answer to that grill question unless a later
ruling (`Rn`) supersedes it, noted inline where one does; every other AC holds as written.

Owner rulings, 24 Sep 2026, verbatim:

> "we should use AutoCount as source of truth of linking"

> "the idea is the suggested link shouldn't be counted as real link and actually appearing in
> the PO or SPO column."

Term: a **suggested link** is the cascade's proposal of a document line for a row. It is not
an `order_inquiry_links` row. It is unrelated to `links[].suggestion`, the existing
`reallocate` / `unlink` advice on a real link (`PLAN-oi-replan-received-links.md` S1b), which
keeps its name and behaviour.

## Journey

**Actor:** purchasing (the buyer working Supply Chain, Order Inquiries). CS and the board act
before them; nobody acts after them on this screen.

**Where they arrive from:** CS confirmed a sales order on the fulfilment board. Its buy lines
landed as order inquiry rows. Some of those sales order lines were already bought in AutoCount
(a PO or SPO line whose `from_so_line_ref` names the sales order line); most were not.
Purchasing opens Order Inquiries from the sidebar.

**What the system already knows, so it never asks:** which documents AutoCount ties to each
sales order line (the book); which open PO and SPO lines of the same item have room, ranked by
location tier, date and priority (the cascade); which links a person made; which rows CS
reserved from stock.

**Steps, and the single decision each:**

1. **J1 - Read the row.** The PO and SPO columns show only REAL links: a document AutoCount
   names for this sales order line, a link a person made, a board or planning decision a
   person applied, or a CS reserve. The State pill (To buy / Partly on PO/SPO / On PO/SPO) is
   read from those alone. Decision: none.
2. **J2 - See the suggested link.** A row AutoCount has not tied to a document, where the
   cascade found an open document with room, shows it in its own **Suggested** column - the
   document number only, a plain `+N` when there is more than one (R11/R12, owner rulings 24
   Sep 2026, superseding this step's original mock: no location, qty, late marker or amber
   word) - never in PO or SPO. The row still reads To buy. Decision: none yet.
3. **J3 - Look closer.** The suggested document number opens the same lightbox as a real one,
   which highlights the exact suggested line in the SAME lines grid "Allocated to" already
   lists real allocations on (R13, owner ruling 24 Sep 2026, superseding this step's own
   separate "Suggested for" panel - the lines grid is the whole answer now). Decision: none.
4. **J4 - Act on it.** One decision: is this the document? Yes: tie the PO line to the sales
   order in AutoCount; the next push makes it a real link and the suggested link goes - the
   only way a suggestion becomes a link (R18, 25 Sep 2026, supersedes the G1 reading below).
   Pool purchases AutoCount will never name for a sales order stay suggested; the buyer ticks
   the rows and presses **Link selected (N)** to recalculate against AutoCount (catching a
   mistake in the automation), but pressing it never promises a placement on its own. No: buy
   something else; the suggested link stays until a pass finds a better one or the row is
   covered.
   ~~Superseded (G1): "Yes, in the CRM (for a pool PO that AutoCount will never name for a
   sales order): tick the rows, Actions, Link selected (N), which writes the suggested links
   as real links in the buyer's name."~~
5. **J5 - Confirm.** Start, Confirm selected (N) stamps the rows as read, exactly as today. It
   does not turn a suggested link into a real one (G7). Decision: none beyond the tick.
6. **J6 - Auto link all.** Follows AutoCount for every open row in scope (real links), then
   refreshes the suggested links for the rows still uncovered. The result names both counts.
   Decision: the Purchase order cut off date, as today (G4).
7. **J7 - Choose a document by hand.** Choose document / Link PO opens today's dialog; what
   the buyer links is real and carries their name (G3). AutoCount still wins over it later
   (D3, 19 Sep).

**What they hold at the end:** every document in the PO and SPO columns is one AutoCount or a
person put there. To buy means nobody has bought for the row yet, whatever the cascade
suggests. On PO/SPO means it is on a document for real.

**What every other stakeholder is told automatically:** the Buy card, the reorder plan's
committed demand (`scm.committed_v`), stock debt, the loading plan, the container planner, the
fulfilment board, the PO page and the SCM sales order detail read real links only, so they
count a row with only a suggested link as not bought (G6). No one is emailed about a
suggested link. The handover email lists real links only.

**Decisions removed:** "is this cascade guess really bought" is no longer a question the
screen leaves open: a guess never reads as bought.

## Group S2 - Phase 1, frontend against mocks

* **AC-LT-01 [FE] (J2)** Given a mocked worklist row with no links and one suggested link
  (`PO-2026/09-0023`, BRW, 2), when the worklist renders, then the PO and SPO cells read `-`,
  the State pill reads To buy, and the Suggested cell reads the document number alone
  (R11/R12, owner rulings 24 Sep 2026, superseding this AC's original mock: no location, qty
  or amber word).
* **AC-LT-02 [FE] (J1, J2)** Given a row with one real SPO link and a suggested link for its
  unlinked remainder, when it renders, then the SPO cell shows the real link only and the
  Suggested cell shows the suggested link only; no document appears in both cells.
* **AC-LT-03 [FE] (J2)** Given a row with no suggested link, when it renders, then the
  Suggested cell reads `-`.
* **AC-LT-04 [FE] (J3)** Given the Suggested cell, when the document number is clicked, then
  `OrderInquiryDocumentDialog` opens for that PO or SPO and highlights the exact suggested
  line in the SAME lines grid "Allocated to" lists real allocations on (R13, owner ruling 24
  Sep 2026, superseding this AC's original separate "Suggested for" panel).
* **AC-LT-05 [FE] (J4) (R18, supersedes the G1 reading below)** Given ticked rows, when
  Actions opens, then Link selected (N) counts every ticked row, whatever it holds, and is
  disabled at 0; pressing it posts `auto-place` with those rows' ids; after it runs, the
  toast names the rows linked from AutoCount, the rows still holding a suggestion, and the
  rows that changed. ~~Superseded (G1): "counts the ticked rows holding a suggested link
  ... the toast names the rows linked and the rows that had nothing suggested."~~
* **AC-LT-06 [FE] (J6) (G4)** Given Auto link all completes, when the toast shows, then it
  names the rows linked from AutoCount, the rows given a suggested link and the rows changed
  as figures, plus the after-cut-off count as today.
* **AC-LT-07 [FE] (J1, J2)** Given the OI detail page Lines tab, when a row with a suggested
  link renders, then its PO and SPO cells follow the worklist's rule (real only) and a
  Suggested column carries the suggested link, reusing the worklist's cell.
* **AC-LT-08 [FE] (J2)** Given the worklist at 375px and at 1280px, when a row carries a real
  link with a `received` mark and a suggested link, then the Suggested column truncates with a
  `title` and the page has no horizontal page scroll.

## Group S3 - the store, and the cascade writes suggested links (backend)

Every AC is seeded on `tests/_pg_fixture.py` with its own company, product, sales order line,
PO line, SPO line and inquiry row. `[BE][T]` unless marked.

* **AC-LT-10 (J2)** Given a raised row with need 2 and an open PO line of that item with 10
  free and an empty `from_so_line_ref`, when the board Confirm cascade runs (`trigger raise`),
  then NO `order_inquiry_links` row is written, one suggested link of 2 on that PO line is
  written, the row's `state` stays `raised`, and `po_ref` / `spo_ref` stay null.
* **AC-LT-11 (J2)** The same as AC-LT-10 for every other cascade door: `worklist` (Auto link
  all), `link_now`, `acknowledge`, `po_confirm` (`POST /scm/purchase-orders/bulk-confirm`),
  `decision_confirm` (planning-change apply), and the displaced-holder re-offer inside
  `follow_book_for_rows`.
* **AC-LT-12 (J1)** Given a raised row whose sales order line an open PO line names in
  `from_so_line_ref`, when any cascade door runs, then the book step writes a REAL link
  (`auto = true`), the row reads `placed`, and no suggested link is written for the linked
  quantity.
* **AC-LT-13 (J1) (G10)** Given the same book-named line, when the AutoCount ingest hooks run
  (`follow_book_for_rows`, `follow_book_repairing`), then the link is real whether the line
  is open, closed or received.
* **AC-LT-14 (J2) (G2)** Given two raised rows of the same item (priority A before B), need 6
  each, and one open PO line with 8 free, when one cascade pass runs, then A is suggested 6
  and B is suggested 2 on that line; the suggested links on a line never exceed `qty_ordered -
  qty_received - real links`.
* **AC-LT-15 (J4) (G2)** Given a PO line with 8 free carrying suggested links of 6 (row A,
  earlier) and 2 (row B, later), when a real link of 5 lands on it for row C (book or
  manual), then in the same transaction the suggested links are trimmed lowest priority first
  until they fit the 3 left: B's goes, A keeps 3. A real link is never refused because of a
  suggested link.
* **AC-LT-16 (J2)** Given a row holding suggested links, when a cascade pass runs over it
  again and the best answer is unchanged, then the rows are not rewritten (same ids, same
  `suggested_at`); when the answer changed, the old ones are replaced.
* **AC-LT-17 (J1)** Given a row that becomes wholly covered by real links (book, manual or
  reserve), when the covering write commits, then the row's suggested links are deleted.
* **AC-LT-18 (J1)** Given a row that is cancelled, actioned, rejected or redirected to pool,
  when that state is written, then its suggested links are deleted.
* **AC-LT-19 (J2)** Given a suggested link on a PO or SPO line that is closed, received or
  retired since, when the next cascade pass runs over the row, then it is gone and, if
  another line has room, replaced by that line.
* **AC-LT-20 (G2)** A suggested link writes no `scm.order_link_claim` row, and deleting one
  frees none.
* **AC-LT-21** Given a row with only suggested links, when `refresh_link_state` runs, then
  its state is `raised`.
* **AC-LT-22** The store is company scoped (`CompanyScopedMixin`); a scoped user of company B
  never reads company A's suggested links through any route.

## Group S4 - readers, Link selected, and the pages wired to the real API

* **AC-LT-30 [BE][T] (G6)** Given a row with need 4 holding a suggested link of 4 and no real
  link, when `scm.committed_v` is read, then the row's 4 count as committed demand, exactly as
  for a row with nothing suggested. No view change: the test pins it.
* **AC-LT-31 [BE][T] (G6)** Given the same row, when stock debt is read, then no hold pins the
  suggested document to that line.
* **AC-LT-32 [BE][T] (G6)** Given the same row, when the worklist summary is read, then the
  row counts in the Buy card and in neither Purchased nor Incoming.
* **AC-LT-33 [BE][T] (J2)** Given a row with a suggested link, when `GET /order-inquiries` and
  the OI detail rows are read, then each row carries `suggested_links: [{kind, document,
  po_id, po_line_id, spo_allocation_id, location, qty, expected_date, late_days, trigger}]` on
  the wire (response_model asserted), and `links` carries nothing suggested.
* **AC-LT-34 [BE][T] (J3)** Given a PO or SPO with real links and suggested links, when its
  lightbox endpoint is read, then `allocations` lists real links only and the response carries
  no `suggested_links` field at all (amended, review round 2 Should fix 5, 26 Sep 2026: R13
  retired the lightbox's own separate "Suggested for" panel this AC originally specified - the
  Lines tab's Allocated/Suggested columns, AC-LT-33's own wire field, are the whole answer now,
  so the field was dropped from the schema rather than left dead on the wire).
* **AC-LT-35 [BE][T] (J4) (R18, supersedes the G1 reading below)** `POST
  /order-inquiries/link-suggested` no longer exists (404). Given a ticked row whose only
  candidate is a pool PO with no `from_so_line_ref`, when `POST /order-inquiries/auto-place`
  runs scoped to it (`row_ids`) as a purchasing user - Link selected's own call - then its
  suggestion is recalculated but never written as a real link; a book-named target still
  links for real, `auto = true`, in AutoCount's own name.
  ~~Superseded (G1): "the first row's suggested link becomes a real link through
  `place_on_po_allocations` with `auto = false`, `linked_by` the user, the claim written,
  the row note 'Linked as suggested by <name>', the suggested link deleted and the state
  refreshed."~~
* **AC-LT-36 [BE][T] (J4) (R18)** A user without the grant `auto-place` already requires
  gets 403 from `auto-place` called with `row_ids` - Link selected reuses that same grant,
  no new permission.
* **AC-LT-37 [BE][T] (J6) (G4, R18)** `POST /order-inquiries/auto-place` returns
  `book_linked_rows`, `suggested_rows` and `changed_rows` beside `after_horizon` -
  `changed_rows` counts rows this pass actually moved (book-linked this pass, or given a
  different suggestion than the one they held coming in), 0 on an identical second pass.
* **AC-LT-38 [BE][T] (J1)** The SCM sales order detail line links, the fulfilment board
  contribution's `order_inquiry.documents`, the PO page placements and the handover email
  context read real links only; a suggested link appears in none of them.
* **AC-LT-39 [BE][T] (G9)** The OI Excel export carries a Suggested column beside PO and SPO;
  PO and SPO carry real links only.
* **AC-LT-40 [FE][T]** Every S2 mock is swapped for the real `api-client` call; no `PHASE2:`
  fallback is left, and the service file's contract comment matches the wire.

## Group S5 - existing links on prod (conversion script)

* **AC-LT-41 [BE][T] (G5)** Given, on a seeded set, (a) an `auto` link on a target the book
  names for the row's own core line, (b) an `auto` link on an open target the book does not
  name, (c) an `auto` link on a received or closed target the book does not name, (d) an
  `auto = false` link, (e) a CS reserve link, when `scripts/convert_oi_cascade_links.py` runs
  without flags, then it writes nothing and prints the count of each class per company, the
  rows whose state would change and to what, and the To buy quantity delta.
* **AC-LT-42 [BE][T] (G5)** Given the same set, when the script runs with `--apply`, then (a),
  (d), (e) are untouched; (b) becomes a suggested link of the same target and qty with
  trigger `converted`, and the link and its claim are removed; (c) is removed with its claim
  and the row note "Link to <doc> removed: suggested by the cascade, not named by AutoCount
  (24 Sep ruling)"; every touched row is refreshed through `refresh_link_state`.
* **AC-LT-43 [BE][T]** Rows in `actioned` or `cancelled` state are never touched. A second
  `--apply` changes nothing.
* **AC-LT-44 [BE][T]** Classification reads `_book_names_target_for_line` (the book itself),
  never the row note's `auto:` stamp: a seeded book link whose note says `auto: worklist`
  (the book step inside a cascade pass) is class (a).
* **AC-LT-45 [E2E] (G5)** On the 23 Sep prod copy restored locally (never the cloud), the dry
  run's output is pasted into plan section 7 before the owner decides to apply.

## Group S6 - browser evidence (end of lane)

* **AC-LT-50 [E2E] (J1 to J6)** agent-browser, sidebar clicks from `/`, on a seeded order:
  board Confirm raises a row the book does not name; Order Inquiries shows it To buy with a
  Suggested cell and blank PO and SPO; opening the Suggested cell's document highlights the
  suggested line in the lightbox's lines grid (R13 - no separate panel); pressing Link
  selected on the ticked row re-runs the AutoCount book step and refreshes its suggestions -
  the toast names how many rows AutoCount linked, how many still hold a suggestion, and how
  many changed (R18: it never itself turns the row On PO/SPO); Auto link all's toast names
  its own book-linked and suggested counts. Screens at 1280 and 375, `console` and `errors`
  clean.
* **AC-LT-51 [E2E] (J1)** On the same stack, a row whose sales order line a PO line names in
  the book shows the document in the PO column and reads On PO/SPO with no Suggested cell.
