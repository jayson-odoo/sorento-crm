# PS-QUOTE-MATRIX browser run (laneboard/scripts/2108.md)

Branch claude/ps-quote-matrix-grid-wvwc9s, HEAD d2fed611ad. Cloud sandbox, dev server (`npm run dev`), backend on
SORENTO_ENV_FILE=.env.ci-tests, no worker. Browser: agent-browser, sessions `pqm2` (CRM, staff user) and `pqm3`
(customer link, not signed in). Viewports 1280x800 and 375x812. Seed: one superadmin test user, project "PQM hand test",
4 catalogue products (FT100-SS, KS903, GH-ACC1, LV-9), brand "Brand Alpha". All names invented.

Deviations from the script, none of them app defects unless listed under Findings:
- Added a third scope LEVEL 9 (RM 570.00, 14 columns under 2 headers) to see vertical PDF headings. Grand total is therefore
  123,660.00 (script: 123,090.00 + 570.00 - 0); the script's three amounts are all present and correct.
- Send used the "Email" menu item (no SMTP in sandbox, the issue was still created as QPQM/Q/0001-A).
- PDF and Excel were fetched from the direct routes `.../issues/{id}/pdf` and `.../issues/{id}/xlsx` with the staff bearer token.
  The CRM button queues the RQ worker which stores to S3/R2; neither worker nor storage credentials exist in the sandbox.
  The queued path was not exercised.
- Step 10 paste was a synthetic ClipboardEvent("paste") with text/plain "10\t20" dispatched on the focused box (headless has no
  system clipboard). The handler called preventDefault and filled right.
- The customer link was copied through the UI ("Copy counter-sign link", POST .../sign-link 200); the URL itself was
  read back by calling the same route with curl.

| Step | Result | What was seen | Screenshot |
| --- | --- | --- | --- |
| 1 Open proposal, Lines tab, UNIT | PASS | Draft proposal, UNIT tab selected. Header, Lines, Cover letter, Terms, Signatures, Customer feedback tabs. | |
| 2 Add first column header TYPE A | PASS with wording note | Entry point is a "+ Column header" button in the card footer (edit page), not an "Add a column header" column at the far right (that column appears once a grid exists). TYPE A shows one box holding 1.00, footer Total qty 1. | 02-first-header-1280.png |
| 3 Two columns under TYPE A | PASS (see F2) | `+ Column` under TYPE A twice, named `1 BH`, `BALCONY`. | |
| 4 TYPE B with `2 BH`, `BALCONY` | PASS | Second header and two columns. Each change fires `PUT /quotation-versions/{id}/columns` 200. | |
| 5-6 Enter 120/120/500/250, read row and footer | PASS | Row: TYPE A Qty 240 RM 10,800.00; TYPE B Qty 750 RM 33,750.00; Total qty 990; Amount RM 44,550.00. Footer qty 120, 120, 240, 500, 250, 750, 990; footer RM 10,800.00 / 33,750.00 / 44,550.00. Photo, drawing, product, description, brand, UOM, rate, Rate only all still present; grid scrolls inside its card, no page scroll at 1280. | 06-quantities-right-1280.png |
| 7 Rename TYPE B to `TYPE B - 2 BH` | PASS | Header reads TYPE B - 2 BH, cells unchanged. | |
| 8 Remove TYPE A / BALCONY then Undo | PASS | Column header turns red with an 8s countdown and an undo icon (aria "Undo removing BALCONY"). After Undo it is back with 120; total back to 44,550.00. | 08-remove-undo-1280.png |
| 9 GUARD HOUSE | PASS | One Qty column (2), Rate 520.00, Total RM 1,040.00, no grid columns. | |
| 10 Paste `10<TAB>20` | PASS (synthetic) | TYPE A / 1 BH = 10, TYPE A / BALCONY = 20 (fills right); row total 30, RM 1,350.00. | |
| 11 Type 120, 120 back | PASS | Back to 240 / 10,800.00 / 990 / 44,550.00. | |
| 12 KS903 at 310.00, TYPE B / 2 BH = 250 only | PASS | TYPE A pair shows "-" and "-"; TYPE B Qty 250, RM 77,500.00; footer TYPE B 750, 250, 1,000, RM 111,250.00. | 12-ks903-row-1280.png |
| 13 Send, open PDF | PASS | Send to Customer A (Email) created QPQM/Q/0001-A. PDF 3 pages (cover, quotation, closing). UNIT table: two-row header (TYPE A over 1 BH / BALCONY, TYPE B - 2 BH over 2 BH / BALCONY), then TYPE A and TYPE B - 2 BH each over QTY and AMOUNT (RM), TOTAL QTY, UNIT RATE, COMPLETE SET, GRAND TOTAL; footer rows TOTAL QTY and TOTAL (RM); TOTAL 122,050.00. Brand, product code, unit rate, complete set printed. GUARD HOUSE block unchanged (QTY 2 PCS, 1,040.00). LEVEL 9 (14 columns) prints vertical headings, TOTAL AMOUNT RM 123,660.00. All three scopes share one landscape page. | 13-pdf-unit-header-totals.png, 13-pdf-level9-vertical-headings.png |
| 14 Excel | PASS | Sheets UNIT, GUARD HOUSE, LEVEL 9. UNIT merged: F14:G14 (TYPE A), H14:I14 (TYPE B - 2 BH), J14:K14, L14:M14, plus A..E, N..Q two-row merges. Row formulas J16 `=SUM(F16:G16)`, K16 `=ROUND(J16*O16,2)`, N16 `=SUM(F16:I16)`, Q16 `=ROUND(N16*O16,2)`; footer `=SUM(F16:F17)`, `=SUM(K16:K17)`. LEVEL 9 merges F4:L4, M4:S4. | |
| 15 Customer link, signed out | PASS | `/quotation-sign/<token>` opens with no CRM login; UNIT section opens as a read-only grid with the same numbers (120/120/500/250, 990, 44,550.00; KS903 250, 77,500.00). | |
| 16 Feedback on FT100-SS TYPE B / 2 BH | PASS | Note "need 520", suggested quantity 520, toast "Thank you. Your feedback has been sent to Sorento." Amber corner on that box. No "suggestions are with Sorento" text on the page. | 17-feedback-sent-1280.png |
| 17 Feedback on KS903 (whole item) | PASS | "can do 290?", Price radio, 290.00, sent; row 2 shows an amber dot and "Feedback sent". | 17-feedback-sent-1280.png |
| 18 Sign on the same page | PASS | Signing still offered after both notes; `POST .../accept` 200; page then reads "Accepted by QA Customer". | |
| 19 Customer feedback tab | PASS with ordering note (F3) | Tab badge 2. Notes: "Flush tank 100 SS demo / UNIT / TYPE B - 2 BH / 2 BH / "need 520" / Suggested quantity 520 (now 500)" and "Kitchen sink 903 demo / UNIT / whole item / "can do 290?" / Suggested price RM 290.00 (now 310.00)". Issued grid unchanged (990 / 44,550.00 and 250 / 77,500.00). | 19-customer-feedback-tab-1280.png |
| 20 Tick Handled | PASS | Ticked on the FT100-SS note (the script's "first" note, listed second): "Handled by QA Sales, 03/11/2026, 2:51 am"; badge 1; `PATCH .../feedback/{id}` 200. | 20-handled-1280.png |
| 21 Show in Lines on the KS903 note | PASS | Lines tab opens on UNIT with an amber dot beside line 2 (KS903). | 21-show-in-lines-1280.png |
| 375px: CRM Lines grid (read) | PASS | document scrollWidth 360 = clientWidth 360; grid scroller 1480 wide inside a 284 card. | 22-lines-375.png |
| 375px: CRM edit Lines grid | PASS | no page scroll (360/360); grid scroller 1684 in a 284 card. | 24-edit-lines-375.png |
| 375px: customer sign page, UNIT and LEVEL 9 | PASS | document 375/375; UNIT table 732 wide, LEVEL 9 table 1422 wide, each scrolling inside a 302 card. Not screenshotted (12-file cap). | |

## Findings

F1. (Low) Edit-mode column-name inputs are clipped. Under a header the leaf column name input shows about 2 characters
("1 E", "BA", "2 E") at 1280, because the leaf columns are narrow while the Qty and RM columns beside them are wide. See
06-quantities-right-1280.png and 08-remove-undo-1280.png. The label is fully shown in read mode and in the PDF.

F2. (Observation, behaviour to confirm) Adding the first leaf column under a header clears the single box's quantity. After step 2 the
box holds 1.00 and the total is unchanged (as the script expects); after step 3 the line quantity is blank and the total drops
to 0 until step 5. The script does not say what step 3 should show.

F3. (Low) Step 19 order and label differ from the script text. Notes list newest first (KS903 note above the FT100-SS note), and
the note title is the line description ("Flush tank 100 SS demo") rather than the product code "FT100-SS". Content of both notes
matches. I ticked Handled on the FT100-SS note and used Show in Lines on the KS903 note so steps 20 and 21 read as the script intends.

F4. (Medium, by design but trap) Column header edits save at once (`PUT .../columns`) while cell quantities only save with
"Save proposal". A tab hang forced a page kill mid-edit and on reload the headers were back but every quantity typed
since the last Save was gone. Not a defect against the script; flagging because the two persistence modes sit in one grid.

F5. (Low) PDF, step 13 wording: UNIT, GUARD HOUSE and LEVEL 9 all print on ONE landscape page (page 2), not one page per scope.
In the 4-column sub header, "BALCONY" wraps as "BALC / ONY" in the narrow leaf columns.

F6. (Low) Console on the customer page warns `Missing Description or aria-describedby for DialogContent` on the feedback dialog.

F7. (Low) The Header-tab address field of the new-proposal form was empty on first open although the proposal saved the
developer address snapshot (the header after save shows it correctly). Seen once on /quotation-documents/new, not investigated.

Sandbox-environment problems (NOT lane defects, fixed in the sandbox DB only so the run could continue):
- `brands.no_promo_selling_price` missing (bootstrap schema older than migration bnsp_0001): `GET /master-data/products/select` 500
  with any brand attached.
- `projects.quotation_issue_views` missing (migration of #2102): Send answered "Sent to the customer" then `GET quotation-documents`
  and `.../{id}` returned 500 until the table was created from the model.
- The tenant had no installed modules, so the sidebar showed only Dashboards and
  Ideas; installed all 24 modules with `install_modules` (as scripts/seed_never_stuck_smoke.py does).
- A product dropdown request hung once and froze the browser tab; the old session had to be killed (own session only).

Not covered: the queued "Download PDF / Download Excel" path through the worker and storage, WhatsApp send, real clipboard paste.
