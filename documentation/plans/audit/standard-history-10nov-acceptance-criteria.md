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
