# Order inquiries: confirm per SO, To confirm default, remembered sort + filters - acceptance criteria

Status: agreed (owner rulings R1-R3 in Lavish 17 Sep 2026)
Plan: `PLAN-oi-confirm-per-so.md`

## Journey

Purchasing opens Order Inquiries. Rows that came in from the Excel are already confirmed; rows raised from Fulfilment Planning are theirs to confirm. The page opens on To confirm: every row CS has raised
that purchasing has not yet signed off. The cascade has already linked what it could to
open PO and SPO lines. They search one SO, look at each line, move a link where the
cascade picked wrong (Unlink selected, Link selected, Choose document), place the rest in
AutoCount, and Upload purchase orders brings that linkage back. When every line reads
right they tick lines one by one, or tick the header and take Select all N, and press
Confirm (N). The SO leaves To confirm.
Reorder planning now counts those lines; it never counted them before the press.

CS later changes a confirmed line. The row comes back on To confirm marked Changed with
Was/Now. Purchasing confirms it again.

Next visit, the grid opens with the sort and filters they left it on. Page number and
search text start fresh.

## Criteria

Handshake
- AC-CF-1 A row raised by a board confirm is born `awaiting`; `acknowledged_by/at` null.
- AC-CF-2 A row carried unchanged by a re-confirm keeps its prior ack fields.
- AC-CF-3 A confirmed row whose qty or date CS changes becomes `changed`, `changed_at` set,
  `acknowledged_*` kept; it is NOT re-acknowledged.
- AC-CF-4 The cascade still auto-links awaiting rows on raise; Link selected, Auto link
  all, Choose document and Unlink all work on an awaiting row.

Confirm
- AC-CF-5 The page's primary button reads "Confirm (N)"; N = ticked rows in awaiting |
  changed and not cancelled; disabled at 0 with the reason as its title; a press opens a
  confirm dialog stating the count, like the fulfilment board's Confirm (N). "Upload
  purchase orders" sits in the Actions menu.
- AC-CF-6 Line by line = tick one row and press Confirm (1). The worklist has no per-row
  menu (R8 of the parity lane) and this lane adds none; superseded by AC-CF-5.
- AC-CF-7 After a page tick, the "Select all N records" banner appears; Confirm then
  confirms every eligible row matching the current filters (all pages), not the page only.
- AC-CF-8 `POST /order-inquiries/acknowledge` accepts `row_ids` OR `filter`, never both
  (422); `filter` reuses the list's own parameters; rejected + cancelled rows skipped and
  reported in the result counts.
- AC-CF-9 A principal without `projects.order_inquiries.acknowledge` (CS) sees no Confirm
  and gets 403 on the endpoint.
- AC-CF-10 Confirm toasts "Confirmed N rows"; list and summary refetch; confirmed rows leave
  the To confirm view without a reload.

Default view
- AC-CF-11 No `?ack` in the URL = To confirm rows only (awaiting + changed); `?ack=all` =
  every row; the four state values unchanged.
- AC-CF-12 Stat tile "To confirm N" reads `summary.ack.to_confirm`; clicking it sets the
  filter; N drops after a confirm.
- AC-CF-13 Filter labels: To confirm, Confirmed, Changed, Rejected, All.

Planning
- AC-CF-14 An awaiting row is absent from reorder planning demand (`horizon_committed`)
  and from a plan run; confirming it puts it in; a changed row stays in.
- AC-CF-15 The plan page awaiting count matches the To confirm tile.

Deploy (R1)
- AC-CF-16 At migration, open rows raised from fulfilment planning (`supply_decision_id`
  set, acknowledged, not cancelled / actioned) become awaiting; rows from the Excel
  importer (no decision) keep acknowledged. Downgrade restores the flipped set.

Remembered view
- AC-CF-17 Sort survives a reload and a new tab, per user, through
  `/list-query/column-config/projects.projects.view::order-inquiry-worklist`.
- AC-CF-18 Every filter survives a reload: ack, view, granularity, delivery month,
  location, agent, SO month, PO number, SPO number, supplier, project, raised date, raised
  by, linked, kind, link up to, link horizon.
- AC-CF-19 Page number and search text are NOT remembered.
- AC-CF-20 A URL parameter present on arrival wins for that visit and becomes the memory;
  an absent one falls back to the memory, then the default.
- AC-CF-21 The first data fetch waits for the memory (no flash of the default view).

Layout
- AC-CF-22 Usable, nothing clipped, at 375px and 1280px; Actions menu and banner reachable
  on mobile.

## Evidence

Browser run on the lane stack, agent-browser via sidebar: screenshots for AC-CF-5, 7, 10,
12, 17-19 under `documentation/plans/scm/evidence/oi-confirm-per-so/`.
