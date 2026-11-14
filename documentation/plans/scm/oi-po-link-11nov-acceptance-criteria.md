# UAC: OI-PO-LINK (Order Inquiry lines link to PO lines with the shared Stock Debt link function)

Plan: `PLAN-oi-po-link-11nov.md`. Every AC is checked against a fake Shared Service in tests (db3 only for the
real AutoCount run, done by lane AC-E2E-DB3).

## Shared function
- AC-1 One service (`app/services/scm/po_link_service.py`) performs link / unlink / change / relink for both screens;
  Stock Debt and Order Inquiry routes call it with their own scope. No second copy of validation, idempotency or
  read-back code.
- AC-2 Stock Debt behaviour unchanged: every existing Stock Debt po-link test passes with no assertion edit
  (`tests/scm/test_stock_debt_po_link*.py`, `test_stock_debt_snapshot_live_cover.py`, FE `PoLinkDialog.test.tsx`,
  `poLinkWording.test.ts`, moved path only).
- AC-3 Link lines are grouped by PO line; each group is sent through one send point (`_send_group`), groups in
  the order of their first line in the request, lines within a group in request order (review S2: grouping is
  what the SS batch op needs, so a request po1, po2, po1 sends po1, po1, po2). Results are answered in request
  order. Until the SS batch op exists the group sends the existing per-line write for each member with the same
  body and the same idempotency key as before this lane (the key's `rowQty` stays the stored 4-decimal form, so an
  operation left unknown before a deploy replays after it, review B2).
- AC-3a Every SS write call (link, unlink, change halves, relink, relocate, resume) carries `X-Request-ID`,
  `X-Acting-User-Id` (the CRM user id) and `X-Acting-User-Name` (the user's display name, percent-encoded with
  `urllib.parse.quote(name, safe="")`), one request id per press, from both screens (AC-DB1-READY, SS plan 63).
- AC-3b Every SS write the CRM makes writes one audit EVENT `scm.po_line.crm_link_write` on the PO line, with the
  pressing user as actor and `request_id`, `operation_id`, action, outcome, SO number + line and qty in
  `new_values`, rolled up to the PO header.

## Order Inquiry scope
- AC-4 `POST /api/v1/project-sales/order-inquiries/po-link/options` with `row_ids` answers the same shape as Stock
  Debt's options (capabilities, open PO lines of the product with free qty, `so_books`) plus `lines`: one per
  distinct AutoCount SO line of the ticked rows (`sales_order_line_id`, `so_number`, `line_no`, `open_qty`,
  `po_links`).
- AC-5 Ticked rows of more than one product: 422 "Tick rows of one product." Rows with no AutoCount SO line are left
  out of `lines` and named in `skipped` (OI number + item code) with "Not in AutoCount yet"; if none are left, 422.
- AC-6 `.../po-link/link` with `row_ids` + `lines` links exactly like Stock Debt: refused with nothing sent for a SO
  line not among the ticked rows' SO lines, an already linked PO line, another book, more than still needed, more
  than free (summed over the request). A qty below the PO row qty sends the split body.
- AC-7 After any result with outcome `done`, the ticked OI rows' AutoCount book step re-runs in the same request
  (the `auto-place` `row_ids` path), so the worklist row's PO column names the PO on the next read.
- AC-8 Refusal retry: a definite refusal answers `refused` with AutoCount's reason; pressing again sends a new
  attempt (new idempotency key). An unknown outcome keeps the key, so the retry replays the stored answer.
- AC-9 `.../po-link/unlink` and `.../po-link/change` behave as Stock Debt's (unlink first in change; a failed link
  after unlink answers `unlinked_po`).
- AC-10 Switch OFF -> 403 with the switch message, nothing sent. Without `projects.stock_debt.link_po` -> 403.
- AC-11 Every write is logged in PO link history (`po_link_history.py`), as Stock Debt's are.

## Screen
- AC-12 OI Actions menu (rows-first) has "Link to PO... (n)", "Change PO... (n)", "Unlink from PO... (n)" counting
  eligible ticked rows ("2 of 3" when some are not), greyed with the reason; hidden entirely when the switch is OFF
  or the user lacks the grant (the screen looks as before, apart from the two renames below).
- AC-13 Right-click on a row offers the same three items for that row.
- AC-14 The popup is the shared dialog: same columns, same defaults (qty = still needed, capped at free), same result
  wording, Move location / Resume buttons.
- AC-15 "Link selected" reads "Recheck in AutoCount"; "Unlink selected" reads "Remove link in CRM"; behaviour
  unchanged.
- AC-16 Usable at 375 px and 1280 px; one line per row in the popup grid; no ids shown.

## Owner hand test round (14 Nov, head 5cfcc2776)
Supersedes AC-5's one-product refusal for Order Inquiry (owner, 14 Nov: "why i cannot link two different products
together"; standing rule 12 Nov: a multi action is the same function as the single one).
- AC-HT1-a `.../po-link/options` with ticked OI rows of two or more products answers 200: `lines` has one entry per
  AutoCount SO line of every product; `po_lines` holds the open PO lines (free qty > 0) of every ticked product, each
  carrying its `product_id`; `so_products` maps each `sales_order_line_id` to its product id (like `so_books`).
- AC-HT1-b `.../po-link/link` (and `/change`) with lines of two products links each SO line to a PO line of ITS OWN
  product in one request. A PO line whose product differs from its SO line's product is refused (422, plain words
  naming the PO, e.g. "PO <no> line is a different product.") before anything is sent to AutoCount.
- AC-HT1-c Stock Debt is unchanged: its scope is one snapshot row, one product (its tests stay green, no assertion edit).
- AC-HT1-d Screen: on the OI lines list and on the OI document (gear), "Link PO... (n)" is enabled for ticked rows of
  different products; there is no "Tick rows of one product." / "Tick lines of one product." reason any more.
- AC-HT1-e In the Link PO popup each new row's PO picker offers only PO lines of that row's product; a row whose product
  has no PO line with free qty shows "No PO line has stock free for this product." in that row, and the other rows
  stay usable (Save links them).
- AC-HT2a In the Link PO popup the qty box of a new row sits under a column headed "Qty"; the Keep / Unlink / Change to
  picker of a linked row sits under a column headed "Action". No column headed "Action" holds a qty box.
- AC-HT2b A link line AutoCount skips or refuses names the plain reason: SS's own `message` for that line when it gives
  one; a PO-row-not-found code (PO_ROW_NOT_FOUND, PO_NOT_FOUND, PO_LINE_NOT_FOUND, DOC_NOT_FOUND) reads
  "PO <po no> is not in AutoCount"; never a raw code. "AutoCount did not accept it" only when neither is known.
