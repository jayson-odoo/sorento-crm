# UAC: STANDARD-HISTORY

Plan: `PLAN-standard-history-10nov.md`.

Part A (an Unconfirm guard) was dropped by the owner on 10 Nov ~12:50; it has no criteria.

## Part B, wave 1: OI detail History tab + "All events" in the OI line dialog

Owner 10 Nov 12:41 on mock v1: approved, "just use back existing components that we had in the
system, don't invent new things". Every element below is an existing component; each swap from
mock v1 is listed in the plan.

Backend: `GET /api/v1/project-sales/order-inquiry-headers/{inquiry_id}/history`, read-only.

- AC-SH-B1: Returns `{events: [...]}` newest first. Each event: `id`, `kind`, `at`, `actor`,
  `title`, `lines` (each line: `row_id`, `so_line_no`, `item_code`, `qty`, `change`).
- AC-SH-B2: One Confirm press is ONE event (`kind = confirmed`) listing every row of THIS OI it
  touched; one Unconfirm press is ONE event (`kind = unconfirmed`), the same. A press whose
  first row belongs to another OI is still found (through `new_values.row_ids`). The title says
  the count in plain words ("Unconfirmed 9 lines"), and each line's `change` reads its prior
  state -> its new state ("Confirmed -> To confirm").
- AC-SH-B3: A batch press that also touched another OI's rows lists only THIS OI's rows; the
  other OI's item codes and row ids never appear in the response.
- AC-SH-B4: Raises (raised / reconfirmed), links (person or automatic), released links,
  rejections, row cancellations and reserve events of this OI's rows are events too, each with
  its own kind, actor (or "Automatic" for an automatic link) and lines.
- AC-SH-B5: Permission: the OI detail page's own read permission (`projects.projects.view`);
  without it, 403. Another company's OI (or an unknown id): 404, the same as the header route.
- AC-SH-B6: No IP, user agent or raw audit JSON in the response (admin extras are not in
  wave 1).
- AC-SH-B7: Owner Q3: a Confirm or Unconfirm press whose rows all belong to one OI stamps that
  OI as the audit row's root (`root_entity_type = project_order_inquiries`,
  `root_entity_id = <OI id>`). A press across several OIs keeps the old root (found through
  `row_ids`).

Frontend:

Frontend (v2, owner "ok" on mock v2 `mockups/standard-history-v2-10nov.html`, 10 Nov):

- AC-SH-B8: The OI detail page has a History tab, last, after Related SPO, with the PO detail
  page's History icon. It renders the existing `AuditTrail` card titled History: entries newest
  first, each two lines: one plain sentence, then "dd/mm/yyyy, time · by <who>" (or
  "Automatic"); seconds only where two entries share a minute.
- AC-SH-B9: At most one control: a "Search history" box, shown only when there are more than 10
  entries. It keeps a batch press as ONE entry and shows its matching lines under it. No other
  filters, no badges, no grids.
- AC-SH-B10: A multi-line entry offers "Show N lines" (then "Hide"); its lines read
  "<item>: <before> → <after>", the Audit Trail's own indented change lines. A one-line entry
  shows its line at once; an entry with no lines offers nothing.
- AC-SH-B11: Empty: "No history yet" heading + "Changes to this record appear here.", no
  button. Error: "Could not load the history" + Retry.
- AC-SH-B12: The OI line History dialog's first tab is "History": the same `AuditTrail` list,
  only the entries that touched that line's rows, each listing only that line's rows. Rows,
  Decisions and Reserve stay as they are.
- AC-SH-B13: The 8 pages already on `AuditTrail` (product, PO, complaint, ...) are unchanged.

## Wave 2: Sales Order + Fulfilment Planning (lane STANDARD-HISTORY-W2, PR #2355)

Behaviour card answered 12 Nov (crew, from owner rulings): Q1 both SO pages, Q2 anyone who can
open the SO (staff session), Q3 per-order History entry on the board opens a lightbox (admin
`PlanningHistorySheet` stays), Q4 line splits as a plain sentence, Q5 status and publish only.

Backend (one service `app/services/sales_order_history_service.py`, two reads):

- AC-SH-W2-1: `GET /project-sales/sales-orders/{pso_id}/history` (gate
  `projects.projects.view`, `require_permission`, NOT `_with_api_key`) and
  `GET /scm/sales-orders/{so_id}/history` (gate `scm.dashboard.view`, `require_permission`)
  return `{events: [...]}` in the wave 1 shape (`OrderInquiryHistoryResponse`: id, kind, at,
  actor, title, lines[{row_id, so_line_no, item_code, qty, change}]), newest first. The SCM read
  covers every project SO whose `so_id` is that SO; an SO with none returns `{events: []}`.
- AC-SH-W2-2: 404 for an unknown or malformed id and for another company's SO; an X-API-Key
  principal is refused (401/403). Read-only: the read writes no row anywhere.
- AC-SH-W2-3: Events and titles (plain words, "→" in change lines):
  - `revision_confirmed`: "Plan confirmed, revision N" (+ ", no change" when re-issued
    unchanged); one line per item (ordered / order back / cancelled). Source
    `projects.so_supply_decisions` via `planning_history_service`.
  - `confirm_refused`: "Confirm refused: <message>", e.g. "Confirm refused: 1 line cannot be
    confirmed. Nothing was written."; lines name the refused items (SRTSA-SS).
  - `autocount_update`: "AutoCount update: N lines changed"; one line per change row, change
    text from `planning_change_service.change_text`. Actor = the person who applied it; an
    unapplied batch uses its uploader.
  - `email_sent`: "Handover email sent".
  - `confirmed` / `unconfirmed` / `cancelled`: the OI presses and row cancellations of every OI
    of this SO, exactly as the OI history titles them ("Unconfirmed 4 lines, back to To
    confirm"). Each press appears ONCE even when its rows span several OIs of the SO.
  - `line_split`: "Split line N: 10 → 6 + 4" from `project_so_line_splits` audit rows rooted at
    the project SO.
  - `status_changed`: "Status: Draft → Published" (plain labels) from `project_sales_orders`
    UPDATE audit rows whose changed columns include `status`; other column changes are NOT
    events.
- AC-SH-W2-4: Actor is the person's name; no person reads null (the FE shows the wave 1
  "Automatic"). No IP, raw values, UUIDs or entity ids in titles or lines.
- AC-SH-W2-5: The shared helpers (`_ROW_AUDIT_TYPES`, the 5 s window, `_iso`) live in one
  module imported by all three services; `test_order_inquiry_history.py` and
  `test_planning_why_history.py` stay green unchanged.

Frontend:

- AC-SH-W2-6: The SCM SO detail page (`scm/sales-orders/[id]`) and the project SO page
  (`project-sales/[projectId]/sales-orders/[psoId]`) each get a History tab, last, with the
  History icon, rendering `AuditTrail` entries mode exactly as the OI tab (AC-SH-B8 to B11).
- AC-SH-W2-7: The Fulfilment Planning board's gear menu has a "History SOxxx" entry per
  planned order (beside "View splits SOxxx"), for every board user; it opens a centred dialog
  titled "History SOxxx" with that order's same list. The admin board-wide History item and
  `PlanningHistorySheet` are unchanged.
- AC-SH-W2-8: dd/mm/yyyy dates, one line per entry heading, no raw ids; usable at 375 px and
  1280 px.

Real shapes (crew, masked, 12 Nov prod copy) for tests and hand test: SO423409 5 revisions
(rev 1 28/09/2026 8 lines, rev 2 30/09 16 lines, rev 3 01/10 swaps two items, revs 1-4
superseded "Reconfirmed by CS."); SO414446 so_book_upload batch, 4 rows kind advanced item
MCM7833-CR, uploaded 27/10/2026 09:07 by the ESB integration, applied 09:30 by a CS user;
SO401624 3 CONFIRM_REFUSED 22/10/2026 15:28, 15:28, 17:25 "1 line cannot be confirmed. Nothing
was written." line SRTSA-SS; SO329258 4 Unconfirm presses 23/09/2026 each 4 rows (B2155-NL-BLUE,
C-FH14, CSA150, CKS1050).
