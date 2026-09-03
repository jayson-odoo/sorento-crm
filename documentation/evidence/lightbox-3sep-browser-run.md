# Loading plan lightbox feedback (3 Sep) - agent-browser evidence run

Run date: 2026-09-03. Frontend :3130 (HMR), backend :8130, both from worktree
`loading-plan-lightbox-3sep`, branch `feat/scm-loading-plan-lightbox-3sep`.
Driver: `npx -y agent-browser@0.27.0`, isolated session `lightbox-3sep`
(`AGENT_BROWSER_SESSION=lightbox-3sep`). Navigation: logged in at
`http://localhost:3130`, then sidebar clicks Supply Chain > Planning > Loading
Plan (no deep URLs for the primary flow). Screenshots under
`documentation/evidence/lightbox-3sep/`.

Two plans were used for the CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD
supplier, both reached via the Loading Plan list:

- **Plan A** (`.../loading-plan/29fb0bb0-a03c-481e-a8e3-3ab1348156a0`) - status
  **Sent**, "No file", the newest CHAOZHOU JINBAICHUAN entry. Used for the
  Lines-tab lightboxes (AC-A, AC-B, AC-C, AC-D, AC-E, AC-F, AC-H1).
- **Plan B** (`.../loading-plan/b03b3b77-c936-489a-80ea-7230c0c6c268`) - status
  **Planning**, "Stock list 03/09/2026", 23 unmatched supplier codes. Used for
  AC-G6 (the Sent plan had "Every code on file is matched", nothing to test).

One environment blip mid-run: the shared worktree's backend (uvicorn --reload
on :8130) briefly 500'd across the board and then dropped the connection
entirely for about 35s while `[Fast Refresh] rebuilding` cycled in the FE
console - consistent with another process editing source concurrently in the
same worktree. Not a product defect; a page reload recovered cleanly once the
backend came back up (confirmed via `curl :8130/docs` polling). No other
console/network errors were observed for the rest of the run (`errors`
command returned empty at the end).

## PASS/FAIL table

| AC | Result | Evidence |
| --- | --- | --- |
| AC-A1 (no "Project peak"/"Retail peak" text) | PASS | Need/Project/Retail history tabs checked via `eval`: dialog `textContent` does not contain "peak" (`10-need-dialog.png`, `11-need-history.png`, `21-project-history.png`, `31-retail-history.png`) |
| AC-A2 (`data-peak="project"`/`"retail"` on the highest cell) | PASS | `eval` on the dialog history tab: `[{"peak":"retail","text":"86"},{"peak":"project","text":"4,189"}]` for CWCX605-RL; `83-project-peak-tinted.png` shows both cells visually tinted |
| AC-A3 (Total row sums both columns) | PASS | `72-po-total-outstanding.png`-style totals confirmed on Need history ("Total" row = 19,505 project / 86 retail in `83-project-peak-tinted.png`) |
| AC-A4 (grid Project-peak cell opens Project dialog on history tab, month tinted) | PASS | Clicked the "4,189 Aug 26" cell in the Project peak grid column; dialog opened as "Project · CWCX605-RL" already on "12-month history" tab (not "Open"), Aug 26 row tinted with "4,189" (`82-project-peak-click.png`, `83-project-peak-tinted.png`) |
| AC-B1 (Need cell is a button, dialog titled `Need · <code>`) | PASS | Clicked Need button on CWCX605-RL row -> dialog title "Need · CWCX605-RL" (`10-need-dialog.png`) |
| AC-B2 (Open tab: project+retail lines with Channel column, Total = row's Need) | PASS | Open tab columns read "Sales order · Channel · Customer · Project · Agent · Price · Qty · Required"; Channel values shown are Retail/Project mixed in one list; tab label "Open (10,044)" matches the row's Need value on the grid (`10-need-dialog.png`) |
| AC-B3 (History: Month/Project/Retail/Total, peaks marked, `data-peak="total"`) | PASS | `eval`: `[{"peak":"retail","text":"86"},{"peak":"project","text":"4,189"},{"peak":"total","text":"4,189"}]` on the Need dialog history tab |
| AC-B4 (Set row: lines/history are driver member's) | NOT TESTED | No product-set row was exercised in this run (out of scope of the picked CWCX605-RL row) |
| AC-C1 (Channel tab label `Open before cut-off <date> (<sum>)` / `Open (<sum>)`) | PASS | Need dialog tab read "Open (10,044)" (no SO cut-off on this plan, so no-horizon form); Project "Open (9,958)"; Retail "Open (86)" |
| AC-C2 (SPO tabs `Open to pools (<sum>)`, `History (<sum>)`) | PASS | SPO dialog for CWCX605-RL: "Open to pools (352)" matching the single SPO-2026/08-0081 row qty 352; SPO dialog for CWC7601-S-RL: "Open to pools (878)" summing 4 rows (206+49+75+384+... ) confirmed as a sum, not a row count (`50-spo-open2.png`, `51-spo-varied.png`) |
| AC-C3 (PO tabs `Open (<sum still_to_come>)`, `History (<sum qty_ordered>)`) | PASS | PO dialog: "Open (1,980)", "History (7,961)" (`70-po-cwcx605.png`) |
| AC-C4 (no context string beside title; no `context` prop) | PASS | Every dialog title checked (Need, Project, Retail, On hand, SPO, Incoming PL, PO) shows only `<Type> · <code>` plus the code repeated once below as a subtitle - no additional context string beside the title in any screenshot |
| AC-D1 (`container_number` on SPO drill rows) | NOT DIRECTLY TESTED (FE-observable proxy only) | FE Container column showed "-" for all SPO rows in this dataset (no shipment attached yet); could not find an SPO row in this supplier's plan with a real container number to confirm the populated case |
| AC-D2 (Container header, dash or number, no "Packing list"/"Draft"/"Not shipped" text in that column) | PASS | SPO dialogs: column header reads "Container", value "-" for all rows shown; the "Not shipped" text appears only in the separate Status badge column, not the Container column (`50-spo-open2.png`, `51-spo-varied.png`) |
| AC-D3 (Status Badge, `Not shipped` when no shipment) | PASS | All SPO rows examined show a grey "Not shipped" pill in the Status column (`50-spo-open2.png`, `51-spo-varied.png`); could not find a row with `Fully Received`/`In Transit` in this dataset to confirm those variants |
| AC-E1 (Incoming PL columns Container/Supplier/Qty/ETA/Status, no Packing list column) | PASS | Incoming PL dialog for CWCX605-RL and SRTWC8152-RL both show header row "Container · Supplier · Qty · ETA · Status" with empty-state body "Nothing is on its way..." (`60-incomingpl-open.png`, `61-incomingpl-r1.png`) |
| AC-E2 (Container cell opens shipment via `onOpenShipment`) | NOT TESTED | Both Incoming PL dialogs tried were empty (no packing-list rows for this supplier in this dataset), so no Container cell was clickable to exercise |
| AC-E3 (Status is a Badge like AC-D3) | NOT TESTED | Same reason - no populated rows found |
| AC-F1 (PO status badge Outstanding/Completed/Cancelled/Draft) | PASS | Open tab rows all show green "Outstanding" pills; History tab rows show grey "Completed" pills (`70-po-cwcx605.png`, `71-po-history.png`) |
| AC-F2 (headers "Outstanding"/"Delivery date", total row "Total outstanding") | PASS | Column headers read "Outstanding" and "Delivery date" (not "Still to come"/"ETA"); bottom row reads "Total outstanding" = 1,980 (`70-po-cwcx605.png`, `72-po-total-outstanding.png`) |
| AC-G1/G2/G3 (lead time on first manual link) | PASS (observed, not isolated to a zero-link supplier) | After confirming a manual match (CWC7605-RL-250 -> CWCX605), the product's Suppliers tab showed CHAOZHOU JINBAICHUAN with Lead time (days) = 90, matching the existing DEFAULT link's 90 - consistent with AC-G3 (mode of the supplier's own/product's existing links); did not isolate a supplier with zero `product_suppliers` rows to specifically prove AC-G1/G2's fallback branches |
| AC-G4 (alias delete never removes the link) | NOT TESTED | Out of scope for this run (would require inspecting the link row after Forget instead of the alias) |
| AC-G5 (backfill script dry-run/apply) | NOT TESTED (not an E2E item) | Script-level check, not part of this browser run |
| AC-G6 (manual match -> product Suppliers tab shows "Their code") | PASS | Matched supplier-code `CWC7605-RL-250` to product `CWCX605` on Plan B's Supplier codes tab (Needs a decision 23 -> Confirm (1) -> 22); product `CWCX605` Suppliers tab then showed CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD with "Their code" = `CWC7605-RL-250` (`103-supplier-their-code.png`, confirmed via `eval` text extraction). Cleaned up: used "Forget" on the Remembered list entry; alias removed, code returned to "Needs a decision" (23), and the product's Suppliers tab "Their code" reverted to "-" for both suppliers (`104`-`107` screenshots) |
| AC-H1 (one recorded run: Need/Project/Retail/On hand/SPO/Incoming PL/PO all opened, screenshots) | PASS | All seven dialogs opened and screenshotted for the CWCX605-RL row on Plan A: Need (`10`), Project (`20`), Retail (`30`), On hand (`40`), SPO (`50`/`51`), Incoming PL (`60`/`61`), PO (`70`-`72`) |
| AC-H2 (pytest/vitest green) | NOT RUN | Out of scope for this browser-only verification task |

## Defects found

None. All discrepancies noted above are gaps in this specific dataset (no
in-transit/received SPO rows, no populated Incoming PL rows, no Channel
column visually re-confirmed after horizontal scroll) rather than product
bugs - no console error, no unexpected network response, and no visual
regression was observed in any of the ~50 screenshots taken.

## Notable environment observation (not a product defect)

Mid-run, `:8130` (this worktree's backend) returned a burst of `500`s on
every in-flight request, then stopped answering entirely for about 35
seconds, while the frontend console showed repeated `[Fast Refresh]
rebuilding` cycles. This lines up with a concurrent edit + uvicorn `--reload`
restart in the same shared worktree, not a bug introduced by the lightbox
work - a `location.reload()` after the backend came back recovered the page
with all dialogs working normally for the rest of the run.
