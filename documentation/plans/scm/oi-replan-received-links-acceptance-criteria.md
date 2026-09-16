# UAC - OI replan with received links (redirect the old row, raise a fresh Buy row)

Plan: `PLAN-oi-replan-received-links.md`. Status: IN PROGRESS, 16 Sep 2026 (issues #957-#961).

## Journey

**Actor:** CS planner (fulfilment planning board), then purchasing (order inquiries worklist).

**Where they arrive from:** the SO book upload moved SO314593 from 01/06/2026 to 01/03/2027 and
raised line 1 (B2154-NL) from 182 to 220. A planning change batch is pending. The CS planner
opens Supply Chain, Project Demand, Fulfilment Planning, plans SO314593.

**What the system already knows:** OI-000477 line 1 is a row of 182, `partly_linked`, 158 on
SPO-2026/01-0143. That SPO line is closed, fully received on 19 Jan 2026 into BRW-IR. BRW-IR
holds 537 of B2154-NL; four earlier orders claim 1305. The board's ladder answers "no stock
for this line: the delivery date is beyond the lead time window, purchasing can still buy in
time" and proposes Buy 220.

**Steps and the single decision each:**

1. CS planner reads the line. The "What changed" dialog shows `Qty 182 -> 220`,
   `Date 1 Jun 2026 -> 1 Mar 2027` (year present, so a delay to next year cannot be read as
   an advance). Decision: Confirm.
2. Confirm runs. Settle-in-place meets a row whose linked document is fully received. It does
   not carry that row: the row is marked redirected (goods went to location stock, no longer
   this line's), its documents stay on it as history, and a fresh ORDER row of 220 dated
   01/03/2027 is raised with no links. No decision asked of anyone.
3. Purchasing opens Order Inquiries, searches SO314593. Two rows for B2154-NL: the old one,
   182, greyed, `received` on the SPO chip and `used` on the quantity, every detail behind
   the word's lightbox; the new one, 220, 01/03/2027, no documents, in the Buy card.
   Purchasing decides nothing new: the row reads as a plain buy.
4. Next AutoCount upload (SO book, PO book, OI sheet). Nothing re-links the received SPO to
   either row. The pairing stays in AutoCount and is harmless.

**What they hold at the end:** stock debt and the Buy card carry 220 for 01/03/2027;
`committed_v` for the line no longer nets the 158 that shipped to other orders a year ago;
the received document is still visible on the row that bought it.

**What every other stakeholder is told automatically:** purchasing sees the change through
the existing handshake (`ack_state = changed` on the redirected row is NOT set; the new row is
born acknowledged as every raise is). No new notification.

## Phase 1 - frontend, mocked

- **AC-RL-01 [FE]** Given the "What changed" dialog on a board line whose date moved, When
  it renders the Date field, Then both dates carry the year (`1 Jun 2026 -> 1 Mar 2027`),
  and the month spelling stays the hand-rolled short form (`Sep`, not `Sept`).
- **AC-RL-02 [FE]** Given an OI worklist row whose link dict carries `received: true`, When
  the PO or SPO chip renders, Then the chip shows the document number followed by ONE
  one-word mark `received` (same muted pill style as `via PO`, no icon), the row stays a
  single line, and clicking the word opens the backing-documents lightbox showing
  `Received <received_qty> of <qty>` for that link. (Rulings 17 Sep: one line per row,
  words not icons, details behind the word.)
- **AC-RL-03 [FE]** Given the backing-documents dialog on that row, When a link row renders,
  Then it prints `received <received_qty>` beside the location and quantity, and an open
  document prints nothing extra.
- **AC-RL-04 [FE]** Given an OI worklist row with `redirected_to_pool: true`, When it
  renders, Then the row is greyed, its Qty cell carries ONE one-word mark `used` (no icon)
  that opens the Qty annotation lightbox reading `<document> received <date> into
  <location>, used by earlier orders. Bought again at revision <n>: see the new row`, and
  the row is excluded from the Buy / Purchased / Incoming card totals. The word on screen
  is `used`, never `redirected` (ruling 17 Sep).
  - **Amended, 17 Sep review round**: "the row is greyed" means every cell of the row
    (item code, qty, etc.) carries the same `opacity-60` this table already uses for an
    inactive row (`components/ui/data-grid-table.tsx`'s own holding-row class - no
    `state === 'cancelled'` precedent exists in this component today, so the review reuses
    the shared DataGrid convention rather than inventing a new one). The lightbox itself
    must never print the word "Redirected" anywhere in its own content (today's
    `OrderInquiryQtyAnnotationDialog` `DialogDescription` prints it literally for exactly
    this row shape) - it reads `Used` instead. On the SEPARATE `note` trigger (AC-RL-46,
    an AutoCount book move, never `redirected_to_pool`), the lightbox's own section heading
    reads `Moved by AutoCount`, not `Redirected` - the two callers of `MovedSection` no
    longer share one heading.
    Tests: `orderInquiryWorklistColumns.test.tsx` describe block "AC-RL-04 amended (17 Sep
    review round)".
- **AC-RL-05 [UX]** No new motion. The `received`, `reallocate`, `unlink`, `used` and `note`
  marks are static one-word pills; chips stay truncated with `title`; the row is usable at
  375px and 1280px.
- **AC-RL-06 [FE]** Given the fulfilment planning list view, When a line's linked inquiry
  cell renders, Then the inquiry number and the word `received` (every document of the
  row's inquiry fully received) or `used` (the row is redirected) appear whenever the
  contribution's `order_inquiry.documents` / `redirected` say so, on a covered line AND on an
  uncovered line with a live proposal; a line that carries its own decision keeps its
  decision slot instead (shipped rule, reconciled 17 Sep after review).
- **AC-RL-07 [BE]** The board contribution's `order_inquiry` dict carries `documents`:
  `[{document, kind, received}]` and `redirected` (bool) for the line's live row(s), read
  through `links_for_rows` (no second query shape).

## Phase 2 - backend, test-first

Settle seam (`ProjectOrderInquiryService.refresh_for_decision` and `_settle_row_in_place`):

- **AC-RL-10 [BE]** Given a line with one still-owed row whose every link points at a fully
  received document (PO line: `qty_received >= qty_ordered` or `line_status = 'closed'`; SPO
  allocation: fails `open_incoming_clauses()`), When a planning change confirmation settles
  that line, Then the row is NOT settled in place: `redirected_to_pool` becomes true, its
  `qty`, `delivery_date`, `state` and links are left exactly as they were, and its note gains
  `; <document> received <date or 'in full'>, goods are <location> stock, released at
  revision <n>`.
- **AC-RL-11 [BE]** Given AC-RL-10, When the same confirmation continues, Then a fresh
  `ORDER` row is raised for the full need (qty = the confirmation's buy quantity, delivery
  date = the confirmation's required date), state `raised`, no links, `previous_qty` and
  `previous_delivery_date` null.
- **AC-RL-12 [BE]** Given a row with one received link and one open link (mixed), When the
  confirmation settles the line, Then the received link stays on the redirected row, the
  open link is removed from it through `_remove_links` (its capacity returns to the target),
  and the raise-time cascade may draft that open document onto the new row.
- **AC-RL-13 [BE]** Given a row whose every link is still open (not received), When the
  confirmation settles the line, Then behaviour is unchanged from today: settle-in-place,
  links kept, `previous_qty` / `previous_delivery_date` carried.
- **AC-RL-14 [BE]** Given a redirected row, When the next auto cascade runs (`auto_place_for_
  products` with any trigger) and when the OI sheet importer re-uploads the same sheet, Then
  no link is written to the redirected row and the received document is not linked to the new
  row (its capacity is zero). Test both writers.
- **AC-RL-15 [BE]** Given a redirected row and its replacement, When `committed_v` (every
  lateral join in `app/services/scm/demand.py` over `projects.order_inquiry_links`) is read
  for the SO line, Then the redirected row contributes nothing (neither its qty nor its
  links) and the new row contributes its full qty.
  - **Rewritten, 17 Sep review round (B1)**: this must hold on the FORM leg specifically -
    a row with NO supply decision at all (`supply_decision_id IS NULL`), naming its product
    and location by code the way the CS form does, never via `ProjectSupplyService.
    confirm()` whose own `d.state = 'active'` join could drop the confirmed leg's row as a
    side effect and mask a broken exclusion. Toggling ONLY `redirected_to_pool` on the same
    form-raised row must move `scm.committed_v`'s `project_committed` (planned=False) by
    exactly the row's own unlinked (owed) quantity.
    **Status: already shipped.** Migration `512_committed_v_redirect_exclude` (commit
    `676d0e71c`, landed before this review round) added `AND oir.redirected_to_pool = FALSE`
    to BOTH the confirmed and form legs; `demand.py`'s `NOT_REDIRECTED_SQL` constant is
    already threaded through every leg. `test_committed_v_ignores_a_form_raised_redirected_
    row` (`tests/scm/test_oi_replan_committed_v.py`) is GREEN today - kept in the suite as a
    regression guard, not a red test the coder needs to make pass.
- **AC-RL-15b [BE]** Given the same form-raised redirected row, When the LIVE horizon path
  a reorder plan run actually reads (`demand.horizon_committed_select_sql()` and its date
  companion `horizon_project_need_dates_sql()`, both built fresh at call time off `NOT_
  REDIRECTED_SQL`) is read for the product, Then the redirected row contributes nothing to
  either - not only the frozen `scm.committed_v` migration body AC-RL-15 pins, but the
  Python-built SQL a live plan run actually executes.
  **Status: already shipped**, same commit as AC-RL-15. `test_committed_v_horizon_and_need_
  dates_ignore_a_form_raised_redirected_row` is GREEN today, kept as a regression guard.
- **AC-RL-16 [BE]** Given the OI worklist for that SO, When rows serialize, Then the
  redirected row is excluded from the Buy / Purchased / Incoming stage totals and from
  `taken_from_po` / `remaining_open`, and its `redirected_to_pool` reaches the FE.
- **AC-RL-16b [BE]** Given the Order Inquiries schedule matrix for that SO, When its stage
  cards compute, Then the redirected row is not counted under Purchased or Incoming.
- **AC-RL-16c [BE]** Given the same redirected row, only PARTLY linked (its unlinked
  remainder still positive), beside a fresh row, When the worklist LIST filters
  `kind=buy` (`order_inquiry_worklist_service.py`'s own `_UNLINKED_QTY > 0` query - a
  SEPARATE query from the stage-total summary AC-RL-16 already covers), Then the redirected
  row's own unlinked remainder is excluded from the `kind=buy` rows too, so a click into the
  Buy card never shows a row the card's own number has already excluded. RED today: the
  filter carries no `redirected_to_pool` exclusion of its own.
- **AC-RL-16d [BE]** Given the same redirected confirmed-leg row, When `demand_breakdown_
  service`'s own copies of the confirmed and form legs (`~:514`, `~:591`) sum project demand
  for a drill-down popover, Then the redirected row is excluded there too - quantity that
  already shipped to another order must not appear in the popover as demand still open.
  RED today: neither copy excludes `redirected_to_pool`.
- **AC-RL-16e [BE]** Given the same redirected row's OWN placement (a link on the core
  line's project mirror recorded before the redirect), When the loading plan's `_PLACED_ON_
  LINE_SQL` (container-request build_open_need) sums placement to net a line's own open
  need, Then a redirected row's placement does not net that need down - the goods already
  shipped to another order, so purchasing must still read the line's full outstanding
  quantity to buy. RED today: `_PLACED_ON_LINE_SQL` sums every link with no exclusion.
- **AC-RL-17 [BE]** Given any link, When `links_for_rows` serializes it, Then the dict
  carries `received_qty` (PO: `qty_received`; SPO: `quantity_received`) and `received`
  (true when the document is fully received by the AC-RL-10 test), and
  `OrderInquiryLinkOut` declares both (response_model drops undeclared fields).
- **AC-RL-18 [BE]** Given a redirected row's note and the new row, When
  `order_inquiry_changed_with_links` automation evaluates, Then it does not fire for the
  redirected row (nothing on it changed) and does not fire for the new row (it has no links).
- **AC-RL-19 [T]** Kill test targets: AC-RL-10 (comment out the received test -> settle
  keeps the link, test red), AC-RL-15 (comment out the demand.py exclusion -> `committed_v`
  nets 158, test red).

Repoint suggestion (S1b):

- **AC-RL-20 [BE]** Given an open link whose `expected_date` is on or before the row's
  `delivery_date` minus the product's lead time days (fallback `DEFAULT_LEAD_TIME_DAYS`), and
  one or more linkable rows (raised or partly linked, linkable verb and ack) for the same
  product on a different SO line with open need and an earlier `delivery_date`, When the
  worklist page serializes, Then the link dict carries `suggestion.kind = "reallocate"` and
  `suggestion.candidates`, EVERY such row ordered by delivery date ascending then open need
  descending, each with inquiry number, item code, SO number, delivery date and open
  quantity; the first candidate is the suggested target (ruling 17 Sep: list all, earliest
  first).
- **AC-RL-21 [BE]** Given the same early link and no such row, Then `suggestion.kind =
  "unlink"`.
- **AC-RL-22 [BE]** Given a link inside the lead time window, or a received link, Then
  `suggestion` is null.
- **AC-RL-23 [BE]** `OrderInquiryLinkOut` declares `suggestion`; the page computes it with
  one grouped query per page (assert query count does not grow with rows).
- **AC-RL-24 [FE]** Given a link with a suggestion, When the chip renders, Then it carries
  ONE one-word amber mark, `reallocate` or `unlink` (no icon), the row stays a single line,
  and clicking the word opens a lightbox headed by the document, item and quantity, stating
  expected date and this row's delivery date, then the candidate list earliest first with the
  first row marked `Reallocate to`, each as `<inquiry> · <SO> · needed <dd/mm/yyyy> · open
  <n>`, and the footer `Re-key the line to the chosen sales order in AutoCount; the link
  moves at the next upload`. With no candidates the lightbox reads `Unlink · no sooner
  inquiry needs this item`. No reason text, no "early", no "repoint" on screen. Nothing is
  written from the lightbox.

Our link follows the book pairing (S5):

- **AC-RL-40 [BE]** Given a PO line linked to row A (SO line A) and an ESB ingest that
  re-pushes that line with `from_so_line_ref` naming SO line B, which has a linkable row B
  with open need, When the ingest commits, Then row A no longer holds the link, its note
  reads `AutoCount moved <PO number> to <SO B> on <date>`, row A's state falls back
  (`raised` or `partly_linked`), and row B holds a link to the same PO line for
  `min(freed qty, need)` with `auto = true`.
- **AC-RL-41 [BE]** Given the same move and SO line B has no linkable row, Then the link is
  removed from row A only and the PO line's capacity is free (`_linked_by_target` excludes it).
- **AC-RL-42 [BE]** Given an SPO allocation linked to row A and a shipping-order ingest that
  moves its `from_so_line_ref` to SO line B, in place or through `_supersede_xlsx_rows`, Then
  the same outcome as AC-RL-40 / 41.
- **AC-RL-43 [BE]** Given a fully received PO line or SPO allocation whose ref moves, Then no
  link changes (S2 owns received documents).
- **AC-RL-44 [BE]** Given a link written by hand (`auto = false`) on row A, Then it follows
  the book the same way.
- **AC-RL-45 [BE]** Given a re-push with `from_so_line_ref: null`, Then the link on row A is
  removed with the note `AutoCount removed <document> from <SO A> on <date>` and nothing is
  placed (ruling 17 Sep: auto remove and note). A re-push with the same ref changes nothing.
- **AC-RL-46 [FE]** Given row A after a move (no links left, note carries `AutoCount moved`),
  When its Qty cell renders, Then it carries ONE one-word mark `note` that opens the existing
  Qty annotation lightbox showing the move note. No new trigger on an empty documents cell;
  the row stays one line.

Security review findings, 17 Sep (S5's `follow_book_repairing` and its three capture sites -
`document_ingest_service.py`, `shipping_order_ingest_service.py`):

- **AC-RL-47 [BE]** Given a PO/SPO line's `from_so_line_ref` moved to a well-formed ref that
  names no line this company has ever pushed (the ordinary "not yet resolvable" case - the
  SO has not landed yet), When the ingest commits, Then row A's existing link and note are
  untouched. `_resolve_ref_line` returning `(None, None)` for an UNRESOLVABLE ref must not
  be read the same way an explicit `from_so_line_ref: null` is (AC-RL-45) - only a genuine
  `null` clears a link.
- **AC-RL-48 [BE]** Given a ref that resolves to a real sales-order line belonging to
  ANOTHER company, When the ingest commits under this company's own anchor, Then row A's
  link is untouched and nothing is placed for the foreign company either. `_resolve_ref_
  line`'s lookup must be scoped to the pushing company; an unscoped lookup resolves a
  foreign line as confidently as one of ours.
- **AC-RL-49 [BE]** Given ONE record with two lines, where line 1's ref move is captured
  into `service.ref_moves` mid-`_sync_lines` and line 2 fails later in the SAME call
  (numeric overflow or any other `except Exception` path), causing `_ingest_one` to roll the
  whole record back, When the route's post-commit hook reads `service.ref_moves`, Then the
  failed record's own captured move is NOT applied - a move whose own ref change was never
  actually persisted must not be applied regardless.
- **AC-RL-50 [BE]** Given a single push naming more than `FOLLOW_BOOK_REPAIRING_MAX_MOVES`
  ref moves in one request, When `follow_book_repairing` processes them, Then it stops at
  the cap, applies no more than the cap's count, and logs a warning naming what was skipped.
  Cap value: 200 in production; the test proves the mechanism with a monkeypatched smaller
  cap rather than seeding 200+ rows.
- **AC-RL-51 [BE]** Given two `sales_order_lines` rows sharing one `source_ref` (a data
  anomaly the ESB should never produce, but the column carries no unique constraint to
  refuse it), When a ref move resolves against that shared ref, Then no move is applied (the
  ambiguous ref is refused, not guessed at) and a warning is logged. `_resolve_ref_line`'s
  `.first()` must not silently pick whichever row Postgres happens to return first.
- **AC-RL-52 [BE]** Given a PO/SPO line whose `from_so_line_ref` (the OLD ref) is a
  well-formed ref that resolves to no line, When the ingest commits, Then row A's real link
  (established independently of this push) is NOT swept up as a candidate for the move - an
  unresolvable OLD ref is not the same fact as NO old ref at all (the genuine xlsx-supersede
  case), and only a genuinely-proven "was on this line" fact should ever move a link.

## Phase 3 - end to end

- **AC-RL-30 [E2E]** On the 15 Sep prod copy, plan SO314593, Confirm all. Order Inquiries
  shows two B2154-NL rows for OI-000477: 182 redirected with `SPO-2026/01-0143 · received`,
  and 220 dated 01/03/2027 with no documents. Buy card includes 220. Recorded agent-browser
  run, sidebar navigation from `/`, 1280px and 375px.
- **AC-RL-31 [E2E]** Same copy, re-upload the 15 Sep OI sheet and re-run "Auto link all".
  Both B2154-NL rows keep their link count (1 and 0).
- **AC-RL-32 [E2E]** Same copy, ingest a PO payload moving 202607-S0077 (CB2805A-DIY) from
  SO314594 to SO314595's line. OI-000586 CB2805A-DIY shows the PO; OI-000539 CB2805A-DIY sits
  in the Buy card with the move note in its popover.

## Out of scope (backlog)

- One-step undo of a board confirmation ("reset one revision back", owner request 16 Sep).
- Retiring the "SPO answers only an ORDER BACK row" docstrings (S5 of the Excel parity plan).
