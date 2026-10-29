# UAC: OI rows auto-confirm, OI auto-complete (OI-AUTO-CONFIRM)

Status: DRAFT on the recommended answers (Q1 b, Q2 a, Q3 a, Q4 a, Q5 a). Rewritten when the
owner answers. Plan: `PLAN-oi-auto-confirm-29oct.md`.

Terms: a row is DONE when purchasing has nothing left to do on it. A live row is any row not
cancelled.

## Row done

- AC-AC-1 A row whose full qty is covered by PO-line links is done.
- AC-AC-2 A row whose full qty is covered by SPO-allocation links is done (Q2).
- AC-AC-3 A row whose full qty is covered by any mix of PO, SPO and reserve links is done.
- AC-AC-4 A row purchasing rejected is done, with no link.
- AC-AC-5 A row covered for part of its qty is NOT done; it shows the qty left to order
  (needs 10, PO covers 6 -> "4 left") (Q1).
- AC-AC-6 A row with no link and not rejected is not done, whatever its supply state reads
  (a `placed` row with no link is not done) (Q5). The one exception is a companion row, AC-AC-10a.
- AC-AC-7 A row from a sheet-migrated OI that purchasing marked done (`actioned`) is done.
- AC-AC-8 An information-only row (DELAY, ADVANCE, CANCEL BALANCE and the other non-buy verbs)
  is done at birth.
- AC-AC-9 A row whose link is removed (PO cancelled, line dropped in AutoCount, untag) is no
  longer done on the next read, with nobody pressing anything (Q3).
- AC-AC-10a A companion ("supplied with") row is done only when its own links plus its bundled
  qty cover its qty AND its host row is done; it never needs a PO of its own (Q5).
- AC-AC-10b A reserve-only row shows its reserve ("Reserved @ <location>") in the PO/SPO column
  instead of "-" (Q5).
- AC-AC-10 A done row CS amends to a qty above its links is not done until the extra is covered;
  a date-only amendment to a covered row leaves it done.

## OI header

- AC-AC-11 An OI is Completed when every live line is done; otherwise Outstanding.
- AC-AC-12 The documents list Lines column reads "N to order / total" on an Outstanding OI.
- AC-AC-13 The Outstanding filter of the documents list returns exactly the OIs with a line not
  done; Completed returns the rest; counts match the Lines tab of each OI.
- AC-AC-14 An OI reopens (Completed -> Outstanding) when a row loses its link, and completes again
  when it is relinked, with no press.

## Presses removed

- AC-AC-15 The OI Lines list has no Confirm (N) button and no Unconfirm (N) menu item.
- AC-AC-16 The OI detail has no Confirm button and no Unconfirm menu item.
- AC-AC-17 POST /order-inquiries/acknowledge and /unacknowledge no longer change any row
  (removed, or answer 410 with a plain message).
- AC-AC-18 The Lines list "To confirm" chip / filter becomes "To order" and filters on not done.
- AC-AC-19 Reject stays, with its reason and its email, unchanged.
- AC-AC-20 "Link now" links awaiting rows as well as previously acknowledged ones.
- AC-AC-21 The fulfilment board Confirm / Apply AutoCount change(s) and the planning sheet
  Confirm Project SO are unchanged, and still send the purchasing email + Excel + in-app task.

## Reorder plan

- AC-AC-22 The reorder plan counts every live, not-rejected project buy row's unlinked qty as
  demand, whatever its old acknowledgement (Q4).
- AC-AC-23 The plan page no longer shows the "N awaiting acknowledgement" chip.

## Data

- AC-AC-24 No backfill: existing OIs on prod read under the new rule the moment it ships.
