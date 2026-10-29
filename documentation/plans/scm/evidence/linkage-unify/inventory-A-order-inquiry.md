# inv-A: order inquiry (OI) domain, "where are this SO line's goods now"

Worktree /Users/tehjayson/Documents/foundryx/sorento_crm-linkage-unify at origin/main 263643ae36. Read-only scout. All paths relative to `sorento_crm_backend/` (BE) or `sorento_crm_frontend/` (FE). Line numbers verified against this checkout.

Abbreviations: PS = `app/services/project_order_inquiry_service.py`, WS = `app/services/order_inquiry_worklist_service.py`, IS = `app/services/project_order_inquiry_import_service.py`, SS = `app/services/scm/spo_supply.py`. "Link" = `projects.order_inquiry_links` row (`OrderInquiryLink`), exactly one of `po_line_id` / `spo_allocation_id` (or `reserve_request_row_id`). "Transferred PO line" = a PO line whose `qty_received` has been set by AutoCount to mean transferred to an SPO.

## 0. Facts that frame everything

F1. A link names ONE target and never changes target when AutoCount transfers the PO line to an SPO. Nothing in the OI domain rewrites `po_line_id` -> `spo_allocation_id`. Confirmed by grep of every writer of `spo_allocation_id` on links:
  - `_write_link` PS:11349-11422 (the one creator; callers: dialog `place_on_po_allocations` PS:11898, `_place_on_po_set` PS:12051, cascade, `follow_book_for_rows` PS:3738).
  - `repoint_allocation_dependants` `app/services/rules/shipping_order_rules.py:825-885` (called `app/services/shipping_order_ingest_service.py:1211`): SPO line to SPO line only (xlsx-era supersede/dedupe), never PO to SPO.
  - `relink_to_matching_lines` PS:13195-13352: PO line to a sibling line of the SAME PO (warehouse fit), never to an SPO.
  - `follow_book_repairing` / `_follow_one_move` PS:3415-3620: reacts to a change of `from_so_line_ref` (which SO line the target names), never to PO to SPO transfer.
  - `scripts/convert_oi_cascade_links.py`: one-time conversion of cascade links to suggestions.
F2. PO to SPO is only followed at LINK CREATION time, by `follow_book_for_rows` (PS:3738-3982) -> `pair_needs` (IS:2160) -> `_through_po` (IS:2310) over `_chain_allocations` (IS:2020-2078). It only touches rows with unlinked need left (`_unlinked_need`, PS:11342, check at PS:3893-3897). PLAN-oi-follow-book-chain D2 ruled "shipping order first, PO line for the remainder", and the plan text (documentation/plans/scm/PLAN-oi-follow-book-chain.md line 140) states: "A row already FULLY linked to a document the book does not name is never corrected ... LEFT AS IS". So a row placed on the PO line BEFORE the transfer stays on the PO line forever (the OI-2609-0128 case).
F3. Two meanings of "received" are hard-wired as one test: PO line `qty_received >= qty_ordered` (> 0) or `line_status == 'closed'`; SPO line = NOT `open_incoming_clauses` (line closed, receipt_status received, or shipment landed). Neither looks at the other book. A transferred PO line therefore reads "received" even while its SPO is on the water.
F4. Exactly ONE place asks "is there an open SPO chained from this PO line" for the received decision: `po_lines_with_open_chained_spo` PS:13453 (reserve/"Request CS to reserve" only).

## 1. Master table of readers (one row per reader)

Columns: id | screen/consumer | file:line + function | SO line / OI row to PO or SPO | PO line to SPO (match key) | states counted/shown | quantity used | difference from the others.

### R1 links_for_rows (the "one reader" for every OI link display)
- screen: OI Lines tab (OI header `[id]` page), per-project OI list (`serialize_rows`), cross-project worklist (`list_rows`, `_all_rows`/export), SCM sales-order detail "Linked to" (`sales_order_service._line_links` app/services/scm/sales_order_service.py:861-935), fulfilment board OI chip documents (`project_fulfilment_board_service.py:2307-2380`).
- where: PS:8081-8389 `links_for_rows` (+ follow-ups 8352-8389, derived call at 8388).
- row to target: `OrderInquiryLink.row_id` outer-joined to `PurchaseOrderLine` on `po_line_id` (PS:8152) and `SPOAllocation` on `spo_allocation_id` (PS:8157). Drops cancelled rows (PS:8168-8172), reserve links (`reserve_request_row_id IS NULL`, PS:8173-8180), retired-and-never-received SPO lines (`visible_line_clauses`, PS:8186).
- PO to SPO: NONE for a real PO link. A real SPO link exposes `source_po_number = SPOAllocation.from_po_number` (PS:8333) and `derived_po = bool(from_po_number)` (PS:8338); `purchase_order_id` is resolved by (a) `SPOAllocation.po_line_id` FK follow-up (PS:8341-8359) else (b) `PurchaseOrder.po_number IN from_po_number` (PS:8361-8382). The PO-link to SPO direction is delegated to R2.
- states: per link `received` (PS:8254-8284): SPO link = NOT (line_status null/open AND receipt_status not in RECEIVED_RECEIPT_STATUSES AND shipment `actual_arrival_date` null); PO link = `line_status == 'closed'` OR (`qty_ordered > 0` AND `qty_received >= qty_ordered`). No "partly received" boolean; a partly received doc is `received=False` with `received_qty` stating the figure.
- quantity: `qty` = link.qty; `received_qty` = SPO `quantity_received` or PO `qty_received` (PS:8271, 8283).
- differs: it is the only reader that exposes BOTH `received` and `received_qty`, and it computes received per link without consulting the chain (F3). Output feeds the pills in FE (section 3).

### R2 _append_derived_spo_entries (the "SPO" column text for a PO-placed row; the OI Lines tab SPO "-" cause)
- screen: same surfaces as R1 (it appends synthetic `derived: true` entries into R1's output, PS:8388).
- where: PS:8391-8503; clause set `derived_spo_open_clauses` PS:366-386.
- row to PO line: only PO-KIND real links with a PO number, a non-blank `source_ref` and a product (`po_pairs_by_row`, PS:8238-8243, built in the R1 loop).
- PO line to SPO: `SPOAllocation.from_po_number == po_number` AND `btrim(SPOAllocation.from_po_line_ref) == strip(PurchaseOrderLine.source_ref)` AND `SPOAllocation.product_id == PurchaseOrderLine.product_id` (tuple IN, PS:8429-8449). Company predicate added by hand (PS:8425-8427). OI-SPO-EXACT.
- states shown: ONLY open and unlanded: `retired_at IS NULL` AND `allocated_quantity > coalesce(quantity_received,0)` AND `open_incoming_clauses` (line_status null/open, receipt_status not received/fully_received, shipment not landed). So: open yes, in transit yes, partly received yes (balance > 0), landed no, fully received no, closed no, cancelled(closed) no, retired no.
- quantity: open balance `allocated - received` (PS:8466), NOT the link qty and NOT capped at the PO link qty (the worklist cards cap it, R5).
- differs: shows the SPO only while incoming, so after the 486/486 receipt the entry vanishes and the SPO column reads "-". The entry has no `received`/`received_qty` keys (so FE `received` is false). Not de-duplicated against a real SPO link on the same row in this display (the cards do: R5 `already_linked_for_real`). UNVERIFIED in a live case, read from code.

### R3 _received_documents_for (the OI engine's own "received" test, separate copy of R1's test)
- where: PS:3346-3412. Callers: `_redirect_row_if_received` PS:3233/3266 (replan, creates "used" rows, sets `redirected_to_pool` PS:3296); `_release_fragment` PS:3318/3330 (note "doc received <date>"); `_split_line_rows` PS:6382, `_asked_qty` PS:6417; zero-qty settle `supply_landed` PS:2672 (EMAIL-SO-CHANGES: fulfilled vs withdrawn); `_movable` reallocate-on-book-change PS:6825; `received_links_of` PS:13495; import `_move_received_links` IS:2929-2985; `planning_change_service.py:1604` (R17).
- row to target: link `po_line_id` / `spo_allocation_id` directly.
- PO to SPO: none.
- states: identical boolean to R1 (PO: closed or qty_received >= qty_ordered > 0; SPO: not open per 3 tests). Returns link id -> SPO shipment `actual_arrival_date` (None for PO).
- quantity: boolean only.
- differs: duplicate implementation of R1's received logic (copy, not shared function; PS:8254 vs PS:3376/3399). If the transferred-PO case is fixed in one it must be fixed in both. Notably drives "used" (redirected_to_pool) decisions, so a transferred PO line is treated as landed stock in a replan even if the SPO is still at sea.

### R4 received_links_of + po_lines_with_open_chained_spo (reserve-received, "Request CS to reserve", OI-RESERVE-RECEIVED #1708)
- screen: CS reserve request/answer (`order_inquiry_reserve_service.py:_requestable` 122-145, `release_received_links` call 923), worklist `reserve_requestable_qty` (WS:2395-2420 via `blocked`).
- where: PS:13453-13485 (`po_lines_with_open_chained_spo`), PS:13487-13503 (`received_links_of`), PS:13505-13554 (`release_received_links`); WS:1742 builds `blocked`.
- row to target: link ids.
- PO to SPO: `SPOAllocation.from_po_number == PurchaseOrder.po_number` AND `SPOAllocation.from_po_line_ref == PurchaseOrderLine.source_ref` (exact equality, NO btrim, NO product_id) AND `SPOAllocation.company_id == PurchaseOrderLine.company_id` AND `source_ref` non-blank (PS:13463-13476). Also `open_incoming_clauses` AND `visible_line_clauses` (NOT `derived_spo_open_clauses`: no `retired_at` test, no `allocated > received` test).
- states: a PO line counts as "received" only if R3 says so AND NO open (line open, receipt not received, shipment not landed, visible) chained SPO exists. Partly received SPO still blocks only if the 3 tests pass (no quantity test), so an SPO fully received by quantity but with `receipt_status` still 'pending' and no shipment arrival date blocks.
- quantity: link qty released/credited whole.
- differs: the ONLY reader that treats "PO line reads closed but goods have not landed" correctly (docstring PS:13453-13457 says exactly that). Different key spelling from R2/R5/R9 (no btrim, no product). WS:1747 collects `blocked` only for links already `received`, and WS:2410 only subtracts them in `reserve_requestable_qty`; the received PILL (R20) ignores `blocked`.

### R5 worklist derived-SPO SQL + stage cards + kind/linked/spo_number filters
- screen: worklist cards (Incoming SPO / On PO / Buy), Schedule matrix, filters `linked=spo`, `kind=spo`, `kind=po`, `spo_number`.
- where: WS:1108-1170 `_derived_spo_query`, 1172 `_has_derived_spo`, 1179-1212 `_derived_cover_qty`, 1214-1223 `_incoming_qty`, 1225-1241 `_purchased_qty`, 3066-3125 `_stage_rows`, 3143-3175 `_kinds`, 3350 `matrix`; filter call sites WS:1421 (linked=spo), 1452 (kind=spo) and 1454 (kind=po), 1544 (spo_number).
- row to target: EXISTS over the row's PO links (WS:1135-1151), so one allocation counts once per row (AC-D12).
- PO to SPO: `from_po_number == PurchaseOrder.po_number` AND `btrim(from_po_line_ref) == btrim(PurchaseOrderLine.source_ref)` AND source_ref non-blank AND `product_id` equal (WS:1138-1146); company predicate by hand. Same key as R2 (btrim both sides vs strip in Python, equivalent).
- states: `derived_spo_open_clauses()` (the same shared function as R2): open/in transit/partly yes; landed, fully received, closed, retired no.
- quantity: derived cover = `sum(allocated - received)` over matching open allocations excluding allocations the row already links for real, capped at the row's own PO-linked qty (`_incoming_qty` = least(qty, spo_linked + least(po_linked, cover)); `_purchased_qty` = least(qty - incoming, greatest(0, po_linked - capped cover))).
- differs: once the SPO lands (486/486), cover = 0, so the 486 moves from the "SPO/Incoming" stage back to the "PO" (purchased) stage, i.e. goods that are physically in stock are counted as "On PO, not yet shipped". There is no received stage in the cards. `_kinds` drops only cancelled/actioned/redirected rows (WS:3157-3158), not received ones.

### R6 worklist PO NO / Supplier / Location columns (and Excel PO NO)
- screen: worklist "PO no", "Supplier", Excel export column "PO NO " (WS:3801), "Supplier" sort/filter.
- where: WS:279-333 (`_LINKED_PO_ID`, `_SPO_LINKED_PO_ID`, `_SPO_REF_PLACED_PO_ID`, `_PLACED_PO_ID`), joins WS:1347-1360; supplier fallback `_SPO_LINKED_SUPPLIER_ID` WS:336-348 via `spo_supply.supplier_id_for` (SS:128-157).
- row to target: first link by `linked_at`: via PO line; else the SPO link's `SPOAllocation.po_line_id` FK; else row `spo_ref` -> `SPOAllocation.spo_number == spo_ref` -> `po_line_id`.
- PO to SPO: none for `po_number`. `from_po_number` is NOT used here (so a book-fed SPO link, `po_line_id` NULL, shows no PO number in this column; the FE PO cell instead reads `source_po_number` from R1). Supplier does use `from_po_number` (via `supplier_id_for`: `po_line_id` FK first, else `PurchaseOrder.po_number == from_po_number` in same company, else the allocation's own supplier).
- states: none (no received/landed test).
- quantity: none.
- differs: Excel "PO NO" and the sort/filter can disagree with the FE PO cell on a book-fed SPO link.

### R7 worklist sort key spo_number
- where: WS:366-376 (`_OWN_LINKED_SPO_NUMBER`, `_SPO_SORT_KEY`), sort map WS:857.
- row to target: first real SPO link, else `row.spo_ref`. Ignores derived entries (documented as an accepted difference, WS:350-365).
- differs: sorts by a different value than the SPO cell prints.

### R8 worklist po_number filter
- where: WS:1516-1531 (`po_number` branch).
- matches PO-link `document` prefix OR an SPO link whose `SPOAllocation.from_po_number` prefix matches. No derived-SPO or PO-line chain involvement; no state test.

### R9 PO popup (get_po_detail) + _spo_numbers_by_po_line
- screen: worklist "PO no" lightbox `OrderInquiryDocumentDialog.tsx` kind=po, SPO column in that dialog (FE:434-454).
- where: WS:2595-2714 `get_po_detail`; WS:2716-2757 `_spo_numbers_by_po_line`.
- row to target: `allocated` per PO line = sum of non-cancelled OI links by `po_line_id` (WS:2650-2664); "Allocated to" panel `_allocations_on(po_line_ids=...)` WS:2893-2968 (PO-line links ONLY, so rows placed on the chained SPO are not listed).
- PO to SPO: `SPOAllocation.from_po_number == po.po_number` AND `btrim(from_po_line_ref) == btrim(PurchaseOrderLine.source_ref)` AND `SPOAllocation.product_id == PurchaseOrderLine.product_id` AND source_ref non-blank AND company predicate (WS:2735-2747). Same key as R2/R5.
- states: `visible_line_clauses` ONLY, i.e. every state except "retired and never received": open, in transit, landed, partly, fully received, closed all shown (WS:2745). No open test.
- quantity: PO line `qty_ordered`, `qty_received` (labelled received but means transferred), `remaining = ordered - received` (WS:2681-2682). No SPO quantities.
- differs: this is the reader that shows the SPO (SPO-2026/09-0107) for OI-2609-0128 while R2 hides it. It states SPO NUMBERS only, with no status.

### R10 SPO popup (get_spo_detail)
- screen: worklist "SPO no" lightbox (`OrderInquiryDocumentDialog.tsx` kind=spo; `highlightLines`).
- where: WS:2759-2891.
- row to target: `_allocations_on(spo_allocation_ids=...)` (WS:2893): links by `spo_allocation_id` only.
- PO to SPO: reverse only: shows `source_po_number = from_po_number` per line (WS:2879-2885). `from_po_line_ref` is never sent.
- states: `visible_line_clauses` (all except retired-never-received).
- quantity: `allocated`, `received = quantity_received`, `remaining = allocated - received` (WS:2866-2872). ETA = min `expected_date`; container from the first shipment.
- differs: rows placed on the PO line instead of the SPO do not appear in "Allocated to" here, and rows on the SPO do not appear in the PO popup.

### R11 Candidate walk / Link dialog / cascade capacity (PO candidates ~10382, "SPO candidates")
- screen: Link dialog (`po_candidates_for_row`), auto-link cascade (`auto_place_for_products` PS:12535), `has_link_candidate` flag (`link_candidate_products` PS:13692), `_place_on_po_set` validation (uses `_candidates_including_own_closed_links` PS:10555).
- where: PS:10272-10553 `_candidates_for_row` (PO query PS:10375-10388, remaining PS:10416-10422; SPO query PS:10463-10477, remaining PS:10480-10484), PS:10555-10687, PS:11187-11320 `po_candidates_for_row`, PS:13692-13806; netting `_linked_by_target` PS:10000-10050 (links + released links per target id), suggestions `_suggested_totals_by_target` PS:11502.
- row to target: product match (`_resolve_product_id`), verb `_SPO_LINKABLE_VERBS`.
- PO to SPO: NONE. PO and SPO candidates are independent lists; no key connects a PO line to the SPO it became.
- states: PO candidate: `line_status == 'open'`, `PurchaseOrder.status in (active, partial)` (unless manual), po_number not like 'SPO-%'; remaining = `qty_ordered - qty_received - links - released` > 0. SPO candidate: `open_incoming_clauses` + `spo_number NOT NULL`; remaining = `allocated - received - links - released` > 0; non-manual only at pool locations (R11 rule, PS:10494-10510). A forced entry (`line_open False`) re-adds a closed/inactive target the row already holds (PS:10599-10687).
- quantity: remaining as above; `qty_received` (PO) means transferred.
- differs: BECAUSE links on a PO line are keyed by PO line id and the SPO's `_linked_by_target` entry is keyed by SPO allocation id, 486 units placed on the PO line do NOT reduce the chained SPO allocation's `remaining`. After transfer the PO line drops out (qty_received >= qty_ordered) and the SPO appears with its full 486 free, so another OI row can be linked to the same physical goods. The importer avoids this with `_less_own_shipments` (R12) but the live walk has no equivalent. UNVERIFIED in a live case, read from code.

### R12 follow_book_for_rows / pair_needs / chain (the only place PO to SPO is followed when creating links)
- screen: AutoCount ingest hooks (`app/api/v1/external/ingest.py` PO hook 723, SPO hook 814, `follow_book_repairing` 557/619), cascade book step, `scripts/backfill_oi_follow_book.py`, OI sheet importer (`apply`, `_pair` IS:2373).
- where: PS:3738-3982; IS:1849-1921 `_target_facts`, IS:1923-1987 `_bought_rows`, IS:2020-2078 `_chain_allocations`, IS:2081-2121 `_less_own_shipments`, IS:2160-2370 `pair_needs`, `_through_po` IS:2310; `_refs_named_by_book` PS:3989; `_book_names_target_for_line` PS:4014-4084.
- row to target: SO line `source_ref` equals `from_so_line_ref` on PO line (`PurchaseOrderLine.from_so_line_ref`) or on SPO allocation (`SPOAllocation.from_so_line_ref`); unambiguous refs only (`_unambiguous_refs`).
- PO to SPO: `_chain_allocations`: `SPOAllocation.from_po_number IN po_numbers` AND `product_id IN` then keyed in Python by (`from_po_number`, `strip(from_po_line_ref)`, `product_id`) against (`po_number`, `strip(source_ref)`, `product_id`); `visible_line_clauses` only. `_book_names_target_for_line` uses `PurchaseOrder.po_number == from_po_number AND PurchaseOrderLine.source_ref == from_po_line_ref` (no btrim, no product, refuses ambiguous > 1).
- states: capacity is the document's WHOLE quantity (`qty_ordered` / `allocated_quantity`), explicitly NOT outstanding, so closed and fully received lines are valid targets (IS:1852-1860). Cancelled PO lines are refused (`_LIVE_PO_LINE` IS:198). Visible SPO lines only.
- quantity: capacity less existing claims; PO line capacity is reduced by the chained SPO allocations' capacity (`_less_own_shipments`: PO 486 with SPO 486 leaves PO 0).
- differs: the only reader that nets PO against its own SPO. Acts only on rows with unlinked need; fully linked rows are never corrected (plan line 140).

### R13 Link follow of ref moves / PO relink / SPO supersede (writers; listed for completeness)
- `follow_book_repairing` PS:3415-3468, `_follow_one_move` PS:3470-3619, `_resolve_ref_line` PS:3621; `relink_to_matching_lines` PS:13195; `repoint_allocation_dependants` shipping_order_rules.py:825; `scripts/convert_oi_cascade_links.py` (`_book_names_target_for_line`, received test at line 178 via `RECEIVED_RECEIPT_STATUSES`). None of them performs PO to SPO.

### R14 refresh_link_state / _coverage_state (OI row state "On PO/SPO")
- screen: row `state` everywhere (FE `STATE_LABEL.placed = 'On PO/SPO'` `_shared/components/OrderInquiryVerbPill.tsx:102`; Lines tab line pill `orderInquiryHeaderLinesColumns.tsx:846`; worklist filter `OrderInquiriesClient.tsx:1577`).
- where: PS:9592-9657 `refresh_link_state`, PS:9659-9671 `_coverage_state`; also `derive_bundles` PS:9673 and PS:9863.
- row to target: `_links_of(row.id)`, sum of `link.qty` (reserve links included in `linked`, PS:9628).
- PO to SPO: none.
- states: only quantity cover: covered = linked + bundled; `<= 0` raised, `< qty` partly_linked, else placed. No receipt, no arrival, no transfer. `actioned`/`cancelled` are left untouched.
- derived display columns written here: `row.po_ref = first link.document` (even when that link is an SPO, PS:9646), `row.po_line_id = first.po_line_id`, `row.spo_ref = first.document` only when first link is SPO (PS:9648-9652).
- differs: "On PO/SPO" is purely a cover-quantity statement; the worklist's received pill (R20) and the Lines tab disagree because only the worklist cell renders `received`.

### R15 serialize_rows (per-project list/Lines tab backend)
- where: PS:7905-8041; `get_for_sales_order` PS:8752.
- row to target: R1 (`links`), `_linked_qty_by_row` PS:9987 (real links only), stored `spo_ref`/`po_ref`/`po_line_id` (R14).
- differs: `linked_qty` real links only; `links` carries derived entries (R2). Frontend that sums `links` must skip `derived` (WS:2403-2406 does; SCM SO detail `_line_links` copies `derived` through, sales_order_service.py:928).

### R16 order_inquiry_header_service related documents
- where: `app/services/order_inquiry_header_service.py:540-620` (query 548-589, supplier 591).
- row to target: PO links by `po_line_id` -> PO header; SPO links by `spo_allocation_id` -> `spo_number`.
- PO to SPO: none (an OI header lists a PO and an SPO as unrelated documents). Supplier from `supplier_id_for` (PO via FK or `from_po_number`).
- states: none (only cancelled rows excluded).
- quantity: sum of link qty per document.

### R17 planning_change_service document-links reader (reallocate/Confirm offer)
- where: `app/services/planning_change_service.py:1550-1640` (`received = ...._received_documents_for(links)` at 1604).
- row to target: all links of the line's live ORDER rows.
- PO to SPO: none. A transferred PO line is counted in `received_qty` (R3 semantics) and is never offered as `po_qty`; an SPO link is never `po_qty` at all (comment at 1558-1568).
- quantity: `qty` all links; `po_qty` PO-kind links not received; `received_qty` received links; `arrival_date` = max of PO line / PO header expected dates, SPO links contribute no date (arrivals built from `po_line_ids` only, 1618-1630).

### R18 worklist link suggestion pill (reallocate/unlink)
- where: WS:1798-1920 `_attach_link_suggestions` (skips `link.received`, WS:1854; uses `link.expected_date`, i.e. PO line date for a PO link or SPO date for an SPO link).
- differs: a transferred PO link never gets a suggestion (it reads received); the date compared is the PO line's, not the SPO's.

### R19 worklist `_serialize` reserve_requestable_qty / reserve chip
- where: WS:2375-2425; `order_inquiry_reserve_service._requestable` 122-145, `_remaining` 109-120.
- logic: open links = links not `received` OR whose PO line is in `blocked` (open chained SPO). `_requestable` (BE) = `remaining + sum(received_links_of qty)`; the two spellings in BE and WS match only if `blocked` is the same set (it is: both use R4).

### R20 FE document cell pills (the screen-level readers)
- Worklist PO/SPO cell: `orderInquiryWorklistColumns.tsx` `documentsOf` 194-233, `DocumentsCell` 358-470; received pill at 401-419 (`first.received`), "via PO"/"via SPO" pill 391-399, suggestion pill 421-436, `+N` pill 440-455.
- OI header Lines tab: `[id]/components/orderInquiryHeaderLinesColumns.tsx` PO and SPO columns (`LineDocumentsCell` 136-184, `DocumentCell` 186-224, SPO column def 769-775); uses `documentsOf` (same derivation) but renders only the `via` pill (219-221), NO received pill and no suggestion pill; state pill `OrderInquiryLineStatePill` 846 -> `OrderInquiryVerbPill.tsx` (STATE_LABEL 98-104).
- Backing documents dialog: `OrderInquiryBackingDocumentsDialog.tsx` derived "via PO" 123-125, `source_po_number` 138-148, "Received N of M" 150-157.
- PO/SPO lightbox: `OrderInquiryDocumentDialog.tsx` PO lines table: received col 369-376, SPO numbers col 434-454; SPO table: received 497-505, source_po_number 535-542, `highlightLines` 71-105; "via SPO" PO resolve 810-.
- SCM SO detail: `scm/sales-orders/[id]/components/SalesOrderDetail.tsx:1122-1148` ("Linked to" total) and `SoLineLinksBody.tsx:40-80` (document column, "via PO" suffix 48; no received).
- Fulfilment board chip: `project-sales/_shared/lib/supplyVocabulary.ts:931-960` `boardOrderInquiryWord`: "used" if redirected; "received" only if EVERY document `received` (derived entries are documents with `received` false, so an open derived SPO makes the chip read "SPO"); then "SPO" if any spo-kind, "PO" if any po-kind. Types: `_shared/types/fulfilmentPlanning.types.ts:1559-1580`.

### R21 OI engine inbound pool (what a NEW OI row can be covered by)
- where: PS:7484-7535 `_inbound_pools` (+ `_claimed` PS:7537, `_pools` PS:7410).
- states: `open_incoming_clauses`, `spo_number` and `warehouse_id` not null, balance `allocated - received > 0`.
- PO to SPO: none (SPO treated as stock on the water, keyed by `spo_number` label via `covered_by`).
- differs: a PO line never enters this pool; a transferred PO line's goods count only via the SPO.

### R22 emails, print, Excel
- Worklist Excel/PDF: `WS:3495-3563` `export_xlsx`/`export_pdf`, `_sheet_values` WS:3739-3820: SUPPLIER and "PO NO " come from R6 (`row.supplier`, `row.po_number`), TAKEN/REMAINING from `linked_qty` (`_export_taken` WS:1001, `_export_remaining` WS:1007), SUGGESTED from suggested links. NO SPO column and no received/transfer info.
- Per-project Excel: PS:13854-13898 `export_xlsx` prints only `remark`, `stock_location`; no PO/SPO number except `remark`.
- `_remark` PS:8742-8750: prints `row.spo_ref` only for verb ALREADY_INBOUND (an engine-written `covered_by` SPO label), else the verb spelling.
- Handover email/print (`build_handover_email` PS:14269-, `oi_handover_resend.py`, `oi_cancelled_used_backfill.py`, `order_inquiry_pdf.py`): grep shows no read of links/SPO/PO lines; the only document words that reach them are note fragments `"<doc> received <date> into <loc>"` from R3 (`_redirect_row_if_received` PS:3320-3345 and PS:3295) and `"Unlinked from <doc>"` from `_remove_links` PS:13556. UNVERIFIED: whether template files outside these modules print more (not searched).

### R23 Misc small readers of "target dates/states"
- `_link_expected_date` PS:5448-5462: SPO expected_date if SPO link, else PO line expected_date (used by borrow shortfall logic).
- `_cited_documents` PS:10238 (row note/spo_ref/cited_document, text only).
- `_dedication_for_target` / `_prime_claims` PS:10086-10179: claims table (scm.order_link_claim) by target id; no chain.
- `link_candidate_products` and `_inbound_pools` are R11/R21.

## 2. Shared predicates (app/services/scm/spo_supply.py, 355 lines, read in full)

| function | lines | admits | note |
| --- | --- | --- | --- |
| `RECEIVED_RECEIPT_STATUSES = ("fully_received","received")` | 55 | the two spellings meaning "in" | `received` has never existed in data; kept for migration 337's view |
| `open_incoming_clauses()` | 58-77 | line_status NULL or 'open'; receipt_status NULL or not in RECEIVED set; (outer-joined) `InboundShipment.actual_arrival_date IS NULL` (or no shipment) | open: yes; in transit: yes; landed (shipment arrived): NO; partly received: yes (quantity test is NOT here); fully received: NO if receipt_status says so; closed: NO; cancelled: represented as `line_status` closed: NO; retired: NOT tested (retired lines pass unless closed). Quantity test (`allocated > received`) deliberately left to each reader. |
| `visible_line_clauses()` | 80-113 | NOT (retired AND never received): `retired_at IS NULL OR coalesce(quantity_received,0) > 0` | every status passes (open, landed, fully received, closed); only retired-and-zero-received hidden. Different question from "incoming". |
| `is_visible_allocation(a)` | 116-125 | Python twin of `visible_line_clauses` | |
| `supplier_id_for(allocation)` | 128-157 | supplier via `po_line_id` -> PO supplier, else PO matched on `PurchaseOrder.po_number == from_po_number` and same company, else allocation `supplier_id` | uses `from_po_number` only (no line ref) |
| `MaskedEta` / `shown_date` | 160-229 | date masking for ETA delay | not state-related |
| `overdue_days` | 232-241 | wording only | |
| `spo_history_for_product` | 244-338 | visible lines at site-pool warehouses; `still_open = open_incoming_clauses AND allocated > received` | "open" vs "history" lists |
| `_shipment_status` | 341-355 | words: open -> "Partly received" if received > 0 else "On the water"; else "Arrived" (shipment landed, received <= 0), "Partly received" (0 < received < allocated), else "Received" | the only code that labels in-transit/arrived/received |

`derived_spo_open_clauses` PS:366-386 (OI-local): `retired_at IS NULL` AND `allocated_quantity > coalesce(quantity_received,0)` AND `open_incoming_clauses`. Used by R2 and R5 only (imported by WS at WS:95).

### Callers of each predicate across the backend (grep `app/` and `scripts/`)

`open_incoming_clauses` (spo_supply) callers:
- PS:385 (via `derived_spo_open_clauses`, readers R2/R5), PS:7517 (`_inbound_pools` R21), PS:10475 (`_candidates_for_row` SPO), PS:13479 (`po_lines_with_open_chained_spo` R4), PS:13791 (`link_candidate_products`), PS:3350/3400 and PS:8256/8266 (text/copy of the same test in `_received_documents_for` and `links_for_rows`, written out by hand, do NOT call the function).
- `app/services/project_supply_service.py:7000`, `:10018` (ladder question 1 / board popover SPO rows).
- `app/services/scm/stock_debt_service.py:1759`, `:1987` (label `spo_incoming`); copy of the test at `:170` using `RECEIVED_RECEIPT_STATUSES`.
- `app/services/scm/group_netting.py:370`, `app/services/scm/project_bin_lock.py:94`, `app/services/scm/site_pool_supply.py:24,145`, `app/services/stock_status_service.py:322`.
- `app/services/procurement_service.py:2596` (list_documents outstanding), `:2953` (`is_open_expr`).
- `spo_supply.spo_history_for_product` itself (SS:298), called from `app/api/v1/scm/reorder_runs.py:837`.
- `app/services/planning_change_service.py:1564` (doc comment only; reaches it via `_received_documents_for`).
- `scm.on_order_v` SQL view repeats the clauses (named in module docstring).

`visible_line_clauses` callers:
- PS:8186 (R1), PS:13480 (R4), WS:2745 (R9 `_spo_numbers_by_po_line`), WS:2791 (R10 `get_spo_detail`), IS:1905/1965/2062 (`_target_facts`, `_bought_rows`, `_chain_allocations`), `app/services/scm/order_link_service.py:300` (claim resolution by spo_number), `app/services/scm/coverage_service.py:660` (`allocation_visible` label), `app/services/scm/purchase_order_service.py:426` (`_spo_takes_of` landing allocations by `po_line_id`), `app/services/scm/stock_debt_service.py:1806,2006`, `app/services/scm/spo_conversion_service.py:852,934,1245`, `app/services/procurement_service.py:1044,1373,2134,2268,2293,2396,2587,2835,2879,2976`, `app/api/v1/procurement/packing_lists.py:280,291`, `app/services/spo_last_receipt_service.py:77,222,279,317,349`, `app/services/incoming_stock_service.py:332` (n8n incoming), `app/services/entity_resolver.py:1664,2315`, `app/services/purchase_order_service.py:280` (chatbot "po placed"), `app/services/embedding_worker.py:741`, `app/services/embedding_backfill_service.py:234`.
`is_visible_allocation`: `app/services/scm/spo_conversion_service.py:2763, 3230`.
`supplier_id_for`: PS:10470, 10651; WS:335; `order_inquiry_header_service.py:591`; IS:1898, 2916 (and WS:2815).
`RECEIVED_RECEIPT_STATUSES`: PS:3400, 8266; `app/services/incoming_stock_service.py:311`; `app/services/scm/coverage_service.py:583`; `app/services/scm/stock_debt_service.py:170`; `scripts/convert_oi_cascade_links.py:178`.
`overdue_days`/`shown_date`/`MaskedEta`: `project_supply_service.py`, `project_fulfilment_board_service.py`, `front_planning_engine.py`, `supply_assignment.py`, `procurement_service.py:3159` (wording only).

## 3. Match-key variants for "PO line to SPO line" in the OI domain (all spellings found)

| # | where | key | normalisation | product | company | other |
| --- | --- | --- | --- | --- | --- | --- |
| K1 | R2 PS:8429-8449 | `from_po_number = po_number`, `btrim(from_po_line_ref) = strip(source_ref)` | btrim both sides | yes | explicit predicate | open set only |
| K2 | R5 WS:1135-1151 | same, in SQL EXISTS from the row's PO links | btrim both | yes | explicit predicate | open set only |
| K3 | R9 WS:2735-2747 | same | btrim both | yes | explicit predicate | visible set (all states) |
| K4 | R4 PS:13463-13476 | `from_po_number = po_number`, `from_po_line_ref = source_ref` | NONE (exact) | NO | `company_id` equality | open AND visible |
| K5 | R12 `_chain_allocations` IS:2060-2078 | `(from_po_number, strip(from_po_line_ref), product_id)` vs `(po_number, strip(source_ref), product_id)` | strip | yes | session scope | visible set |
| K6 | R12 `_book_names_target_for_line` PS:4057-4084 | `po_number = from_po_number AND source_ref = from_po_line_ref` | none | no | session scope | refuses ambiguity (> 1) |
| K7 | R6 / supplier / `supplier_id_for` SS:138-157 | `SPOAllocation.po_line_id` FK, else `po_number = from_po_number` (document only) | none | no | same company | supplier only |
| K8 | R1 PS:8341-8382 | `SPOAllocation.po_line_id` FK (Sorento-raised SPO), else `po_number = from_po_number` | none | no | session scope | resolves `purchase_order_id` for the document link only |
| K9 | `scm/purchase_order_service._spo_takes_of` (not OI, outside scope but same question) | SPO PO-line `source_ref` JSON pulls | JSON | | | CRM-raised SPOs only; UNVERIFIED depth |

## 4. Divergences that matter for the real case (OI-2609-0128 line 880, PO 202607-S0100 line 2 to SPO-2026/09-0107 line 9, 486/486 received)

D1. SPO column "-" (R2) vs SPO number in PO popup (R9): R2 requires `derived_spo_open_clauses` (open, unlanded, balance > 0) but R9 only `visible_line_clauses`. Once the SPO is fully received or the shipment has `actual_arrival_date`, R2 drops it and R9 keeps it. Same SPO, same key (K1 = K3), different state filter.
D2. "On PO/SPO" (R14) is cover-only; worklist shows "received" pill (R20 first.received from R1 PO test: PO `qty_received >= qty_ordered`, which is the TRANSFER figure) but the Lines tab renders no received pill and no suggestion pill. Moreover the PO link reads `received=True` as soon as AutoCount transfers the line, i.e. BEFORE the SPO lands, while R4 is the one reader that notices an open chained SPO.
D3. Worklist cards (R5): landed SPO leaves "Incoming/SPO" and the quantity falls back into "On PO"; there is no received stage.
D4. Link keying (F1/F2): a link placed before the transfer stays on the PO line; only unlinked need is paired through the chain (R12). Candidate/capacity logic (R11) does not net PO line against its SPO, so 486 on the PO link leaves the SPO allocation looking free (importer-only `_less_own_shipments`).
D5. Duplicated received tests (R1 vs R3) and 4 spellings of the PO to SPO key (K1..K6); K4 and K6 omit btrim and product.
D6. `received_qty` for a PO link is the transfer figure (R1 PS:8283), so the Lines/Backing dialog states "Received 486 of 486" on a PO that has not physically received anything.
D7. PO popup "remaining = ordered - received" (R9) is zero after transfer, and "Allocated to" lists only PO-line links; the SPO popup (R10) lists only SPO-line links. Neither shows a row that sits on the other book of the same chain.
D8. `po_ref` / "PO NO" column (R6, R14): `row.po_ref` = first link's document even when that is an SPO; Excel "PO NO " uses a join that needs `SPOAllocation.po_line_id`, blank for book-fed SPO links.

## 5. Not read / UNVERIFIED
- `project_supply_service._own_arrival_credit_components` and `own_arrival_credit_for` (reads PO/SPO supply for a row, called from PS:3107-3231): other agent's scope.
- `scm/stock_debt_service`, `coverage_service`, `demand`, `supply_assignment`, `container_request_service`: other agents.
- Email template files beyond `build_handover_email` caller wiring (PS:14269-14336) were not read in detail.
- Live-data confirmation of D4 (double availability of the SPO capacity) and of R2 not de-duplicating an existing real SPO link: derived from reading code, not run.
- `scm/purchase_order_service._allocations_for` / PO occupancy on the SCM PO page (also sums `order_inquiry_links` by `po_line_id`): grep'd only, not read.
