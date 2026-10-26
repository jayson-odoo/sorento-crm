# UAC - AC-REMOVED-LINES: a line removed in AutoCount releases its links

Status: DRAFT, written to the card's recommendations; final once the owner answers Q1-Q5
(`ac-removed-lines-behaviour-card.md`). Plan: `PLAN-ac-removed-lines-26oct.md`.

## Journey

Purchasing deletes a PO line in AutoCount (or moves its qty onto another line of the same PO).
The next AutoCount push reaches the CRM. The line shows as Removed, nothing is placed on it any
more, and every sales order row that was placed on it is back in purchasing's To confirm with a
note saying why, plus a suggested link to the line the qty went to. The same happens for an SPO
line AutoCount drops, and a sales order line AutoCount deletes gives its placements back.

## Criteria

Marker (R1)
- AC-RL-01 A PO line whose DtlKey a push of its (not cancelled) PO no longer carries, and that
  something references, ends `line_status = cancelled` AND `removed_at` set. Same for an SO line.
- AC-RL-02 A line cancelled by a Cancel PO / Cancel SO document, by a header cancel, or on the CS
  Cancel SO board never gets `removed_at`, and its links are untouched (regression guard for
  LINKAGE-UNIFY Q5).
- AC-RL-03 A ref-less (xlsx-era) line swept at adoption gets no `removed_at` and keeps its links.
- AC-RL-04 A removed line whose DtlKey comes back in a later push loses `removed_at`; the links
  released earlier are not restored.
- AC-RL-05 Re-pushing the same reduced document again changes nothing more (idempotent: no second
  note, no second To confirm flip on a row purchasing already confirmed).

PO / SPO line removed (R2)
- AC-RL-10 Every OI link on the removed PO line is deleted; the row's state recomputes from what
  is left (placed -> raised, or partly linked when another link remains); an `actioned` row keeps
  `actioned`.
- AC-RL-11 Each affected row has `ack_state = changed` (To confirm) and its note ends
  "Unlinked from <PO number>: line removed in AutoCount".
- AC-RL-12 Open `order_link_claim` rows and suggested links on the removed line are resolved /
  dropped.
- AC-RL-13 PO detail Placed for the removed line reads 0 after the push.
- AC-RL-14 An SPO line retired by a push (`retired_at` newly set) gets AC-RL-10..12 for links
  on `spo_allocation_id`, note "Unlinked from <SPO number>: line removed in AutoCount".
- AC-RL-15 A reserve (stock) link on the row is untouched.

SO line removed (R3, Q1 rec a)
- AC-RL-20 The removed SO line's live raised / partly linked / placed rows are cancelled with
  their links released, an `OI_ROW_CANCELLED` audit row and a purchasing handover entry, the way
  `retire_rows_for_cancelled_lines` does for Transfer to Cancel SO; `actioned` rows are only
  flagged to To confirm.
- AC-RL-21 Stock holds (`so_line_allocations`) on the removed SO line are released.

Moved qty (R4, Q3 rec a)
- AC-RL-30 When the same push leaves another line of the same PO with the same product and room
  for the released qty, the released row carries a suggested link to that line (trigger
  `ac_removed`), and no real link is created.
- AC-RL-31 With no such line, no suggested link is written.

Reconciliation (R6, Q4 rec a)
- AC-RL-40 `scripts/release_removed_autocount_lines.py` `run(db, company_id, dry_run=True)`
  returns counts and a per-line list (document number, DtlKey, product code, qty, placed qty,
  rows affected; no customer names) and writes nothing.
- AC-RL-41 With `dry_run=False` it sets `removed_at` on existing removed AutoCount lines (line
  cancelled, AutoCount source, header not cancelled, not by a Cancel document, not CS-cancelled)
  and applies AC-RL-10..21 through the same code the ingest uses; a second run changes nothing.

Display (R5, Q5 rec a; mock first)
- AC-RL-50 PO and SO detail show a removed line's status as a grey "Removed" pill, distinct from
  red Cancelled, at 1280 and 375.
- AC-RL-51 LINKAGE-UNIFY's goods chain reads a removed PO line / retired SPO line as dead, reason
  "PO line removed" / "SPO line removed" (lands in whichever of this PR and #1870 merges second).
