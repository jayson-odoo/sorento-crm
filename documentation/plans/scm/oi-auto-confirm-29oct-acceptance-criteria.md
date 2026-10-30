# UAC: OI rows auto-confirm, OI auto-complete (OI-AUTO-CONFIRM)

Status: owner answered the behaviour card 29 Oct 2026 (~22:45): Q1 b, Q2 SPO counts (it hangs off
a PO), Q3 a, Q5 yes; Q4 = b (~23:20); mock v1 notes (23:18): Confirm / Unconfirm stay as manual
overrides, documents list drops its Lines column. Override behaviour: crew-note on PR #1986. Plan:
`PLAN-oi-auto-confirm-29oct.md`.

Terms: a row is DONE (stored as `ack_state = acknowledged`, shown "Done") when purchasing has
nothing left to do on it. A live row is any row not cancelled. A LIVE link is one whose PO line is
not cancelled and whose SPO allocation is not retired, and whose PO line / SPO allocation is for the
row's CURRENT item, read the way the link writers read it: the SO line's product first, the row's
`item_code` only when the line has none (review rounds 1 and 2: an item swap leaves the old item's
link in place but it no longer covers the row; 6 rows on the 28 Oct copy carry an item_code that
differs from their SO line's product while their links follow the line). Reserve links have no
product check.

## Row done (written by the system unless a person overrides, see Manual override)

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
  qty cover its qty AND its host row is done (a manually confirmed host counts as done; a rejected
  host is no host, also right after the reject press). When the host becomes done or not done, its
  companions follow in the same write.
- AC-AC-10b A reserved row shows its reserve ("Reserved @ <location> <qty>") in the PO column, beside
  any PO chips. The reserve is NOT a document link (`links_for_rows` keeps leaving reserve links out,
  as on main, so no quantity is counted twice); rows carry `reserve_label` + `reserved_qty` instead.
- AC-AC-10d Rows carry `open_qty` = qty minus live cover minus bundled qty; "N left" reads it.
- AC-AC-10e Every live row on a CANCELLED SO line is done, with or without a PO / SPO link, and
  purchasing never has to act on it (owner, 30 Oct ~10:00: "OI rows on cancelled SO shouldn't need
  purchasing to confirm, it should just be done, I don't want purchasing intervention"; replaces lead
  ruling (c) and, for this case, the 20 Sep "purchasing must act" rule). The cancel does not stamp
  `changed`, queues no purchasing email or notice, and the row never counts in To order. A manual
  Unconfirm still overrides like on any row.
- AC-AC-10c A row the system marks done carries `acknowledged_at` = the moment it became done and
  `acknowledged_by` = NULL (no person pressed anything).

## OI header

- AC-AC-11 An OI is Completed when every live line is done (or rejected); otherwise Outstanding.
- AC-AC-12 The documents list has no Lines column (owner, mock v1 note); the Outstanding empty
  state reads "Nothing to order".
- AC-AC-13 Outstanding returns exactly the OIs with a live line not done; Completed returns the rest;
  the counts match the Lines tab of each OI.
- AC-AC-14 An OI reopens when a row loses its link, and completes again when it is relinked, with no
  press.

## Manual override (owner, mock v1 notes 23:18: keep Confirm / Unconfirm for manual overriding)

- AC-AC-15 Confirm (OI detail, Lines list Confirm (N), Select all N matching) stays. A manually
  confirmed row is Done even with no link, and stays Done whatever its links do, until Unconfirm.
- AC-AC-16 Unconfirm (OI detail menu, Lines list Unconfirm (N)) stays. A manually unconfirmed row is
  To order even if covered, and stays To order until Confirm, or until a link made AFTER the
  Unconfirm arrives; then the automatic rule decides again.
- AC-AC-17 A CS amendment (qty / date / item, today's `changed`) clears any manual override; the
  automatic rule decides again.
- AC-AC-17a Rejecting a row clears its override; a rejected row cannot be confirmed (today's guard).
- AC-AC-17b A manual decision is stored with kind (confirmed / unconfirmed), by and at, and the row
  status reads "Done · manual" / "To order · manual" with who and when on hover. Confirm writes one
  audit entry per press, like Unconfirm. A row the system marked done never reads "Confirmed by".
- AC-AC-17c Rows a PERSON confirmed before this ships stay Done (owner, 30 Oct ~10:35: "for SO lines
  someone confirmed, keep it confirmed for old lines"; reverses the 29 Oct point 7). The backfill
  records each stored `acknowledged` row with a person's name (`acknowledged_by` set) as a manual
  Confirm (`ack_override = 'confirmed'`, by / at copied from `acknowledged_by` / `acknowledged_at`), so
  the automatic rule never reopens it; a CS amendment or a reject clears it as for any manual Confirm.
  Rows the system marks done carry no name, so a re-run never freezes them.
- AC-AC-18 Row labels: "To confirm" reads "To order", "Confirmed" reads "Done" (owner may still pick
  "Confirmed"); the Lines list quick chip and Status filter use the new words.
- AC-AC-19 Reject stays, with its reason and its email, unchanged.
- AC-AC-20 "Link now" links awaiting rows as well as acknowledged ones.
- AC-AC-21 The fulfilment board Confirm / Apply AutoCount change(s) and the planning sheet
  Confirm Project SO are unchanged and still send the purchasing email + Excel + in-app task.

## Reorder plan (Q4 = b, owner 29 Oct ~23:20)

- AC-AC-22 The reorder plan counts every live, not-rejected project buy row that is To order
  (`awaiting` / `changed`) for its uncovered qty, whatever a person pressed before; a Done row
  (automatic or manual) adds nothing. The plan page's "N awaiting acknowledgement" chip and the SO
  picker's awaiting count go (nothing waits on a press any more).

## Data

- AC-AC-23 A one-time data migration: every live `awaiting` / `changed` row the rule marks done becomes
  `acknowledged` (by NULL); every person-confirmed `acknowledged` row gets the manual Confirm of
  AC-AC-17c; no PERSON-confirmed row moves from Done to To order (a system-done row, `acknowledged_by`
  NULL, is re-read by the rule like the live writer does). Checked on a dev copy before the hand test.
- AC-AC-24 The migration is idempotent: a second run changes nothing.
