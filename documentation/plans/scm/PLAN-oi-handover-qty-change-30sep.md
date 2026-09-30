# PLAN: OI handover email shows line quantity changes and stops cramping the table (EMAIL-HANDOVER-QTY)

Status: built, on hand test (feature track, abbreviated per the crew brief: alignment mock, owner ruling 30 Sep recorded on the mock, red tests, one PR #1392; carries one data migration so it is not the small fix track). Hand test: `laneboard/scripts/1392.md`.
Lane: EMAIL-HANDOVER-QTY, PR #1392, branch `claude/email-handover-qty-n1okn0`
Domain: scm (order inquiry handover email, `order_inquiry_handover` automation) + email layout shell
UAC: `oi-handover-qty-change-30sep-acceptance-criteria.md` alongside
Mock: `ALIGN-oi-handover-qty-change-30sep.html` alongside (before / after on the real shell markup)

## Problem (owner, 30 Sep)

On the "ORDER, ORDER BACK, ADVANCE" email for SO402757 / SRTWT6808 the owner asked:
"will we show qty change in an additional column? i think this email template is too
narrow already, the words are cramped". Planning moved the line to a Buy of 436, required
25/09/2026 (OI-2609-0678); the email printed ADVANCE 172 (01/10 to 25/09) + ORDER 64 +
ORDER BACK 16 and nowhere said the line's quantity had changed.

## Measured (origin/main e26410c2, `sorento_crm_backend/`)

- QTY on a handover line is ONE order inquiry row's `qty`, never the line's total
  (`_record_handover`, `app/services/project_order_inquiry_service.py:3273`).
- A quantity change reaches the email on ONE path only: `_settle_row_in_place` sets
  `row.qty = need` and records `was = {qty, delivery_date}` (lines 1783, 1824 to 1829),
  which the template prints as QTY (old) + QTY CHANGE TO (new).
- The owner's case is a planning-change apply (`planning_change_service.apply` names the
  line in `settle_in_place_line_ids`, line 4382). `_settle_row_in_place` declined (a lone
  placed row with no link row, or two live rows), so `_write` took the
  `asked_to_settle` fallback (lines 1224 to 1253): `_stamp_date_move` stamped the new
  date on the existing row(s) and recorded ONE settled line with
  `was = {delivery_date}` only (lines 1960 to 1965); the netting loop then raised the
  remainder `need - placed` as a separate ORDER row (lines 1341 to 1349, `kind="raised"`).
  The 436 never reaches the email.
- The live handover template renders through its `layout_json` block document seeded by
  `alembic/versions/eml_0002_seed_layouts.py` (brand header, heading, custom_text with the
  two tables, button, footer). The shell is `app/templates/email/base.html` (600px card,
  line 31) + `layout.html` (40px side padding, line 66): nine columns share about 520px.
  The old `body_html` (`oihr_0003_location_column.py` + `soatt_0001`'s attachment
  fragment) is only the mirror the list and search read (`_mirror_body_html`, #1349 D3).
- Test harness: `tests/scm/test_oi_date_move_settle.py::_apply_date_move` drives exactly
  the owner's seam (book change, batch, confirm row, apply); `_captured_dispatches` in
  `tests/test_order_inquiry_handover_automation.py` reads the dispatched context.

## Rulings (owner, 30 Sep, on the mock)

- Q1 row model: "i thought it should be as straight forward as what's the before OI qty, and
  what's the after OI qty, then show it?" = (a): one line per OI line, QTY = the line's
  quantity before this handover (its live rows added up), QTY CHANGE TO = after, no separate
  ORDER remainder line for the same line. The remark keeps today's wording for the difference.
- Q2 width: "ok" = (a), the wide shell, chosen per template.
- Q3: "column" = keep DELIVERY DATE CHANGE TO as a column.

## Design (simplest thing that works)

### S1 Line totals on the declined-settle path (backend, no schema change)

In `_write`'s `asked_to_settle` branch the line's live buy rows and their total
(`live_buy_qty`) are already computed. When that total differs from `need` and the line
has at least one live row, the line's total moved, and the email is told ONCE, in the
same shape `_settle_row_in_place` already prints:

1. `_stamp_date_move` gains `line_total` / `previous_total`: when given, the ONE settled
   line it records carries `was = {delivery_date: old, qty: previous_total}` and prints
   `qty = line_total`. When the date did not move (nothing to stamp) but the total did,
   `_write` records the same settled line itself off a representative live row (a
   non-raised one first, the netting cancels raised rows).
2. `_record_handover` gains `qty: Optional[Decimal]` (the line total to print instead of
   `row.qty`); `_handover_settle_diff`, `handover_remark` and `_handover_verb_keys` take
   the same optional `qty` so the remark and the headline verbs read the difference
   between the totals (`ORDER n` / `CANCEL BALANCE n NOS`), exactly as a settle does.
3. For that line the netting loop's own handover calls are skipped: the superseded raised
   rows (`kind="cancelled"`), the remainder ORDER row (`kind="raised"`) and the
   CANCEL_BALANCE exception row (`kind="raised"`) are still WRITTEN (worklist unchanged),
   just not printed as their own email lines. The totals line itself is recorded AFTER
   the netting loop (the date move defers its representative and previous date to
   `_write`), so the loop can change its mind:
   - a row the netting REDIRECTS to the pool (received link, no own-arrival credit)
     leaves the line's "before", and the fresh row is `need - placed`, not `need -
     held`; that line falls back to today's per-row lines (date-only settle, each
     superseded row, the fresh row with its own "Replaces N used" remark). Review
     round 1, blocking 1.
   - "what purchasing held" leaves out a raised row purchasing refused (ACK_REJECTED):
     the fresh row is `need - placed` and a refused row is never placed, so the
     difference then equals the row raised. Review round 1, should-fix 4.
   - a line marked Order back keeps today's per-row lines entirely: its remainder
     names the cited document, which a totals line has no cell for, and a totals
     remark saying `ORDER n` beside an `ORDER BACK n` line would read as twice the
     quantity. Review round 1, should-fix 2. No seam can drive an order-back line
     through the planning-change apply today (the composition carries no order_back),
     so this is a one-term guard, documented, not end-to-end tested.
4. Everything else is unchanged: pure date move (total equal) prints as today; a fresh
   line with no live row prints a plain raise; `_settle_row_in_place`'s own path is
   untouched; amendment / book-change rows, subject, headline order, sorting.

### S2 Wide shell variant (email layout)

- `EmailDocument.width: Literal["standard", "wide"] = "standard"` (one field on the
  document; a legacy document without it is standard). `render_document` passes it to
  `_layout`; `base.html` renders the card at 600 or 900 with the phone breakpoint at
  620 or 920; `layout.html`'s side padding is 40 (standard) or 24 (wide).
- Frontend: `EmailLayoutDocument.width?`, the template editor keeps the saved width in its
  draft, sends it on save and on the draft preview, and offers Width (Standard / Wide)
  as a `SearchableSelect`. No other screen changes.
- Trigger for a third width: none today; two named widths are the whole surface.

### S3 Handover template ships wide (data migration `oihr_0004_wide_line_table`)

Updates `email_templates.code = 'order_inquiry_handover_default'` IN PLACE, but only
while its `layout_json` is still the document eml_0002 seeded (eml_0002's own guard;
review round 1, should-fix 3: the template has been admin-editable since #1349, so an
admin's arrangement, or a row eml_0002 left NULL because its body was edited, is left
alone by both directions, and the skip is logged; the seeded document re-saved unchanged
by the editor, which adds `width: "standard"`, still converts): `layout_json` = the
eml_0002 document with `width: "wide"` and the
custom_text block's line table carrying per-column widths, `white-space:nowrap` on every
cell but REMARK, and the tighter 6px 8px cell padding; `body_html` = the mirror of the
custom_text blocks (D3); `body_text` untouched (the hand-tuned pipe table). A DB with no
row gets one inserted in the new shape. Idempotent. Downgrade restores the eml_0002
document and the pre-migration `body_html` byte for byte (frozen copies in the file).

## Tests (red first)

- `tests/scm/test_oi_handover_line_total.py`: AC-1 to AC-7 through `_apply_date_move`
  and `_captured_dispatches`; pure-function table for `handover_remark(..., qty=)`.
- `tests/test_email_layout.py`: AC-8 to AC-10 (wide render, default, legacy parse).
- `tests/test_oi_handover_wide_migration.py`: AC-11 to AC-13 (replay the real seed chain,
  upgrade in place, idempotent, insert when absent, downgrade byte for byte, render).
- Frontend vitest `[id]/page.test.tsx`: AC-14 (width round-trips through save).

## Hand test

`laneboard/scripts/1392.md` (posted as crew-handtest on the PR): trigger a planning
change on the crew test copy, read the email in System Management > Email Outbox.
