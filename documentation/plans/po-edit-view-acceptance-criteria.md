# UAC - Customer PO edit view

**Slug:** po-edit-view. **Plan:** `PLAN-po-edit-view.md`. **Parent:** `PLAN-quotation-edit-view.md`
(the same complaint, answered the same way, on the other document).

## Journey

**Actor:** the project sales admin who owns the PO.

They arrive at a PO either from the POs tab of a project (clicking the row, or its Edit pencil)
or from the readiness step that told them to check it. **What the system already knows:** the PO
number, the date, who issued it, the quoted version it answers, and every line - either keyed in
or read off the uploaded scan and confirmed. Nothing on that list is asked for again.

1. **They read the PO.** One page: the facts about the document, the scans behind it, and the
   lines. Nothing on it can be typed into, so nothing can be changed by accident.
2. **They press Edit** (gear, or the pencil in the list, which lands them here already editing).
   Every value they were just reading becomes an input **where it was** - same fields, same order.
   The lines become a spreadsheet: type across, Tab to the next cell, "Add a line" for one more,
   the bin to mark one for removal (struck through, restorable).
3. **They press Save once.** The header and the whole line set go in ONE request. If the save
   would delete lines, they are asked once, naming the count.
4. **They hold** a corrected PO, its total recomputed, its lines re-checked against the quoted
   version. Cancel at any point leaves the server exactly as it was.

## AC

### Read (FE)

- **AC-P1 [FE]** Given a PO with lines, when its page is opened, then every header field the PO
  owns (number, date, source, issuer, bound version, amount, notes) is READ on the page, and no
  input, add row, per-row tick or per-row delete exists anywhere on it.
- **AC-P2 [FE]** Given the PO detail page, then read-only metadata (last updated) is in the page
  header, never inside a section that has an edit counterpart.
- **AC-P3 [FE]** Given a PO with no lines, then the Lines section still renders its header plus an
  empty state that names the next step ("Press Edit ..."), and a reader (no edit right) is told
  the PO was recorded as a single amount instead.
- **AC-P4 [FE]** Given a user without edit rights, then every section still renders, and the page
  says they can read but not change it.

### Edit (FE)

- **AC-P5 [FE]** Given the read view, when Edit is chosen from the gear, then each value becomes an
  input in place: same fields, same order, nothing added, moved or hidden.
- **AC-P6 [FE]** Given the PO list, when the row's Edit pencil is pressed, then the PO's own page
  opens already in edit mode (`?edit=1`). There is no second modal that edits the same fields.
- **AC-P7 [FE]** Given an open session, when nothing has been changed, then Save is disabled and
  says why.
- **AC-P8 [FE]** Given an open session, when a quantity or price is typed, then the row total, the
  table footer and the header's "Lines total" all move at once, and NO request is made.
- **AC-P9 [FE]** Given an open session, when a line's bin is pressed, then the row stays on screen
  struck through and marked "Removed on save", nothing is asked, nothing is deleted, and it can be
  restored.
- **AC-P10 [FE]** Given a session with a header edit and line edits, when Save is pressed, then
  exactly ONE `PUT` carries the changed header fields and the FULL line set in display order.
- **AC-P11 [FE]** Given a session where only the header changed, when Save is pressed, then the
  request carries NO `lines` key (a whole-set write of untouched rows is a rewrite, not a no-op).
- **AC-P12 [FE]** Given a session whose save would delete stored lines, when Save is pressed, then
  one confirmation naming the count is shown first, and nothing is written until it is confirmed.
- **AC-P13 [FE]** Given a session with a line naming neither a product nor a code, when Save is
  pressed, then the cell is already marked, the refusal says how many lines are unfinished, and no
  request is made. Same for an emptied PO number.
- **AC-P14 [FE]** Given a session, when Cancel is pressed, then every value reads what the server
  holds and no request was made.
- **AC-P15 [FE]** Given a PO with published sales orders, when the session opens, then the page
  states how many already went out and that changing the PO does not change them.
- **AC-P16 [FE]** Both views are usable and non-clipped at 375px and 1280px.

### Save (BE)

- **AC-P17 [BE]** `PUT /api/v1/project-sales/purchase-orders/{po_id}` accepts the header fields
  plus an optional `lines` array and applies both in ONE transaction.
- **AC-P18 [BE]** `lines` absent leaves the stored lines untouched (the record-a-PO modal's shape).
  `lines: []` clears them.
- **AC-P19 [BE]** `lines` present is a REPLACE: an item with `id` updates that line, an item
  without one is created, and a stored line whose id is absent is deleted. `sort_order` is array
  position; any sent value is ignored.
- **AC-P20 [BE]** A re-bound `quotation_version_id` is applied BEFORE the lines are written, so
  every line's mismatch flags answer for the new binding.
- **AC-P21 [BE]** Refusals: a line with neither product nor code -> 422 `po_line_identity_required`;
  the same id twice -> 422 `po_line_duplicate`; an id belonging to another PO -> 404
  `po_line_not_found`. Any of them rolls the whole save back - neither header nor lines move.
- **AC-P22 [BE]** A mismatch against the quoted version is still FLAGGED, never refused (AC-F9),
  and a whole-set save raises ONE mismatch notification, not one per line.
- **AC-P23 [BE]** A caller without `projects.projects.edit` gets 403 and nothing is written.
- **AC-P24 [BE]** The PO list reports `published_sales_order_count` (published or amended SOs built
  from that PO), which is what AC-P15 states.

### Tests

- **AC-P25 [T]** pytest covers AC-P17 to AC-P24: happy path, header-only, empty array, rebinding,
  each refusal, auth denial, and the count.
- **AC-P26 [T]** vitest covers AC-P1 to AC-P14: loading / error / empty / read / reader states, the
  staged line edit-add-remove contract, one save with the full payload, header-only save, both
  refusals, and Cancel.
- **AC-P27 [E2E]** No new Playwright spec (standing order). An agent-browser evidence run stands in
  and is recorded in the plan.
