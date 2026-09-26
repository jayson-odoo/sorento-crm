# S4-6 and S6-6 browser evidence, PR #1237

Stack: frontend http://localhost:3081, backend http://localhost:8081, DB sorento_cagent_stack, branch feat/po-schedule-redesign-s3-s4-s6 at 05469a50c.

## Files

- `s4-6-1-start-menu-1280.png` (S4-6, J5) - Pipeline page with the Start menu open (Register a project / Upload PO / Upload delivery schedule), 1280 wide. Proves the Start entry point exists on Pipeline.
- `s4-6-1-start-menu-375.png` - same Start menu at 375 wide.
- `s4-6-2-upload-po-setia-alam-1280.png` (S4-6, J5) - Upload a customer PO dialog with the Project field showing "Setia Alam" picked, 1280 wide. Proves the project picker step of the journey.
- `s4-6-2-upload-po-setia-alam-375.png` - same dialog state at 375 wide.
- `s4-6-3-po-review-1280.png` (S4-6, J5; also S4-1/S4-5) - the PO review screen reached after Upload, for the new PO version (HQ/26/01/121 v2, "To confirm"), 1280 wide. The URL after Upload was `/project-sales/abfcad89-30ec-45ab-a04d-8631c768b3a9/purchase-orders/51753eb1-8b6e-4e63-9965-5acabcd6dc6c?from=%2Fproject-sales%2Fpipeline%3Fpage%3D1%26limit%3D50%26sort%3Dcreated_at%26dir%3Ddesc%26from%3Dabfcad89-30ec-45ab-a04d-8631c768b3a9`, proving the `from` param carries the Pipeline list state and the picked project's id (S4-1, S4-5).
- `s4-6-3-po-review-375.png` - same PO review screen at 375 wide.

- `s6-6-po-review-hq-26-01-121-v1-1280.png` (S6-6, J3) - the PO review screen for HQ/26/01/121 v1 on Setia Alam (version id `5825ce6e-c875-4d72-b3c2-b01ad7865335`, confirmed 19/08/2026), reached via sidebar Project Sales > Pipeline > Setia Alam row > project page > POs tab > HQ/26/01/121 row > "Open" next to v1 (not a deep URL). Header shows "PO HQ/26/01/121 v1", green "Confirmed" pill, the meta line ("Setia Alam (PRJ-000001) · 51 lines · Document total RM 1,810,640.62 · Our sum RM 1,805,907.02 · RM 4,733.60 short, 1 cancelled line"), the Confirmed/Approved/Countersigned status trail, one primary button ("Approve"), and the Lines (51) / Documents tabs with "Lines identified 1" / "Show all lines (51)" toggle - matches the approved mockup's structure (`mockups/po-review.html` panel 1, "1280 WIDE, LINES TAB (DEFAULT)").
- `s6-6-po-review-hq-26-01-121-v1-375.png` - same screen at 375 wide.

## Not shown

- **S4-6's final frame (back on Pipeline with the Setia Alam row highlighted) was not captured.** On this real extracted PO the "Confirm this PO" button is disabled with the copy "19 handwritten notes still unreviewed / Review them". Clicking "Review them" scrolls the Lines grid to individual "Accept the note" / "Edit the note" / "Reject the note" actions on 19 separate handwritten annotations (page notes like "Cancel item (7)... Refer to New P/O HQ/26/05/087", code amendments, etc). Accepting or rejecting each of these is a business judgment about the content of a real customer PO, not a UI-only action, and is out of scope for a screenshots-only evidence run (the brief's own instruction to stop before an action with real consequences, applied to this blocker rather than to an external-publish one, since the Confirm button here does not send anything outward - the status trail Confirmed/Approved/Countersigned is an internal-only chain). I stopped at the pre-Confirm PO review state (`s4-6-3-*`) instead. The `from` URL parameter captured in `s4-6-3` already demonstrates S4-1/S4-5 (that the origin, including the Pipeline row, is threaded through); S4-2/S4-4 (the post-Confirm return-and-highlight behaviour itself) remain unverified by this run and are owed a follow-up pass, either on a PO version with no outstanding handwritten notes, or after the coder/owner decides how the 19 notes on this real PO should be resolved.

## Divergences from the mockup (factual, S6-6)

- The mockup's Lines table shows six columns (#, Our product, Description, Qty, Total, Action). The real screen's Lines grid (`POIntakeLinesGrid`, unchanged per the plan) has more columns (#, Code on the PO, Description, Qty, UOM, Unit price, Amount, Flag, Our product, Actions). This is the existing grid with only a Flag column and inline action added, not a new build to the mockup's exact column set; the mockup is a simplified wireframe of the same grid, not a literal spec. Flagged per R22 (fewer elements than the mockup is fine, more is a defect) since it is visibly more columns, for the reviewer's judgment call.
- The mockup's flagged row shows a "Dismiss with a reason" action. The real screen's flagged row (line 7, SRTFV1001, struck through, RM 4,733.60) shows "Cancelled / Cancel line" instead, with no Dismiss action. This matches the plan's documented reviewer amendment (a), 25 Sep 2026 (S6-4): a PO line's mismatch is not a persisted `SODraftFinding` row, so correcting/cancelling the line is the designed resolution and Dismiss does not apply to a PO line. Not a defect, an intentional post-mockup amendment.
- Documents tab (checked but not screenshotted, since not in the requested file list): renders "This PDF is not available yet" with an "Upload the PO again" action (no error code), matching S6-5/R13 and the mockup's 375 empty-state panel, with the rejected-note annotations grid directly below it in the same tab, matching R18.
- Dev-mode-only: a Next.js "1 Issue" overlay badge is present, tracing to a React "Each child in a list should have a unique key prop" warning in `Demo1Layout` (the app shell, not this PR's components) and a `[tiptap warn] Duplicate extension names found: ['link']` warning from a shared rich-text editor. Neither appeared in `errors` (no uncaught exception) and neither traces into the S3/S4/S6 code touched by this PR; noted for completeness, not filed as a defect of this slice.

## Data left as found

Before (both projects.purchase_orders and projects.po_versions for Setia Alam, project id abfcad89-30ec-45ab-a04d-8631c768b3a9):

```
                  id                  |  po_number   | status |         created_at
--------------------------------------+--------------+--------+----------------------------
 26ac5723-a6fe-417b-93f0-af2e52f15553 | HQ/26/01/121 | draft  | 2026-08-19 05:46:29.625945
(1 row)

                  id                  |          purchase_order_id           | version_no | extraction_state |        confirmed_at        |               source_filename               |         created_at
--------------------------------------+--------------------------------------+------------+------------------+----------------------------+---------------------------------------------+----------------------------
 5825ce6e-c875-4d72-b3c2-b01ad7865335 | 26ac5723-a6fe-417b-93f0-af2e52f15553 |          1 | done             | 2026-08-19 05:58:52.105636 | Buimaco Bulk PO - Tuju Residence - (R1).pdf | 2026-08-19 05:46:29.625945
(1 row)
```

After:

```
                  id                  |  po_number   | status |         created_at
--------------------------------------+--------------+--------+----------------------------
 26ac5723-a6fe-417b-93f0-af2e52f15553 | HQ/26/01/121 | draft  | 2026-08-19 05:46:29.625945
(1 row)

                  id                  |          purchase_order_id           | version_no | extraction_state |        confirmed_at        |               source_filename               |         created_at
--------------------------------------+--------------------------------------+------------+------------------+----------------------------+---------------------------------------------+----------------------------
 5825ce6e-c875-4d72-b3c2-b01ad7865335 | 26ac5723-a6fe-417b-93f0-af2e52f15553 |          1 | done             | 2026-08-19 05:58:52.105636 | Buimaco Bulk PO - Tuju Residence - (R1).pdf | 2026-08-19 05:46:29.625945
 51753eb1-8b6e-4e63-9965-5acabcd6dc6c | 26ac5723-a6fe-417b-93f0-af2e52f15553 |          2 | done             |                             | customer-po-buimaco-r1.pdf                  | 2026-09-25 08:06:36.228272
(2 rows)
```

New rows created by this run, not undone:

- `projects.po_versions` id `51753eb1-8b6e-4e63-9965-5acabcd6dc6c` - version 2 of purchase order HQ/26/01/121 (id `26ac5723-a6fe-417b-93f0-af2e52f15553`), extraction done, never confirmed, source file `customer-po-buimaco-r1.pdf` (the committed e2e fixture).
- `attachments` id `07bde8ae-491d-4e67-9711-9ca27d1ba617` - the uploaded `customer-po-buimaco-r1.pdf`, storage_provider `r2`, created 2026-09-25 08:06:37.

Not undone: the "Purchase order actions" menu on the PO detail page offers only "Upload a document" and "Delete this PO" - no per-version delete/discard action exists for the unconfirmed v2 alone. "Delete this PO" would remove the whole PO header, including the real confirmed v1 (production data, confirmed 19/08/2026), so it was not used. The v2 row is left in place, unconfirmed, extraction_state done, no confirmed_at - it does not affect v1 or its confirmed status, and does not change HQ/26/01/121's document total / our-sum figures shown anywhere since those are computed per version.
