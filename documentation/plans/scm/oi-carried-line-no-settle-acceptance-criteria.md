# UAC: a carried line never settles or redirects its row on reconfirm

Plan: `PLAN-oi-carried-line-no-settle.md`. Issue #1226. Owner ruling 25 Sep 2026.

Vocabulary: a CARRIED line is one the confirmation did not name (`entry["carried"]` true in
`refresh_for_decision`); its snapshot is the previous revision's, verbatim. A DRAFT row is a
placed or partly linked ORDER / ORDER_BACK row whose links are all cascade-made
(`_cascade_only`).

- AC-CL-1 [BE][T] Given a carried line whose only live row is a PLACED draft linked to a
  fully received PO line (`line_status = 'closed'`, `qty_received >= qty_ordered`), and the
  own-arrival credit for the row is 0, when a sibling line of the same order is reconfirmed,
  then the row is still `placed`, `redirected_to_pool` is false, its `note` is unchanged,
  and the line has no second ORDER row.
- AC-CL-2 [BE][T] Same as AC-CL-1: no handover record of any kind is written for the
  carried line's row by that reconfirm.
- AC-CL-3 [BE][T] Given a carried line whose only live row is a PARTLY_LINKED draft (qty 5,
  3 linked), when a sibling line is reconfirmed, then the row keeps qty 5, its state and its
  note; no "Remainder superseded" note is appended and no remainder ORDER row is raised.
- AC-CL-4 [BE][T] Given a NAMED line whose only live row is a PLACED draft linked to a fully
  received PO line, credit 0, when that line is reconfirmed, then today's redirect still
  happens: the row reads `redirected_to_pool` true and a fresh ORDER row carries
  `previous_qty` / `previous_delivery_date` (AC-OH-40 unchanged).
- AC-CL-5 [BE][T] Given a carried line whose only live row is still `raised` (no links),
  when a sibling line is reconfirmed, then today's behaviour stands: the row is cancelled
  "Superseded by revision N" and re-raised under the new revision with the handshake
  inherited (no `changed` promotion).
- AC-CL-6 [BE] A planning change that names a line still settles it in place and may
  still redirect a received link; a settled line is always named, so a carried line
  never reaches that path.
- AC-CL-7 [BE][T] AC-OH-41 and `tests/scm/test_confirm_local_buy_no_oi.py::
  test_carried_local_line_skipped` stay green.
- AC-CL-8 [DoD] No migration, no frontend change; service diff under 100 lines (tests
  excluded); PR body names the small fix track, states the measured counts, and states
  that `security-reviewer` was not run (no auth, RBAC, ingest, upload or multi-company
  change).
