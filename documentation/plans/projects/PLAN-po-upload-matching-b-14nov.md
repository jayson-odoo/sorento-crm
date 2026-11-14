# PLAN: PO upload matching B (PO-UPLOAD-MATCHING B)

Status: building (small fix track, size S: no migration, no auth/RBAC change). Follow-up to #2409,
owner 14 Nov ~18:19: "need a follow up PR for me to bulk cancel the lines instead of 1 by 1";
crew decision on line 46.

## 1. Bulk cancel of PO lines (To confirm screen)

- Lines grid gets the shared tick column (`components/ui/data-grid-select-column.tsx`
  `buildSelectColumn`, with its shift-click range); the header box ticks the shown lines.
- Rows first, then ONE action: with lines ticked, the lines toolbar shows "Cancel lines (N)"
  (and "Put back (N)" when ticked lines are cancelled). Right-click keeps the single-line actions.
- Same function as the single cancel: each ticked line goes through the existing line update
  with `{ is_cancelled: true }` (or `false` to put back), one request per line, in order.
  One bad line never stops the rest; one summary toast names the count done and each line
  that was skipped with its reason.
- Cancelled lines stay on the record; "Put back" (single or bulk) reverses it, as today.

## 2. Line 46: exact code with a variant sibling is not settled

Evidence (#2409 crew passes): "SORENTO BBTSRTWB243", description "WALL HUNG BASIN 35MM", came
back resolved with no pill on a first read with no remembered codes, so it was placed by the
exact-code step (`project_po_intake_lifecycle.py` `_resolve_product`), never by the model.
Crew decision: it must come back Suggested with both SRTWB243 and SRTWB243-35MM offered.

Rule: an exact catalogue code is settled only when no other product of the same company has
that code plus a variant suffix (`<code>-<suffix>`) whose suffix the line's description names.
Otherwise the line goes to the model with the bare code and those siblings among its
candidates; the prompt's variant guidance makes it offer both. The code only decides whether to
ask the model; the model judges.

## Reuse

`buildSelectColumn` / `rangeSelectProps`, the grid's existing `commit` (single-line update),
`customer_code_map`, `project_po_matching.suggest_matches`.

## Standing rules that apply

Bulk actions rows-first with one action; ticking (shift range, header box); one bad line never
fails the batch, named in a clear notice; plain words; no new row icon buttons; 375/1280 px.
