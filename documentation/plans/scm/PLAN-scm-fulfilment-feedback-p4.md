# PLAN: SCM fulfilment feedback, part 4 (loading plan list, supplier document fidelity, PI Start, packing list fixes, SPO planner redesign)

**Status:** GRILLED round 2 (2026-08-27 late), Q1-Q7 ruled (section 11), awaiting GO. Nothing built.
**Lane:** worktree `.claude/worktrees/scm-fulfilment-p4`, branch `feat/scm-fulfilment-feedback-p4` off `origin/main` `741469185` (#353). No stack slot yet (:3000/:8000 = inline-decisions lane, :3050 = oi-draft, :3060 = reorder revamp).
**UAC:** `scm-fulfilment-feedback-p4-acceptance-criteria.md`. **Review artifact:** `mockups/fulfilment-feedback-p4-plan.html` (lavish).
**Predecessor:** `PLAN-scm-fulfilment-feedback.md` (part 3, MERGED #347). R1-R25 there stand unless a ruling below names one.
**Reference files (Drive, `phase-2/User Requirements/purchasing/fulfilment_example_files/`):** `2026-7-27  库存明细.xlsx` (supplier stock list, the format every supplier document must match), `FSCU8103365.xlsx` (the packing list workbook).

## 0. The ask, in the captain's words, mapped to sections

| Captain said | Section |
|---|---|
| Loading plan: only one Upload button; a list view like reorder planning; cancel / delete a plan; click to open the plan | 1 |
| The list CTA is Upload, it opens the Plan-a-container popup, and the drag-to-upload lives inside that popup; "Plan until" becomes the sales-order cut-off | 1 |
| Project, Retail, On hand, SPO, Incoming PL, PO, Project peak, Retail peak all open the standard lightbox | 2 |
| Send to supplier by email OR chat; email lets me add recipients; track when the supplier opens the link | 3 |
| Link view, PDF, XLSX tally 100% with `库存明细.xlsx`, cbm merging included, formatting included | 4 |
| Form view: CTA = Send to supplier, secondary Save, gear LEFT of the CTA; Upload moves to the list | 1, 2 |
| PI list: "Convert to draft shipment" reads "Convert to packing list"; one CTA "Start" with two items (Upload proforma invoice, Convert to packing list); Delete under a gear left of the CTA; convert proceeds directly unless CBM exceeded | 5 |
| Packing list: draft number too random; notes not needed; supplier select shows the name only; Edit on the Shipment lines tab stays there; download tallies 100% with `FSCU8103365.xlsx`; the "Not packed / Not on the loading plan" extras go | 6 |
| SPO planner: PO covers and SO covered open a lightbox with the suggested documents pre-ticked; On hand and Incoming SPO drill like reorder planning; locations in an expanded row, not a popover | 7 |

## 1. Loading plan becomes a record with a list

### What exists (verified 27 Aug)

- `/scm/loading-plan` is ONE page with ephemeral state (`LoadingPlanView.tsx:51-62`): supplier, plan-until date and document kind live in React state; `POST /container-requests/build` "persists nothing" (`container_requests.py:87`). Leaving the page loses the plan; two people cannot see the same plan; nothing to cancel or delete.
- The legacy `scm.loading_plan` table (migration 336, model `app/models/scm.py:1296`) still exists with CRUD on `fulfilment.py:439-566` (list by supplier, delete 204, notices), and `supplier_notices.loading_plan_id` already points at it. Its stage-2 columns (`container_cbm`, `capacity_cbm` NOT NULL, `planned_cbm`, `deferred_count`...) belong to the CBM-fit half that was cut; the UI never reaches it.
- The reorder revamp lane (`feat/scm-reorder-revamp`, Phase 1 built `2c0f809c5`) has the list design to copy: `ReorderRunsGrid.tsx` (DataGrid on `DataGridListToolbar`, whole-row click, `listingKey`, Start Plan CTA) and `RunPlanningModal.tsx` (field label "Sales order cut-off", hint "Empty = every open order counts.").

### Design

**R1. A loading plan is a row in `scm.loading_plan`, not a new table.** The table, its FK from `supplier_notices`, its list/delete routes and its tests exist; a second "container plan" table would be the same thing under a second name. Migration `441_loading_plan_lifecycle` (BUILT; renumbered from 440, which S6 took for the packing-list numbering seed, and chained onto it): add `status` (`planning | sent | cancelled`, default `planning`), `plan_horizon_date` DATE NULL, `document_kind` (`stock_list | proforma | none`), `source_attachment_id` UUID NULL (the file the plan was started from), `line_edits` JSONB NOT NULL default `{}` (`row_key -> qty`), `sent_at`, `cancelled_at`, `cancelled_by`; relax `container_cbm` / `capacity_cbm` to NULL (stage-2 leftovers). No plan number: the row is named by supplier + started time, exactly as a reorder run is.

**Two columns beyond that list, added while building.** `to_request_qty` and `to_request_cbm`. R3's grid prints a "To request" column "from the last build", and re-deriving it per listed row is one full suggestion run (about fifteen queries) per row of a 25-row page. The build stamps them on the plan it has just run; the figure is a cache of a derived number, never a decision. The stock-list snapshot DATE is pinned on the EXISTING `inventory_as_of` column at create time, which is what lets a newer stock list change an older plan's numbers (R2, stated in the open) without rewriting which file that plan says it started from (AC-A17). A proforma stand-in has no column of its own, so its number is read at display time.

**R2. The build is scoped to a plan.** `POST /api/v1/scm/container-requests/build` takes `plan_id` (as built, so do `POST /container-requests` and `POST /container-requests/document`); supplier and cut-off are read from the row and `line_edits` are applied to `suggested_qty` before the payload leaves (the "suggested" figure the engine computed rides along as `engine_qty` so the tooltip can still show the formula). The `{supplier_id, plan_horizon_date}` body form is retired: the page was its only caller. The supplier stock snapshot stays per supplier, replaced whole (S7 rule); a plan records which file it started from, and reads the supplier's CURRENT snapshot. Consequence, stated not hidden: uploading a newer stock list for the same supplier changes an older open plan's numbers. That is the correct reading (the plan asks for what the supplier holds now); a plan the buyer is done with gets cancelled.

**R3. The list.** `/scm/loading-plan` = DataGrid on `DataGridListToolbar`, `listingKey scm.dashboard.view::loading-plans`, `tableLayout fixed + columnsResizable`. Columns: Started (dd/mm/yyyy HH:mm, default sort desc), Supplier, SO cut-off, Document (Stock list dd/mm · Proforma invoice PI-x · No file), To request (qty, second line `est. N cbm`), Sent (channel icon + dd/mm HH:mm of the latest notice, `-` when none), Opened (dd/mm HH:mm of the latest open, `-`), Status pill (Planning / Sent / Cancelled). Search = supplier name. One Filters popover: Status (default chip "Active" = planning + sent; Cancelled shown on demand). Whole row opens `/scm/loading-plan/{id}`. Row actions column (same shape as `SalesOrdersGrid.tsx:677`, `stopPropagation`): **Cancel** (`ConfirmActionDialog`, "Cancel this plan? The supplier link stops working.") and **Delete** (`ConfirmDeleteDialog`, hard delete + cascade, refused with a stated reason when a notice was already sent: "Sent plans are cancelled, not deleted"). Backend: `GET /loading-plans` gains `page/limit/sort/dir/query/status` via `buildDataGridParams`; `POST /loading-plans/{id}/cancel`; `DELETE` keeps its 204 and gains the sent guard.

**R4. ONE Upload button, on the list, and the dropzone lives in the popup.** The list's only primary action is **Upload**. It opens "Plan a container": Supplier (server-searched `SearchableSelect`, required), **Sales order cut-off** (date, clearable, hint "Empty = every open order counts."; the words "Plan until" disappear everywhere), Document (radio: Stock list / Proforma invoice / No file). Choosing Stock list or Proforma invoice reveals the `FileDropzone` INSIDE the same dialog; the existing two-step (`useTwoStepUpload`: Test -> verdict card -> Confirm) runs in place; the separate `StockListUploadDialog` / `ProformaUploadDialog` are no longer hosted as a second dialog from here (they keep serving their own pages). Confirm = `POST /loading-plans` (creates the row) + the upload apply against that supplier + `router.push('/scm/loading-plan/{id}')`. "No file" = Start plan directly. Supersedes R22's two-step "Continue into the existing upload dialog".

**R5. The detail page is the plan, laid out like a record.** `/scm/loading-plan/{id}`: `Toolbar` with title = supplier name, subtitle "Started dd/mm/yyyy HH:mm · SO cut-off dd/mm/yyyy · Stock list dd/mm/yyyy" (or "Proforma invoice PI-x" / "No file") + status badge; prev/next record navigation; right cluster in this order: **[gear] [Save] [Send to supplier] [Back to loading plans]**. The header card of today (Supplier / Plan until / Upload / gear) is deleted; the "What to ask X to cover until d" heading keeps its title only, its Send button and gear move to the toolbar. The one gear holds: View uploaded list, Refresh matching, Refresh suggestion, Copy link, Download XLSX, Download PDF, Change cut-off, Cancel plan, Delete plan. Cancelled plan: grid read-only, Save and Send disabled with the reason. Supersedes R23's "Send to supplier stays beside the gear" placement (gear is now LEFT).

**R6. Save persists the typed quantities; Send saves first.** Save = `PUT /loading-plans/{id}/edits` with the whole `{row_key: qty}` map, one transaction, `Save (N)` counts rows whose qty differs from `engine_qty`; disabled at 0. Send to supplier runs the same PUT before the send, so the document and the screen never disagree. Leaving with unsaved edits asks (the users-page unsaved prompt). Refresh suggestion clears edits after a confirm ("Drop your N typed quantities?").

## 2. Eight columns open the standard lightbox

**R7. One `PlanRowDialog` for the SCM family.** Copy the shell from the revamp lane (`scm/reorder/components/PlanRowDialogs.tsx:603-660`: `DialogContent sm:max-w-[95vw] max-h-[85vh]`, `Th/Td/DocTable/EmptyRow/LoadingRows`) into `app/(protected)/scm/components/PlanRowDialog.tsx` with a `kind` union and a `body` registry per screen. At merge, the revamp lane re-points its import to the shared file (one owner, agreed with that lane). Popovers (`SoLinesDrillPopover`, `ContainerRequestHistoryPeakCell`'s Popover) are replaced; `PopoverPortal` pinning workarounds go with them. R3 of part 3 (Dialog, not Popover) already ruled this for the row breakdown.

Loading plan kinds and their data:

| Column | Kind | Body | Data |
|---|---|---|---|
| Project | `project` | tabs Open project SO lines (n) · 12-month history; columns Sales order, Customer, Project, Agent, Price, Qty, Required; total row | open = build payload (`include_lines`, R15 read); history = history payload |
| Retail | `retail` | same shape, retail + unclassified lines | build payload + history payload |
| Project peak / Retail peak | `project` / `retail` opened on the history tab | the two 12-month series, peak month named | history payload (exists) |
| On hand | `on_hand` | reorder planning's On hand lightbox verbatim: Location, On hand, Reserved, Free, SO qty, SPO qty, Available, PO qty, › documents, "Stock as of"; site pools only, total = cell | `GET /reorder-runs/location-stock?product_id=` (product-only, reused as-is) |
| SPO | `spo` | tabs Open to pools (n) · History; columns SPO, Packing list, To, Qty, Received, ETA, Status | NEW drill endpoint over **`spo_allocations`** (the `spo_pool` rows), not the PO table |
| Incoming PL | `incoming_pl` | Packing list, Container, Supplier, Qty, ETA, Status; opens the packing list | NEW drill endpoint over unreceived `inbound_shipment_lines` |
| PO | `po` | tabs Open (n) · History; columns PO, Supplier, Qty, Still to come, Unit price, Issued, ETA, Status | NEW drill endpoint over `purchase_order_lines` |

Captain (27 Aug, artifact): these dialogs follow reorder planning's lightboxes (revamp lane `PlanRowDialogs.tsx`) and the fulfilment board's drawer; the SPO planner reuses On hand and SPO (R21).

**R8. One drill endpoint, not three.** `GET /api/v1/scm/container-requests/drill?supplier_id&product_id&kind=spo|incoming_pl|po` returns `{kind, rows[], total}`; each is the row form of the SUM the cell shows, so the number in the cell and the rows in the dialog come from one predicate. Set rows drill on the driver member (R19). The revamp lane's Phase 2 will want the same SPO/PO rows run-scoped; whichever lands first, the other calls it.

**R8a. SPO reads the purchase-order table.** Captain (27 Aug): "we need to standardize and take from the purchase order table cause we will allow the upload of SPO to purchase order table". So the SPO cell and its lightbox read SPO-kind rows of `purchase_orders` / `purchase_order_lines` (today the planner-created SPOs are the lines carrying `source_ref`, R9 of part 3; the SPO upload lane lands uploaded SPOs on the same table with the same kind marker), bound for a site pool, open first then received. `_stock_context.incoming_spo` moves off `net_position.on_order` / `spo_allocations` onto this reader in S2 Phase 2, and the guard test AC-H1 re-baselines the From SPO card on that read. PO and SPO share one reader keyed by kind.

## 3. Send to supplier: channel, recipients, opens

### What exists

- `request_and_notify` (`supplier_notice_service.py:557`) writes one notice per channel EVERY send; the chat row is always `skipped` ("No chat channel is linked to this supplier yet.", `:876-883`). Email goes solely to `suppliers.email` (`:886-892`); no way to add an address. Nothing records an open: the public page (`public_request_page`, `:740`) is a pure read.
- Respond.io sends need a `RespondContact` (`respond_outbound_service.find_contact`), and a text outside the 24-hour window must go as a template (the composer's smart-send rule, `feedback_respond_send_always_logs_outbox`).

### Design

**R9. The send is a dialog with a channel.** "Send to supplier" opens "Send this request" (replaces the bare AlertDialog): radio **Email** / **Chat**. Email: **To** = address chips, prefilled with `suppliers.email`, the user adds or removes addresses (validated, at least one), optional note line. Chat: a Respond.io contact picker (server-searched over `respond_contacts`, prefilled with the contact whose phone equals `suppliers.phone_number` when one exists), otherwise "No chat contact for this supplier yet" with the picker still usable. Confirm sends on the chosen channel ONLY: one notice row per send, `channel` = the choice, new column `recipients` JSONB (email addresses, or the respond contact id + name). The always-written skipped chat row goes. Migration `441_supplier_notice_recipients_opens`.

**R10. Chat = WeChat, through the composer's send path, not a new one.** Captain (27 Aug): "chat should be using wechat" (suppliers are in China). The chat row is the supplier's WeChat contact on the Respond.io WeChat channel (Respond.io offers WeChat Official Account as a channel; whether the Sorento workspace has one connected is verified in S3 Phase 2 before the send path is wired, and stated in the PR if it does not). The picker lists Respond.io contacts on that channel, prefilled by the supplier's phone. The send calls the same outbound service the unified composer uses (text + link inside the window, the approved template outside it, outbox row always logged), with the xlsx as the media attachment where the channel allows and the link in the text either way. If no approved template exists or no WeChat channel is connected, the send is refused with that reason and the notice reads `failed`; connecting the channel / seeding the template is a Respond.io task (needs the captain's go, n8n rule).

**R11. Opens are tracked on the notice.** `GET /api/v1/public/supplier-request/{token}` stamps the notice(s) carrying that token: `opened_at` (first), `last_opened_at`, `open_count += 1`. That is a write on a GET by design (it is the tracking); it never blocks the page (best-effort, own short transaction). Surfaced: list column Opened, the Requests sent card ("Opened 3 times, last 27/08 15:10" or "Not opened yet"), and the plan status stays `sent` (no `opened` status: a status is a decision, an open is an event). Document downloads through the token count as opens too (same handler family).

## 4. The supplier document is THEIR sheet

### What exists

- xlsx (`container_request_xlsx.py:120 _with_qty_to_load`) replays the retained stock list's VALUES and appends `需装数量 / Qty to load`; merges, fills, fonts, widths and the title row do not survive, and the fallback is a five-column sheet of our own. PDF (`_document_html`, inline HTML) and the public page (`page.tsx:185-192`) carry six columns of our own naming. Three renderers, three shapes.
- The reference `库存明细.xlsx`: title row A1 "金百川库存表 2026年7月27日" (Calibri 22 bold, merged, 39.75pt), header row 2 (Calibri/宋体 14 bold, centred, borders): 序号 / 型号 / 商标 / 规格 / 品名 / 包装好库存 / 空瓷 / 体积(cbm) / 总体积(cbm) / 备注; data rows 18.75pt, 宋体 14 centred, B:G and J filled yellow `FFFF00`, a zero in 包装好库存 in red font; **a product family is one 序号: A, H (体积) and I (总体积) are merged down the family's rows** (`A3:A11`, `H26:H27`, `I3:I11`...); last row `合计：` with `=SUM()` on F, G, I (red, 18/14pt); widths A 6 / B 28.7 / C 10.1 / D 12.7 / E 13.3 / F 13.4 / G 19 / H 13.7 / I 17.1 / J 13.9.

### Design

**R12. One sheet model, three renderers.** `supplier_document_model.py` builds `SheetModel{title, columns[10+1], rows[], merges[], totals}` once; `xlsx`, PDF and the public page render it. Rows carry `family_span` so a merged 序号/体积/总体积 becomes `rowSpan` in HTML and a merge range in openpyxl. Column 11 = `需装数量 / Qty to load`, styled as column J (yellow, 14pt, bordered), header bold; a 0 ask leaves the cell empty (AC-C3 stands). Requested rows not on their list are appended below the last family, own 序号 continuing the count, same styling, `备注` = "不在库存表 / Not on your list". The `合计：` row keeps their three sums and adds the sum of column K.

**R13. With a retained stock list the xlsx IS their file.** `_with_qty_to_load` loads the retained workbook with openpyxl and writes column K into it (header + cells + total), leaving every existing cell, merge, width, fill and font untouched; appended rows copy the style of the row above. Set lines print the supplier's own code (AC-F12.6). The PDF and the public page render the same model with the same fonts (宋体/Calibri stack), fills and merges; the public page keeps its bilingual header labels as a second header line under theirs. Without a retained file (PI stand-in, no file): the model is built from our data in the same 10+1 columns, no merges (we hold no family information), 商标 = the product's company letter (S / C / M), 规格 = the product's size where known, 品名 = product name; the old five-column fallback is deleted. A golden test opens `库存明细.xlsx` (committed fixture), runs the builder, and asserts merges, fills, fonts, widths, the title row and column K.

## 5. Proforma invoices list: Start

**R14. One CTA "Start" with two items, Delete under a gear on its left.** Toolbar right cluster: **[gear] [Start ▾]**. Start menu: "Upload proforma invoice" (opens the two-step upload, R24) and "Convert N to packing list" (disabled with reason "Select invoices first" until rows are ticked; N = ticked count). Gear (`aria-label="More actions"`): "Export" (selection-gated, today's client export) and "Delete N" (destructive, `AlertDialog`, disabled without selection). The selection strip keeps "N selected · Clear" only; the bulk buttons "Convert N to draft shipment" and "Delete N" leave it. The words "draft shipment" disappear from this screen (toasts read "Packing list PL-2608-003 created with 12 lines").

**R15. Convert from the list proceeds directly.** No dialog: every ticked current, un-converted invoice places what it has left into ONE NEW draft packing list; result = toast + navigate to the packing list (skipped invoices named in the toast, as today). The only interruption is capacity: a 409 `over_capacity` opens the existing `OverCapacityDialog` ("This will not fit", reason required, "Convert anyway"). `ConvertToPackingListDialog` is removed from the list; the PI DETAIL keeps its Convert with the per-line quantity editor, because a partial placement (Q9 split) is a deliberate act made on one invoice. **"Add to existing draft" is dropped everywhere** (captain, Q6): `target_shipment_id` leaves the convert request, `useDraftShipments` and the target select go; a PI always opens a new draft.

## 6. Packing list fixes

**R16. The draft number comes from a numbering rule, never a random hex.** `SHIP-DRAFT-46949e1c` is the fallback at `proforma_invoice_service.py:972-976` firing because no `document_numbering_rule` row exists for `inbound_shipment_draft`. Migration `442_seed_inbound_shipment_draft_numbering` seeds `PL-{YYMM}-{NNN}` (monthly sequence, company-scoped like 279's SCM decision rule); the random fallback is deleted, the service raises `AppException(code="numbering_rule_missing")` instead. `create_shipment` without a number uses the same rule (AC-F3.3 stands). The user renames the shipment number to the container number when the container is known (Details tab, editable, unchanged).

**R17. Conversion writes no notes.** `_draft_notes` ("Draft from proforma invoice(s): ...") is deleted; provenance lives on the Proforma invoices tab (AC-F3.2) and the Timeline. An over-capacity override keeps its reason: it becomes the Timeline entry "Converted over capacity: <figures>. Reason: <text>" (audit log row on the shipment, `__audit_track__` exists), not a notes string. `notes` stays the user's own field.

**R18. Supplier selects show the name only.** `SupplierCombobox` label = `supplier_name`; `searchText` keeps the code so typing a code still finds it. Applies to the packing list Details tab, `/new`, the Shipment lines per-line factory select and the PI detail supplier select (same component).

**R19. Edit stays on the tab it was pressed on.** On `/lines`, Edit puts the Shipment lines tab in edit mode in place and Save/Cancel leave the route unchanged; same for Details. Phase 1 reproduces the jump in the browser first (no redirect is visible in `layout.tsx`; the tab bar re-mounting or the pager is the suspect) and the fix lands with the AC.

**R20. The packing-list workbook prints the shipment and nothing else.** The `not_packed` rows ("Not packed - loading plan asked N", `consolidated_packing_list.py:642-653`) and the derived remarks (`NOT_ON_PLAN`, "Loading plan asked X, packed Y", `:188-206`) are deleted; REMARKS = the supplier's own remarks. A fidelity test opens `FSCU8103365.xlsx` (committed fixture) and asserts, cell by cell against a shipment built from that file: the 12-row header block, the two-row column header (labels, merges `I15:K15`, `A15:A16`...), widths (A 18.9, C 27.9, D 45.9, S 29.3...), row heights (data 35.1, subtotal 15.95), fonts (Calibri 12, bold header, bold red subtotals), number formats (`0.00;[Red]0.00` on L/M, `#,##0.00` on U, dd/mm/yyyy on B1:B3), formulas, the V-column block amount merged down the block, the `-` rule row, the SORENTO/MOCHA footer rows and the 订单号/柜号/封号 lines. Every difference the test finds is fixed in the builder.

## 7. SPO planner redesign

### What exists

`SpoPlannerTable.tsx` (1,371 lines): PO covers and SO covered are Popovers with checkboxes; On hand and Incoming SPO are static numbers; Location is a Popover holding the destination rows and the "What this covers" block; the row's only expansion is the info tooltip on a `reason`.

### Design

**R21. Four cells open the lightbox.** PO covers -> `PlanRowDialog kind="po_takes"`: the PO candidates (issue date ASC, R-Q8), a checkbox per row, the suggested takes PRE-TICKED, qty taken per row, footer "n of m POs · covers X of packed Y"; ticking feeds the same client cascade (`cascadeTake`) as today. SO covered -> `kind="so_coverage"`: open demand lines, project first then retail (AC-G3), pre-ticked to the packed quantity, "Unassigned N" footer. On hand -> `kind="on_hand"` (the location table, `useLocationStock`, site pools first). Incoming SPO -> `kind="spo"` (the R8 drill rows). The two Popovers are deleted; `SpoPlannerTable` shrinks to the grid and the dialog requests.

**R22. Locations live in the expanded row, full width; coverage lives in the SO covered lightbox.** Each line expands (chevron in the Location cell; cell text = "No location" / `BRW` / "3 locations", second line "N unassigned" as today). The expanded area is a small table: destination rows (warehouse `SearchableSelect`, qty input, remove), an "Unassigned" row (remainder, read-only, turns destructive when the split exceeds the SPO qty), "Add location". The "What this covers" list is NOT in the row: captain (27 Aug) wants SO coverage in the lightbox like PO covers, so the SO covered dialog carries per-line Location and the Unassigned footer. Toolbar gains Expand all / Collapse all (the revamp lane's `leftActions` prop on `DataGridListToolbar`, copied; deduped at merge). `LocationSplitPopover` is deleted. The split model and validation (`splitMismatch`, `overTicked`) are unchanged.

## 8. Slices, order, slots

Phase 1 (FE against mocks, browser-verified) then Phase 2 (BE test-first) per slice. Two coder slots.

| Slice | Content | Days | Slot |
|---|---|---|---|
| S1 | R1-R6: migration 441, plan row + list + Plan-a-container dialog with the dropzone, detail toolbar, Save/edits, cancel/delete **(BUILT)** | 4.5 | A |
| S2 | R7-R8: shared `PlanRowDialog`, eight lightboxes, drill endpoint | 3.5 | A |
| S3 | R9-R11: send dialog, recipients, chat via composer path, open tracking, migration 441 | 3.5 | A |
| S4 | R12-R13: sheet model, xlsx-is-their-file, PDF + public page, golden test | 3 | B |
| S5 | R14-R15: PI Start ▾, gear, direct convert | 1.5 | B |
| S6 | R16-R20: numbering seed 442, no notes + timeline reason, name-only supplier, edit-on-tab, workbook extras + fidelity test | 3 | B |
| S7 | R21-R22: SPO planner lightboxes + expanded-row locations | 3 | B |

~22 dev-days. Order A: S1 -> S2 -> S3. Order B: S6 -> S4 -> S5 -> S7 (S6 first: two of its items are verified defects). Migration chain as built: 438 (main's head at branch time) -> `440_pl_draft_numbering` (S6) -> `441_loading_plan_lifecycle` (S1). S3 and S4 take the next ids; re-check `alembic heads` before each migration commit. Dev DB: apply DDL via `Operations.context`, never stamp (shared-DB rule).

## 9. Cross-lane facts

- **Reorder revamp** (`feat/scm-reorder-revamp`): owns `PlanRowDialogs.tsx` and the `leftActions` toolbar prop today. R7 copies the shell into `scm/components/`; at whichever merge comes second, the copy is deduplicated (one file). Its Phase 2 SPO/PO endpoints are run-scoped; R8's is product-scoped; both may exist.
- **Inline decisions** (#355) touches the fulfilment board, not these screens.
- **#327 #328 #330 #335** stay open; nothing here closes them.
- The `PlanContainerDialog.test.tsx`, `ContainerRequestSection.test.tsx`, `LoadingPlanView.test.tsx` suites are rewritten with S1/S2 (the components they test change shape); `SpoPlannerTable.test.tsx` with S7; `test_container_request_xlsx.py` + `test_consolidated_packing_list.py` with S4/S6.

## 10. Rejected alternatives

- New `container_plan` table (R1): a second table for the row `loading_plan` already is; the FK from `supplier_notices` would have to be duplicated.
- `opened` as a plan status (R11): an open is an event that repeats; the status would flip back and forth or lie.
- Keeping both channel rows per send (R9): the chat row was `skipped` on every send since 343; a row that always says "not done" is noise.
- A Respond.io send path of our own (R10): the composer's path already handles window, template, outbox and errors; a second one would diverge on the first bug.
- Direct convert on the PI detail too (R15): the detail is where a buyer places PART of an invoice (Q9); the quantity editor is that act's only surface.
- Per-family merges for the no-file document (R13): we do not know the supplier's families; inventing them would be wrong on the first product with two sizes.

## 11. Rulings from the captain (artifact round 2, 27 Aug)

| # | Ruling |
|---|---|
| Q1 | Asked quantity = appended column K `需装数量 / Qty to load`; their ten columns untouched (R12 stands). |
| Q2 | Draft packing list number = `PL-YYMM-NNN`, monthly sequence (R16 stands). |
| Q3 | Email + chat both in S3; chat = WeChat via Respond.io; connecting the channel / seeding the template is a separate Respond.io task with its own go (R10). |
| Q4 | Cancelling a plan retires the live supplier link (R3 / AC-A8). |
| Q5 | A sent plan cannot be deleted; cancel instead (R3 / AC-A9). |
| Q6 | "Add to existing draft" is dropped everywhere, list and PI detail (R15). |
| Q7 | Empty Sales order cut-off = every open order counts, same words as reorder planning (R4). |
| A1 | SPO figures and lightbox read the purchase-order table; one reader for PO and SPO (R8a). |
| A2 | SPO planner expanded row = destinations only, full width; coverage in the SO covered lightbox (R22). |
| A3 | Gear items on the loading plan record confirmed (R5). |
