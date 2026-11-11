# PLAN: Non-cancellable items (NON-CANCELLABLE-ITEMS)

Status: Build (track: standard M; one additive migration, one new permission). UAC:
`non-cancellable-items-11nov-acceptance-criteria.md`.

## Journey

Owner, project sales meeting 11 Nov 2026: bulky items such as bathtubs are non-cancellable
("sorento cannot afford to store these bulky items"). Sales must see it on the quotation, the
CRM must stop a cancel or reduction after the order is confirmed unless a manager overrides with a
reason, and a cancel made straight in AutoCount must raise an alert.

## Owner answers (card, 11 Nov ~16:40 and ~16:55)

- Setting on the project series, plus a company-wide default by category / model; the series
  wins (a). Model beats category.
- No terms sentence: "say Non cancellable at the remark" (b). A REMARK column on screen and in
  the PDF.
- Override: new permission, sales manager + director (admin always), reason required, audited;
  the same role gets the AutoCount alert (c).

## Design

### Setting (where it lives)

| Level | Storage | Values |
| --- | --- | --- |
| Series category | `projects.series_categories.non_cancellable` | true / false; a parent covers its children |
| Series model | `projects.series_products.non_cancellable` | null (follow category) / true / false |
| Series set | `projects.series_sets.non_cancellable` | true / false |
| Company product | `projects.non_cancellable_rules` (product_id) | true / false |
| Company category | `projects.non_cancellable_rules` (category_id) | true / false, nearest ancestor wins |

Precedence, first answer wins: series model row, series category, company product, company
category. A set line is non-cancellable when the series marks the set or ANY frozen part is
non-cancellable.

### Line flag

`projects.quotation_lines.is_non_cancellable`, computed in `_apply_guardrails` on every line save
and on Recompute, STORED (same rule as `is_non_standard`): a later setting change never rewrites
an issued quotation. Copied on revision (`copy_line`).

### Quotation (screen, PDF, sign page, Excel)

`quotation_columns.REMARK` ("REMARK") sits before GRAND TOTAL and appears only on a scope with a
non-cancellable line; the cell reads "Non-cancellable". Line notes are not printed (they never
were; some are internal). The screen shows the remark beside the line's own notes.

### CRM gate (after confirmation)

`non_cancellable_service.assert_may_reduce`: 409 `non_cancellable_line` (details `can_override`,
`lines`), 403 `non_cancellable_override_forbidden` when a reason comes from a user without
`projects.non_cancellable.override`; with permission + reason one audit EVENT row
`non_cancellable_override` per line. Called from:

- Publish amendment (`POST /amendments/{id}/publish`, body `non_cancellable_override_reason`):
  accepted rows whose qty verb (CANCEL BALANCE / ORDER / RESERVE & ORDER) lowers the line.
  Amendment rows carry `non_cancellable` for the screen. Declining the row is the other way out.
- Board Transfer to Cancel SO (`cancelled_lines[].non_cancellable_override_reason`); a line
  AutoCount already cancelled (`awaits_cancel_so`) is not refused.
- Remove a line from a WON quotation scope (`DELETE .../lines/{id}?non_cancellable_override_reason=`).

SO lines read the flag through `quotation_line_id`; an adopted line with no quotation line is
not protected (no series answer exists for it).

### AutoCount alert

`alert_autocount_reductions` notifies (in-app + email, deduped per line and quantity) every
holder of the override permission when:

- `planning_change_service.build_batch` sees a qty cut / removal on a flagged line (SO book
  upload, ESB ingest, partial Cancel SO via `_raise_planning_change`); the change row's
  `facts.non_cancellable` is set;
- `run_cancel_hooks` sees a flagged line fully cancelled by a Cancel SO.

Delivered / settled lines (`CLOSED`) are never alerted.

## Not in scope

- Blocking AutoCount itself (it owns SO cancels).
- Quantity reduction by editing a line on a won quotation (only removal is gated; editing a won
  scope opens a revision).
