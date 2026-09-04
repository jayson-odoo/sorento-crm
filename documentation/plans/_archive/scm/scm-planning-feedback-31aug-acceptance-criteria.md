# UAC: Fulfilment planning feedback batch, 31 Aug

Companion to `PLAN-scm-planning-feedback-31aug.md`. Every criterion is testable; S1/S2
land as pytest, S3 as vitest + a recorded agent-browser run.

## S1 - Incoming = SPO only

- AC-1.1 A planning unit whose only whole-covering supply document is a purchase-order
  line receives NO "Borrow incoming"/"Use incoming" offer; the walk falls through to the
  pool step and, failing that, Buy.
- AC-1.2 A planning unit covered by a single SPO behaves exactly as before this change
  (same offer, same sentence, same fulfil date).
- AC-1.3 No suggestion, option row, or composition sentence produced by the engine names a
  purchase-order document. Grep-level assertion in tests: the rendered reasons for a book
  containing an eligible PO never contain that PO's number.
- AC-1.4 `assignments_for` still reads purchase orders: PO netting (SPO cut out of PO),
  the stock table's "PO qty" column, and Stock Debt outputs are byte-identical for a book
  with no SPOs borrowed.
- AC-1.5 The PR body records the measured impact on the captain's 76-unit batch:
  units whose step-3 document was a PO before, and which category each moved to.

## S2 - transfer_days setting, default 0

- AC-2.1 With no policy row and with an existing policy row that predates the migration,
  `transfer_days` reads 0 and a pool-take option's fulfilled date equals as_of (same as an
  own-location take). The captain's 02/09-for-a-31/08-plan case reads 31/08, days late 6
  not 8.
- AC-2.2 With `transfer_days = 2` saved on the policy, a non-own-location option's
  fulfilled date is as_of + 2 and days-late follows; an own-location option is never
  charged.
- AC-2.3 The settings endpoint round-trips `transfer_days` (assert the field is present in
  the response - response_model lesson), rejects negatives with a coded 422, and the FE
  settings surface shows and saves the field at 375px and 1280px.
- AC-2.4 Changing the setting changes the NEXT walk; no stored decision is rewritten.

## S3 - Lightbox navigation

- AC-3.1 One click on a grid cell's order line opens the lightbox with the own-location
  detail expanded, scrolled so the first "This line" row is visible, and that row visibly
  highlighted. No intermediate expand/hunt step.
- AC-3.2 Inside the lightbox, a "My line" control repeats that scroll+highlight from
  anywhere in the table.
- AC-3.3 When the suggestion borrows from another order, the donor SO number in the
  suggestion sentence is a link; activating it expands the holding location, scrolls to
  the donor row, and badges it "Donor". The badge and "This line" can coexist on screen.
- AC-3.4 When the suggestion uses/borrows incoming, the SPO number in the sentence is a
  link; activating it expands that location's incoming detail, scrolls to and highlights
  the document row.
- AC-3.5 The stock table and the contributing-lines table each carry a `ListSearchInput`
  that filters by SO number, customer, and agent; a spinner runs until rows land; a miss
  shows an explicit empty state; clearing restores the full table.
- AC-3.6 All of the above usable and non-clipped at 375px and 1280px; every jump target
  works inside the lightbox's own scroll container (scrollintoview before highlight).
- AC-3.7 Recorded agent-browser run: grid -> cell click -> My line -> donor jump ->
  incoming jump -> search -> clear, navigated from `/` via the sidebar.

## Mockup round 2 additions (31 Aug)

- AC-3.8 The whole grid cell is the click target (hover ring + pointer); no separate small
  link. Landing at "This line" is the lightbox's default open position from a cell click.
- AC-3.9 The lightbox toolbar (search + My line + Donor + document jump buttons) is sticky
  at the top of the lightbox's scroll container; Donor and document buttons render only
  when the active suggestion names one.
- AC-3.10 An SPO row in the expanded detail shows +qty and a running balance that ADDS at
  its chronological position; rows are strictly date-ordered so an arrival never reads as
  covering a commitment dated before it.
- AC-3.11 S3 UI obeys the apple-design skill + PRINCIPLES design mandates: reduced-motion
  respected, jump highlight is a fading flash (not a persistent second selection), sticky
  toolbar does not jitter while scrolling, end-state geometry verified in the browser run.
- AC-3.12 The projection ledger is strictly date-ordered: a commitment dated before an
  SPO's arrival deducts from the pre-arrival balance (captain's SO410406 case: 1887, not
  1917); the SPO row adds at its own date position.
- AC-3.13 In a Borrow-incoming suggestion, the waiting order (the SPO's donor) is a link
  and a Donor jump target exactly like an on-hand borrow's donor; both the SO link and the
  SPO document link work from one sentence.

## S4 - PO never supplies planning (1 Sep)

- AC-4.1 A unit whose only cover at any rung is PO-backed receives no offer from steps 1-4
  and lands on Buy; no option, suggestion, or composition anywhere dates itself off a PO.
- AC-4.2 A unit covered by an SPO (own group or another group's free pile) behaves as
  before; the sentence names the SPO and its arrival.
- AC-4.3 Assignment outputs, Stock Debt view, and the PO qty column are unchanged by the
  exclusion (asserted the AC-1.4 way).
- AC-4.4 The chosen step-1 option row's label matches the composition: "Use incoming"
  when the cover is on the water, and it names the lending group when cross-group; the
  board card and the option row can no longer disagree.
- AC-4.5 The use-incoming SPO document is a link with the S3 jump behaviour, and the SPO
  leg appears in that location's expansion.
- AC-4.6 PR body records the rerun probe: SO381895 category counts before and after.
