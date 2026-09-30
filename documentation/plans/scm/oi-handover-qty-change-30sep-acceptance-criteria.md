# UAC: OI handover email line quantity changes + wide shell (EMAIL-HANDOVER-QTY, PR #1392)

Plan: `PLAN-oi-handover-qty-change-30sep.md`. Built toward the three recommendations
asked on the PR; a different owner pick reworks only that part.

Line totals (planning-change apply, settle in place declined):

- AC-1 Given a line whose lone placed row (no link) is 5 on WAS and the book moves it to
  8 on NOW (earlier), then the email prints ONE line for it: QTY 5, QTY CHANGE TO 8,
  DELIVERY DATE WAS, DELIVERY DATE CHANGE TO NOW, REMARK `ADVANCE, ORDER 3`; the
  headline verbs include ADVANCE and ORDER; no separate `ORDER` line is printed for the
  line. The worklist still holds the placed row (5, dated NOW) and the fresh ORDER 3 row.
- AC-2 Same shape, book moves 5 to 3: ONE line, QTY 5, QTY CHANGE TO 3, REMARK
  `ADVANCE, CANCEL BALANCE 2 NOS`; the CANCEL BALANCE exception row is written but not
  printed as its own line.
- AC-3 Same shape, quantity only (5 to 8, date unchanged): ONE line with `was = {qty: 5}`
  and no `delivery_date` key, QTY CHANGE TO 8, REMARK `ORDER 3`, no DELIVERY DATE CHANGE
  TO in the email.
- AC-4 Two live raised rows (10 + 3) on WAS, book moves the line to 8 on NOW: ONE line,
  QTY 13, QTY CHANGE TO 8, REMARK `ADVANCE, CANCEL BALANCE 5 NOS`; neither superseded row
  prints a `CANCEL BALANCE` line of its own and the fresh ORDER 8 row prints no line of
  its own.
- AC-5 Pure date move (total unchanged): unchanged from today, ONE line with
  `was = {delivery_date}` only and no `qty` key.
- AC-6 A line with no live buy row (fresh): unchanged, a plain `ORDER` line with no `was`.
- AC-7 `handover_remark("settled", row, was, qty=)` and `_handover_settle_diff` read the
  difference off the given `qty` when one is passed and off `row.qty` otherwise; the
  existing remark table keeps passing unchanged.
- AC-7a (review round 1) A line the netting redirects to the pool in the same apply
  prints today's per-row lines (date-only settle, superseded rows, the fresh row with its
  "Replaces N used" remark) and never a totals line.
- AC-7b (review round 1) A raised row purchasing refused is left out of QTY: placed 10 +
  refused 3, book to 15, prints 10 -> 15, ORDER 5, the fresh row's own quantity.
- AC-7c (review round 1) A line marked Order back keeps today's lines (documented, one
  guard term, no seam reaches it through the planning-change apply).

Wide shell:

- AC-8 `EmailDocument` accepts `width: "standard" | "wide"`, defaults to standard; any
  other value is rejected; a stored document without the key parses as standard.
- AC-9 A wide document renders the card at `width="900"` / `max-width:900px`, side padding
  24px on the content cells, and the phone breakpoint at 920px; a standard document still
  renders exactly today's 600 / 40px / 620px.
- AC-10 The plain safe layout (fallback) is unchanged (standard).

Handover template migration `oihr_0004_wide_line_table`:

- AC-11 Upgrade on a database carrying the real seed chain (212 to soatt_0001, eml_0002)
  sets `layout_json.width = "wide"`, keeps the block order (brand header, heading,
  custom text, button, footer), the custom text carries per-column widths and
  `white-space:nowrap` on every line cell but REMARK, `body_html` equals the mirror of the
  custom text blocks, `body_text` is untouched. Running it twice gives the same row.
- AC-12 Upgrade on a database with no handover row inserts one in the new shape; downgrade
  restores `layout_json` and `body_html` byte for byte to what they were before.
- AC-12a (review round 1) A document an admin arranged since eml_0002, or a row eml_0002
  left with NULL `layout_json`, is left untouched by upgrade and by downgrade, and the
  skip is logged. The seeded document re-saved unchanged by the editor (which adds
  `width: "standard"`) is still converted.
- AC-7d (review round 1) A refused raised row alone never produces a totals line whose
  before equals its after: placed 5 + refused 3, book keeps 5, prints today's date-only
  line.
- AC-13 The migrated template renders through `EmailTemplateService.render` at 900px
  with the settled line `172 -> 436` printing cells in the order SO DATE, S/O NO,
  LOCATION, ITEM CODE, QTY, QTY CHANGE TO, DELIVERY DATE, DELIVERY DATE CHANGE TO,
  REMARK, and the plain text part still starts its table with `SO DATE | S/O NO`.

Frontend:

- AC-14 The template editor keeps a saved `layout_json.width` on Save and on the draft
  preview payload, and a Width select (Standard / Wide) changes it; a template without
  the key saves `standard`.

Housekeeping:

- AC-15 Single alembic head after `./scripts/alembic-reparent.sh`; revision id at most
  32 characters; no em-dash or en-dash anywhere in the diff; existing handover, layout
  and migration tests keep passing, none deleted.
