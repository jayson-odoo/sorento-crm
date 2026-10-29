# UAC: OI rows auto-confirm, OI auto-complete (OI-AUTO-CONFIRM)

Status: owner answered the behaviour card 29 Oct 2026 (~22:45): Q1 b, Q2 SPO counts (it hangs off
a PO), Q3 a, Q4 the reorder plan keeps reading confirmed rows, Q5 yes. Plan:
`PLAN-oi-auto-confirm-29oct.md`.

Terms: a row is DONE (stored as `ack_state = acknowledged`, shown "Done") when purchasing has
nothing left to do on it. A live row is any row not cancelled. A LIVE link is one whose PO line is
not cancelled and whose SPO allocation is not retired.

## Row done (written by the system, never by a press)

- AC-AC-1 A row whose full qty is covered by live PO-line links is done.
- AC-AC-2 A row whose full qty is covered by live SPO-allocation links is done.
- AC-AC-3 A row whose full qty is covered by any mix of live PO, SPO and reserve links is done.
- AC-AC-4 A row purchasing rejected stays `rejected`; it counts as done for the OI header.
- AC-AC-5 A row covered for part of its qty is not done; it shows the qty left
  (needs 29, PO covers 21 -> "To order · 8 left").
- AC-AC-6 A row with no live link and not rejected is not done, whatever its supply state reads
  (a `placed` row with no link is not done). The one exception is a companion row, AC-AC-10a.
- AC-AC-7 A row purchasing marked done (`actioned`, the sheet-migrated history) is done.
- AC-AC-8 An information-only row (DELAY, ADVANCE, CANCEL_BALANCE and the other non-buy verbs) and
  a used row (`redirected_to_pool`) are done at birth.
- AC-AC-9 A row whose link is removed or dies (PO line cancelled, SPO retired, untag) is not done
  after that write, with nobody pressing anything; a done row that was `acknowledged` goes back to
  `awaiting`.
- AC-AC-10 A done row CS amends to a qty above its links is not done (keeps `changed`, shows the
  qty left) until the extra is covered; an amendment that leaves it covered keeps it done.
- AC-AC-10a A companion ("supplied with") row is done only when its own live links plus its bundled
  qty cover its qty AND its host row is done. When the host becomes done or not done, its
  companions follow in the same write.
- AC-AC-10b A reserve-only row shows its reserve ("Reserved @ <location> <qty>") in the PO column
  instead of "-".
- AC-AC-10c A row the system marks done carries `acknowledged_at` = the moment it became done and
  `acknowledged_by` = NULL (no person pressed anything).

## OI header

- AC-AC-11 An OI is Completed when every live line is done (or rejected); otherwise Outstanding.
- AC-AC-12 The documents list Lines column reads "N to order / total" on an Outstanding OI; the
  Outstanding empty state reads "Nothing to order".
- AC-AC-13 Outstanding returns exactly the OIs with a live line not done; Completed returns the rest;
  the counts match the Lines tab of each OI.
- AC-AC-14 An OI reopens when a row loses its link, and completes again when it is relinked, with no
  press.

## Presses removed

- AC-AC-15 The OI Lines list has no Confirm (N) button and no Unconfirm (N) menu item.
- AC-AC-16 The OI detail has no Confirm button and no Unconfirm menu item.
- AC-AC-17 POST /order-inquiries/acknowledge and /unacknowledge are removed (404).
- AC-AC-18 Row labels: "To confirm" reads "To order", "Confirmed" reads "Done"; the Lines list
  quick chip and Status filter use the new words.
- AC-AC-19 Reject stays, with its reason and its email, unchanged.
- AC-AC-20 "Link now" links awaiting rows as well as acknowledged ones.
- AC-AC-21 The fulfilment board Confirm / Apply AutoCount change(s) and the planning sheet
  Confirm Project SO are unchanged and still send the purchasing email + Excel + in-app task.

## Reorder plan (Q4)

- AC-AC-22 The reorder plan keeps counting project demand on `acknowledged`/`changed` rows only,
  exactly as today; the state is now written by the system. (Consequence, PR body: a done row is
  covered, so planned project demand falls to the uncovered remainder of `changed` rows; measured
  1,761 rows / 95,499 pcs today on the 28 Oct prod copy.)

## Data

- AC-AC-23 A one-time data migration sets every live, not-rejected row to the state AC-AC-1..10c
  give it (done -> `acknowledged`; not done and `acknowledged` -> `awaiting`; `awaiting`/`changed`
  not done unchanged). Checked on a dev copy before the hand test; the counts match the card.
- AC-AC-24 The migration is idempotent: a second run changes nothing.
