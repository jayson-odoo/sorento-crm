# OI-PO-LINK browser pass (11 Nov 2026)

Stack: backend uvicorn :8055 on a private Postgres DB (`sorento_browser`, bootstrapped with `scripts.bootstrap_env`),
frontend `next dev` :3055, a scratch fake Shared Service on :8056 (stateful per PO doc, one-shot refusal switch).
All data is fake (project "Marina Heights Residences", products BSN-A100 / BSN-B200, SO-24101..24103, PO-60011..60013).
Agent-browser session `oipo`, headless, deviceScaleFactor 1, 1280x800 then 375x812. Navigation by sidebar clicks.
Seeded user holds only: projects.projects.view, stock_debt.view, stock_debt.link_po, order_inquiry.action, scm.dashboard.view,
plus order_inquiries.acknowledge/reserve (needed to get tick boxes at all, see N1). A second superadmin toggled the switch.

Data shape: one project SO, 4 OI rows (A line 12, A line 10, B line 6, A line 3 with no AutoCount line); two open PO lines of A
(free 30 and 5) plus one PO line (4) already linked to the 12-line. Fake SS answers `write-capabilities`, `po-links`, `po-links/unlink`.

| # | Step | Expected | Actual | Result | Screenshot |
|---|------|----------|--------|--------|------------|
| 1 | Sidebar to Order Inquiries (1280) | Reachable by clicks from `/` | Reached via Procurement > Supply Chain > Order Inquiries (it is not under Project Sales in this sidebar, see N2); Lines tab shows 4 rows, dates dd/mm/yyyy | PASS | 01-lines-1280.png |
| 2 | Tick 2 eligible A rows + the non-AutoCount row, open Actions | "Link to PO... (2 of 3)", Change/Unlink same counts, "Recheck in AutoCount (3)", "Remove link in CRM" present | Exactly that: Link/Change/Unlink "(2 of 3)", "Recheck in AutoCount (3)", "Remove link in CRM (0 of 3)" | PASS | 02-actions-menu-1280.png |
| 3 | Open Link to PO | One row per SO line, one line per grid row, no ids, default qty = still needed capped at free | 2 rows (SO-24101 L10 needs 8 = 12 less the 4 already linked; SO-24102 L10 needs 10); "OI-BR-0001 BSN-A100: Not in AutoCount yet" named; no ids. Location and Delivery date columns are "-" (D1) | PASS with D1 | 03-link-dialog-1280.png, 04-po-picker-1280.png |
| 4 | Pick PO-60011 on both lines (same PO line), qty typing: select, delete, type 2 | Field empties on delete, shows 2, no stuck 0 | Delete gave "", typing 2 gave "2" | PASS | 05-dialog-filled-1280.png |
| 5 | Link 2 lines (one partial of 30, one to the same PO line) | Two `po-links` writes, both done | SS got qty 2 (split) then qty 10 with `X-Acting-User-Name: Aisha%20Rahman` and a request id; both cards "Linked"; FE called `/order-inquiries/po-link/link` 200 | PASS | 06-link-results-1280.png |
| 6 | Close; rows show the PO | PO column names the PO | Row A10 shows PO-60011, row A12 shows "PO-60013 +1" | PASS | 07-rows-after-link-1280.png |
| 7 | Right-click a row | Three items | Link to PO..., Change PO..., Unlink from PO... (synthetic `contextmenu` event, the CLI has no right-click) | PASS | 08-row-context-menu-1280.png |
| 8 | Change PO on the 12-line (covered by 2 PO lines) | Not offered or a clear reason | Dialog says "No PO linked / The ticked lines have no PO line linked" although two are linked (D2) | FAIL (wording, D2) | 09-change-po-dialog-1280.png |
| 9 | Change PO on the 10-line (one PO) | Unlink first, then link | SS order: `unlink`, then `po-links`; cards Unlinked, Linked | PASS | 10-change-po-single-1280.png, 11-change-result-1280.png |
| 10 | Unlink on one row | Unlink done | "Unlinked"; SS got `po-links/unlink`. No deferred countdown on the button (N3) | PASS | 12-unlink-dialog-1280.png, 13-unlink-result-1280.png |
| 11 | SS refuses once, Link | Result reads refused with the reason; retry sends a new attempt and succeeds | Card "Not linked: SO-24102 line 10: PurchaseAgent is required."; there is no "Try again" button, Done only (N4); reopening and pressing Link again sent a second call and answered "Linked" | PASS with N4 | 14-po-picker-options-1280.png, 15-refused-1280.png, 16-retry-done-1280.png |
| 12 | Tick A and B rows | Link/Change/Unlink greyed "Tick rows of one product." | All three disabled, `title="Tick rows of one product."` | PASS | 17-mixed-products-1280.png |
| 13 | Renames | "Recheck in AutoCount", "Remove link in CRM" | Present (steps 2, 12) | PASS | 02, 17 |
| 14 | Stock Debt snapshot, drill Dec 26, tick both lines, Link to PO... | Dialog opens as before, columns filled | Dialog opens, Location MWH and Delivery 15/12/2026 filled, defaults 6 and 2 | PASS (open + options only, no write) | 18-stock-debt-drill-1280.png, 19-stock-debt-link-dialog-1280.png |
| 15 | 375px: OI Lines, Actions, Link dialog | No horizontal page scroll, usable | `scrollWidth == clientWidth` on the list and with the dialog open; dialog 375 wide, grid scrolls inside itself (PO, Qty columns need a sideways swipe, and a second scrollbar shows under the skipped note) | PASS | 20-oi-lines-375.png, 21-actions-375.png, 22-link-dialog-375.png |
| 16 | Settings: switch "AutoCount PO links" OFF, save (superadmin) | Saved | `POST /user-management/settings/general` 200, DB flag false (a fresh DB needed a timezone and support email first, not a lane defect) | PASS | 23-settings-switch-1280.png |
| 17 | Switch OFF, OI Actions and right-click | The three items gone | Actions has no Link/Change/Unlink to PO; right-click opens no menu (0 items) | PASS | 24-switch-off-actions-1280.png, 25-switch-off-context-1280.png |

Owner standing rules: one line per row in the dialog grid PASS; no ids or UUIDs shown PASS; dates dd/mm/yyyy PASS (OI grid, Stock Debt drill);
number field typing PASS; nothing hung PASS (every write answered within 5 s); 375px no horizontal page scroll PASS.

## Defects
- D1 (AC-14): the Order Inquiry dialog shows "-" in Location and Delivery date for every line while the Stock Debt dialog fills them.
  `PoLinkService.lines()` in `sorento_crm_backend/app/services/scm/po_link_service.py:355-362` returns no `location_code` / `delivery_date`
  per line (the SO line has both: the OI grid shows MWH and 15/12/2026), so the shared columns in
  `sorento_crm_frontend/app/(protected)/project-sales/_shared/po-link/PoLinkDialog.tsx:332-338` stay empty.
- D2: Change PO on a line covered by two PO lines opens the empty state "No PO linked" (`PoLinkDialog.tsx:206-208`, `:617`), which is false.
  The popup should say the line has more than one PO.

## Notes
- N1: the tick boxes in the Lines grid exist only for users holding acknowledge or reserve (`OrderInquiriesClient.tsx:1151`); a user with only
  link_po + action can use the right-click items but cannot tick.
- N2: the task says Project Sales > Order Inquiries; in this build the sidebar entry is under Procurement > Supply Chain.
- N3: Unlink has no 5 s countdown although the SS capability is on (code comment in `po_link_service.py` says it is owed).
- N4: a refusal shows no "Try again" button; the retry is reopening the dialog.
- After Unlink the worklist PO column can still name the PO, because the re-run book step re-places the row on a PO line with free qty.
- The dev server was killed once by the sandbox out of memory (a parallel pytest run); restarted, which is the only source of the
  `ChunkLoadError` lines in the console. No other console errors.
