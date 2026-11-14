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

## Re-check 46af9049

Same method (fresh private DB, fake Shared Service, `next dev`, session `oipo`, sidebar navigation). The line covered by two PO lines was seeded
as PO-60013 (4) plus PO-60014 (2) on SO-24101 line 10.

| # | Step | Expected | Actual | Result | Screenshot |
|---|------|----------|--------|--------|------------|
| R1 | OI Link to PO dialog (1280) | Location and Delivery date per line, dd/mm/yyyy | Cells read "MWH" and "15/12/2026" for both lines (the date is cut by the column width to "15/12/20..." on screen, full value in the cell) | PASS | 30-recheck-link-dialog-1280.png |
| R2 | Change PO on the line covered by two PO lines | "Covered by more than one PO line", cannot be sent | Title "Covered by more than one PO line", text "Change PO needs a line covered by exactly one PO line.", button "Change 0 lines" disabled | PASS | 33-recheck-change-two-po-1280.png |
| R3 | SS refuses one link, OI dialog | Reason plus "Try again"; pressing it turns the card to done without reopening | Card "Not linked: SO-24102 line 10: PurchaseAgent is required." with "Try again"; pressing it sent a second `po-links` call and the same card became "Linked ... PO-60011 (10)" | PASS | 31-recheck-refused-try-again-1280.png, 32-recheck-try-again-done-1280.png |
| R4 | Same from the Stock Debt drill | Same behaviour | Refused card with "Try again", pressing it gave "Linked ... PO-60011 (6)" in place | PASS | 35-recheck-stockdebt-refused-1280.png, 36-recheck-stockdebt-try-again-done-1280.png |
| R5 | Dialog at 375px | No horizontal page scroll | `scrollWidth == clientWidth == 375`, dialog fits, grid scrolls inside itself | PASS | 34-recheck-link-dialog-375.png |

## Owner round 13 Nov

Stack: private Postgres DB `sorento_browser` (re-created, `scripts.bootstrap_env`), backend :8055, `next dev` :3055, scratch fake Shared Service :8056
answering `write-capabilities` (split_link, link_row, unlink_row, relink_row enabled), `po-links`, `po-links/batch`, `po-links/unlink`
(stateful per PO doc; the link and Change PO writes in this round went to `po-links/batch` and `po-links`/`po-links/unlink`).
Agent-browser sessions `oipo13` (desk user, 1280x800 then 375x812) and `oipo13adm` (superadmin, switch only). All data fake.
Data: one OI with 6 rows. SO-24101 L10 qty 12 covered by TWO PO lines tied in AutoCount (4 + 2); SO-24102 qty 10 AutoCount, unlinked;
SO-24103 product B qty 6; SO-24104 qty 8 AutoCount, CRM-only link to PO-60016 (not tied); SO-24105 qty 5 AutoCount, tied to PO-60015;
one row qty 3 whose SO line is not in AutoCount. No SPO allocation row was seeded (CRM-only case covered by a PO line not tied).
Navigation by sidebar clicks from `/` (Procurement > Supply Chain > Order Inquiries), row click for the document view.

| # | Step | Expected | Actual | Result | Screenshot |
|---|------|----------|--------|--------|------------|
| D1 | Document view gear, nothing ticked | Auto link, Link to PO... (n), Change PO... (n), Unlink... (n); no Choose document / Link selected / Unlink selected | Exactly those four, counts (0) greyed; none of the retired items | PASS | r13-01-doc-gear-nothing-ticked-1280.png |
| D2 | Link to PO on the AutoCount unlinked line (qty 10) | Shared dialog, no "Line" column, link done | Columns Sales order, Location, Delivery date, Outstanding, PO, PO qty, Free, Qty; no Line column; Link gave "Linked ... (10)"; SS got one `po-links/batch` with `X-Acting-User-Name: Aisha%20Rahman` | PASS | r13-02, r13-03, r13-04, r13-05 |
| D3 | Change PO on the twice-covered line | One row per PO, pick one, only that PO replaced | Two rows "PO-60013 . line 1 (4)" and "PO-60014 . line 1 (2)"; picked a target only on the PO-60014 row, "Change 1 line"; SS log: `po-links/unlink` for doc 12310 only (PO-60013 untouched), then `po-links` doc 12008 qty 2 | PASS | r13-06, r13-07, r13-08, r13-09, r13-10 |
| D4 | Unlink... on the CRM-only line | Countdown, no dialog | "Unlinking in 4s" bar with Cancel in the header, no dialog; after the window the CRM link was gone, no SS call made | PASS | r13-11, r13-12 |
| D5 | Unlink... on an AutoCount-tied line | Shared dialog | "Unlink from PO" dialog, row SO-24105 PO-60015; Unlink 1 line gave "Unlinked", SS `po-links/unlink` doc 12320 | PASS | r13-13, r13-14 |
| D6 | Unlink... on a mix (one CRM-only, one tied) | Both | Dialog for the tied line AND countdown for the CRM-only line at once; countdown removed the CRM link, dialog cancelled, no SS call | PASS | r13-15 |
| D7 | Link to PO... on the line not in AutoCount | CRM dialog, PO lines only | "Link to a document" listing PO-60011, 60012, 60015, 60016 (all tagged PO, no SPO), issue date 01/09/2026 | PASS | r13-16 |
| D8 | Switch OFF (saved in Settings as superadmin, POST general 200, DB flag false), document view | Link to PO... opens CRM dialog, Change PO absent | Gear: Auto link, Link to PO... (1), Unlink... (0); no Change PO; Link to PO opened "Link to a document"; no SS call | PASS | r13-36, r13-37, r13-38 |
| L1 | Lines view Actions | No Choose document; Link to PO (n), Change PO (n), Unlink from PO (n), Recheck in AutoCount, Remove link in CRM | All present, plus Auto link all / Reject / Unconfirm etc.; none of the retired items | PASS | r13-17, r13-18 |
| L2 | Lines: Link to PO | Works as before | Row SO-24105 to PO-60012 (5): "Linked", `po-links/batch` sent | PASS | r13-19, r13-20 |
| L3 | Lines: Change PO on the twice-covered line | One row per PO, one replaced | Rows PO-60011 and PO-60013; changed only PO-60013 to PO-60016: `po-links/unlink` doc 12300 then `po-links` doc 12330 qty 4 | PASS | r13-21, r13-22 |
| S1 | Stock Debt drill Dec 26, tick the twice-covered line, Decide | Change PO... enabled, popup lists both, works | Menu lists Request CS, Link, Change PO..., Unlink, Move PO (none greyed); popup shows PO-60011 (2) and PO-60016 (4); changed PO-60011 to PO-60014: unlink doc 12008 then link doc 12310 qty 2, both done | PASS | r13-23 to r13-28 |
| M1 | 375px: document gear, Change PO, picker, Link, Unlink dialogs; Lines Actions + Change PO | Fit, no horizontal page scroll | `scrollWidth == clientWidth == 375` in every state; dialogs 375 wide at left 0; grids scroll inside themselves | PASS | r13-29 to r13-35 |
| R1 | Standing rules | one line per row, no ids, dd/mm/yyyy, nothing hangs | One line per grid row in the shared dialogs, no ids or UUIDs, all dates dd/mm/yyyy (15/12/2026, 01/09/2026, 13/11/2026), every write answered within 6 s | PASS | all |

Not walked: Stock Debt Decide menu and its Change PO popup at 375 (same shared dialog as M1, not opened at 375 in this round).

### Observations (not failed steps)
- O1: after an AutoCount unlink (Change PO or Unlink), the OI row keeps its `order_inquiry_links` row to the PO line that was just unlinked in
  AutoCount. DB after D3: SO-24101 still held links to PO-60014 (2, no longer tied) next to the new PO-60011 link, and the Lines PO column read
  "PO-60014 +2"; after D5 the SO-24105 row kept its PO-60015 link and then counted as CRM-only (the next Unlink went through the countdown).
  `PoLinkService._send_unlink` (`sorento_crm_backend/app/services/scm/po_link_service.py:831-843`) and `change` (`:941-951`) never touch the
  OI link. Same family as the 11 Nov note on the PO column after Unlink; needs an owner call whether the CRM link should go with it.
- O2: Change PO... (n) in the document gear is enabled for a ticked AutoCount line that has no PO linked at all
  (`OrderInquiryDetail.tsx:863`, gate is switch + grant + in AutoCount only). Not opened to see the dialog message in this round.
- O3: at 1280 the shared Link dialog grid scrolls sideways inside itself (Qty column partly cut); at 375 the Change PO grid shows two stacked
  scrollbars and the PO picker column needs a sideways swipe (pre-existing from the 11 Nov pass).
- O4: the PO numbers in this fixture start with "PO-", so the wording reads "PO PO-60011"; a fixture artifact, not a defect.
- O5: the document header read "Completed" on first open of the seeded OI (unlinked rows present) and "Outstanding" after the first write; seed shape, not traced.
- Settings: the first Save click did nothing because the button was off screen (scrollintoview needed); a fresh DB also needs support email and timezone.
