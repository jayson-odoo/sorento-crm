# UAC: Non-cancellable items (NON-CANCELLABLE-ITEMS)

Plan: `PLAN-non-cancellable-items-11nov.md`.

## Setting

- NC1 A series category marked Non-cancellable marks every product under it and its child
  categories; a tap in another category stays cancellable even if its name says "bathtub".
- NC2 A series product row set to No exempts that model from a marked category; set to Yes marks
  it although its category is not marked.
- NC3 A company rule (Project Sales > Non-cancellable Items) marks lines on scopes with no series,
  and lines the series says nothing about. The series' own answer beats the company rule.
- NC4 One rule per product or category per company (409 on a second); exactly one target (422).
- NC5 A set line is Non-cancellable when the series marks the set or any part is Non-cancellable.
- NC6 Changing the setting does not change saved lines until they are saved again or Recompute
  is pressed; an issued version never changes.

## Quotation

- NC7 A flagged line shows "Non-cancellable" in the REMARK column on screen, in the PDF, on the
  customer's sign page and in the Excel export.
- NC8 A scope with no flagged line prints exactly as before (no REMARK column).

## CRM gate

- NC9 Before the SO is confirmed (published), changing or removing a flagged quotation line is free.
- NC10 Once a published SO consumes a flagged quotation line, removing it, lowering its quantity,
  turning it into a heading or swapping its product is refused (409) naming the line.
- NC11 Publishing an amendment whose accepted rows reduce or cancel a flagged line is refused
  (409); declining those rows publishes normally.
- NC12 Transfer to Cancel SO of a flagged line on the board is refused (409); a line AutoCount
  already cancelled is not.
- NC13 A user with `projects.non_cancellable.override` (superadmin, admin, director,
  project_sales_manager) can override with a reason; the override is in the audit log with the
  reason. A reason from a user without the permission is refused (403).

## AutoCount alert

- NC14 A qty cut or cancel of a flagged line arriving from AutoCount notifies every override
  holder (bell + email) once per line and quantity; the change row carries
  `facts.non_cancellable`.
- NC15 Delivery (settled lines) and increases raise nothing.
