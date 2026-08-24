# PLAN - SCM order imports: agents, duplicates, async, standard modal

**Status:** S1 to S4 merged to main (PR #143, which absorbed #147). S6 merged to main (PR
#154, branch `feat/scm-agent-master-ui`); browser pass done. S5 is THIS
PR - branch `feat/scm-po-spo-history-main`, PR #161; developed stacked on S3 + S4, then
carried onto main so it stands alone; backend only, pytest green, no browser pass needed -
the channel has no new screen. Contract: `UAC-scm-order-import-feedback.md` (same
directory). Captain feedback sections 1-6 in
`firstmate/data/so-import-feedback/captain-feedback.md`.

**Amendments made while building S3 + S4** (each one is a place the plan as written could not
be followed, recorded here so the contract and the code agree):

1. **`unmapped_agents` renders on the TEST result only, not on an apply result.** S4 item 3
   asked for the field on `OutstandingPreview` AND `OutstandingApplyResult`. S3 deletes the
   second: apply answers 202 with a job id, so there is no apply result for a dialog to
   render. The fact still reaches the operator twice - in the Test result (which is what
   AC-6.4 asks for) and on the job, where the commit's own copy lands in
   `result.upload.unmapped_agents` and says which agents THIS upload created.
2. **The channel's answer is nested under `result.upload` on the job**, rather than spread
   across the result envelope. Its shape is unchanged; nesting is what stops the diff's
   `counts` (added / closed / unchanged) overwriting the envelope's `counts` (the row totals
   every job page reads).
3. **The unreadable-file 400 became a failed JOB.** Reading happens on the worker, so the
   request cannot answer without parsing the whole book twice. `?validate_only=true` is
   unchanged and still synchronous, and Test is what tells the operator before they confirm.
4. **Three shared-hook dialogs outside the five channels changed behaviour**: reorder levels,
   the packing list and the supplier stock list all use `useTwoStepUpload`, so they stopped
   reading on file-select too and the reorder-level dialog gained the Test button it lacked.
   Their applies stay SYNCHRONOUS - they are not order-book feeds, they have no queued task,
   and inventing one was not in scope.
5. **The shared warning section is `components/common/ImportFeedbackSections`**, extracted
   from the customer importer's `TestResultPanel` (see S4 item 2 for why the winner had to be
   named). The customer dialog now renders through it, which is what proves it is shared.
6. Two reader/parser additions were needed to account for every source row on the job:
   `ReadResult.layout_row_numbers` / `settled_row_numbers` (outstanding), and `_instalments`
   returning the absorbed ROW NUMBERS rather than a count (order inquiry). Without them a
   4,349-row file finishes reporting 4,290 rows processed and nothing explains the rest.

**Amendments from the S3 + S4 review pass** (same rule: each is a place the built code and
the contract disagreed, recorded so they agree again).

7. **`total_rows` on a queued SCM job means "everything the job accounted for", not "the
   rows of the file".** The destructive halves - a line CLOSED by its absence from an
   outstanding book, an instalment WITHDRAWN because the inquiry sheet stopped stating it -
   carry an outcome and no source row, so with the file's own count as the total the job page
   read `6 / 5` and drew a progress bar past 100%. The total is now published a second time
   once the diff is known and before the write loop (outstanding) or once the withdrawals are
   known (order inquiry), and the file's own count stays on the result as `file_rows` /
   `rows`. Invariant, asserted per channel: **processed == total**.
8. **One definition of that total across all five channels: every non-blank SOURCE ROW.** The
   two history readers counted only the LINES, so the sales book's 9,144 package captions and
   the PO listing's headers, `**SO:174830**` notes and spacers were outside the total and
   carried no outcome at all - the same file reconciled on one channel and not on another.
   Both readers now carry caption/layout row NUMBERS (as the outstanding reader already did)
   and both services emit `NOT_A_LINE` per such row.
9. **The single-company 400 is hoisted onto every READ, not just apply** (AC-4.2's "preview
   runs at the same company scope the queued job will run at", which was stated and not
   built). The four preview routes and both `?validate_only=true` branches now refuse with
   the same message the apply refuses with. Reason: every one of these readers resolves item
   codes to ids through last-write-wins lookups and 11,390 product codes are held by more
   than one company, so an all-companies read binds a line to the wrong company's product and
   shows a diff apply would never make. Precedent: the customer importer refuses both modes
   for the same reason (`order_management/customers.py`).

**Amendments made while building S6** (same rule: each is a place the built code and the
plan as written disagree, recorded so they agree again).

10. **List + edit modal only; no `[id]` detail page.** The AutoCount mirror surface is a list
    AND a detail page, and S6 item 2 asks for a modal, so the two cannot both be reproduced.
    The modal wins (it is what the plan specifies, and two annotation fields do not justify a
    page). Nothing under `master-data-management/sales-agents/[id]/` is touched, so that
    branch's detail page merges in as an addition rather than a conflict, and it will find
    both new columns already on `SalesAgentResponse`. Consequence for the list: the mirror's
    per-row chevron-to-detail becomes a per-row Edit (pencil) that opens the modal.
    **What that page imports must therefore still exist here**, or "merges as an addition"
    is false and the next build breaks: `useSalesAgent` (hooks), `getSalesAgent` (service)
    and the type name `MirrorAnnotationPayload` are all kept, unused by this slice, for
    exactly that reason. `SalesAgentAnnotationPayload` is an alias of the same type, so both
    spellings resolve and no call site has to be renamed on merge. The only edit the merger
    makes to that page is none: it should compile as it stands.
11. **Three files are created here that the AutoCount branch also creates**, at the same
    paths and with the same class names. Two are safe to take either copy of:
    `app/services/autocount_mirror_service.py` (copied VERBATIM, so it cannot drift) and
    `app/schemas/autocount_mirror.py` (only the sales-agent classes, since this chain has no
    other mirror table) - resolve by taking that branch's copy plus the extensions S6 item 3
    names, all already made here: `person_label` (bounded `max_length=100`, the column's own
    width) + `demand_class` on `MirrorAnnotationUpdate` AND on `SalesAgentResponse`, and
    `source` widened to accept `import`. The third is
    `app/api/v1/master_data/sales_agents.py`, and it is **NOT verbatim**: the docstring is
    rewritten for the annotation surface and the PATCH handler calls
    `sales_agent_service.annotate` before the mirror annotate. Take THIS branch's copy of
    that file; the other differs only in lacking those two things.
12. **The frontend service uses `buildDataGridParams` + `extractApiError`**, where the mirror
    page hand-rolls a `URLSearchParams` and throws a bare `Error`. The repo rule
    (ARCHITECTURE-RULES, and a code-review hard-fail) outranks faithfulness to that file.
    Same reason the source column renders a plain `Badge` off a label map rather than
    `AutoCountSourceBadge`, which does not exist on this chain: on merge it becomes a
    one-line swap to that component. The toolbar's Export is switched OFF rather than
    carried over: it is selection-gated and this list has no selection column, so the
    mirror page's `exportConfig` renders a button that can never be pressed.
13. **`demand_class` is typed as a plain string in the PATCH body, not a `Literal`.** A
    Literal would answer a word outside the vocabulary with FastAPI's field error, and the
    thing an admin needs to read is the service's message naming the words the fulfilment
    policy can weigh. So the body is permissive, `sales_agent_service.assert_demand_class`
    is the only judge (S6 item 4), and a bad word is a 400 carrying that message. The route's
    own `MirrorAnnotationUpdate` keeps `extra="forbid"`, so an unknown KEY is still a 422.
14. **List search is the mirror's two columns (code + description), not widened to
    `person_label`.** The plan asks for search on the code; keeping the mirror's exact
    search set is what makes the two branches one page rather than two that look alike.
15. **The screen's class write does NOT go through `set_demand_class`,** which S6 item 2
    asked for. That function resolves the agent by CODE, with a `.first()` and no ORDER BY,
    and the code is unique only PER COMPANY: a shared row (`company_id IS NULL`) and a
    company-owned row may both spell `SEAN III`, so classifying the row the user clicked
    could flush the class onto the other one and change the wrong salesperson's whole book.
    The screen writes the class onto the row it fetched by id. The closed vocabulary still
    has exactly one judge, `assert_demand_class`, called by both paths;
    `set_demand_class` remains the code-keyed path importers use. Pinned by
    `test_the_class_lands_on_the_clicked_row_not_a_namesake`.
16. **Duplicate-hunk merges with the AutoCount branch: menu keeps THIS branch's entry,
    registry and router keep one line either way.** The captain ruled (2026-08-15) that
    Sales Agents lives under **User Management** (after Market Segments), not Product
    Management, so this branch's menu entry in both arrays of
    `sorento_crm_frontend/config/menu.config.tsx` is the one to keep; DROP autocount's
    Product Management placement on merge. The `_crud("master_data", "sales_agents", ...)`
    line in `app/rbac/permission_registry.py` and the `include_router(sales_agents.router,
    ...)` line in `app/api/v1/master_data/__init__.py` are identical in both branches: keep
    one copy of each. A duplicated menu entry renders the page twice in the sidebar; a
    duplicated `_crud` line seeds nothing twice (the sync is idempotent) but reads as a
    mistake; a duplicated `include_router` mounts the same routes twice and the second
    silently shadows the first. The URL stays `/master-data-management/sales-agents` (the
    merged-surface contract); only the sidebar group moved.

**Amendments made while building S5** (same rule again: each is a place the plan as written
could not be followed, or a fact the file itself corrected). These were written as 10-20 and
are **renumbered 17-27** here: S6 merged to main first and took 10-16.

17. **The SPO half lands in `purchase_orders` / `purchase_order_lines`, discriminated by
    `source_system` (`scm_po_history` / `scm_spo_history`), NOT in `spo_allocations`.** The
    plan left the landing open ("the same table discriminated by doc family or a sibling
    table, whichever needs no migration"). `spo_allocations` fails on four counts, each
    measured rather than argued: (a) it IS the supply read model - `scm.on_order_v` selects
    from it (migration 337) - so 13,550 history rows would sit one status flag away from
    becoming netting supply, which is the single thing this channel exists to prevent;
    (b) `spo_allocations.warehouse_id` is NOT NULL and 578 rows of the captain's book name a
    location this database does not hold, so those rows would be dropped rather than
    recorded; (c) every allocation needs an `inbound_shipments` parent (`shipment_date` NOT
    NULL, unique `shipment_number`), so the import would invent ~1,500 shipments that then
    appear on the incoming-stock and container-status screens as real containers; (d) the
    unique key `uk_spo_allocations_spo_number_product_warehouse` forbids the same item twice
    on one SPO, and the file contains 2,253 such groups, up to 75 rows deep. The purchase
    tables hold exactly what the file states - a creditor document with dated item lines -
    and history there is inert by construction (closed line + fully received). **No migration
    was needed for the landing.** One migration was added, and it is data only: 358 seeds the
    27 header aliases (AC-1.2).
18. **Routing by prefix is applied to BOTH file shapes, not only the structured one.** The
    family is a property of the DOCUMENT (`po_listing_reader.doc_family`), and the banded
    report carries `SPO-2020/01-0001` too. One definition, so the two readers cannot disagree
    about which family a number belongs to.
19. **Nine rows disagree with their `Shipping Order` flag, not ten.** Re-measured on the real
    file 2026-08-14: 13,641 PO + 13,550 SPO + 1 blank-doc grand-total row = 27,192, and the
    flag disagrees on nine `######-S####` rows (all flagged `Checked`). The routing reads the
    prefix, so all nine land as purchase orders.
20. **`Agent` on this book is NOT a salesperson, so it is not fed to the agent master.** Its
    values are the creditor's own shorthand (`TAIYANG` against `XIAMEN TAIYANG TECHNOLOGY
    CO.,LTD`, `CAIZOU` against `CAIZHOU PLUMBING PRODUCTS FITTING CO LTD`). Feeding it to
    `sales_agent_service` as the outstanding SO reader does would have created 38 factories
    in the salesperson master S1 built. It is aliased under the history doc type, where it
    resolves and stops.
21. **No cost and no currency are read from the structured export.** It carries no unit price
    at all; its `Standard Price` is the item's standard price rather than what the document
    paid, and the supplier cost ranking compares what was paid. `unit_cost` therefore stays
    NULL on the structured half (the banded report still supplies it), and `unmatched_creditors`
    is reported instead of a supplier being invented: this export names the creditor and never
    its code, and `suppliers.supplier_code` is unique and NOT NULL.
22. **Two facts the structured export states that the banded report cannot, and which are now
    written:** the stock location per line (`purchase_order_lines.warehouse_id`, NULL where the
    code is unknown - a closed line cannot be mis-placed by it, and the codes are reported),
    and the sales order per LINE (`FromSODocList`), which becomes an `OrderLinkClaim` that
    NAMES the item and so resolves to that line rather than to the order's first line. The
    banded report's `**SO:174830**` notes stay order-level. The claim is per line but it is
    not per OCCURRENCE: `order_link_service` matches on `(so_number, item_code)`, so where a
    document names the same item on several rows the claim resolves to ONE of them, chosen
    by whichever the join returns. The file cannot disambiguate that (the rows differ only by
    container), so nothing better is available and the claim is still true at the level it is
    stated: this SO relates to that item on that PO. This is an addition to the plan's three
    S5 items, taken because the alternative was to alias the only precise SO-to-PO pairing in
    either export as "deliberately ignored". One existing test moved with it:
    `test_po_listing_reader.py` asserted the line type had NO `so_number` ATTRIBUTE, which
    was the mechanism rather than the contract; it now asserts the banded report leaves every
    one of them UNSET, which is the contract (that report cannot say which line a note
    describes, and nothing in this change lets it guess).
23. **Line identity is positional.** The structured export has no line-number column, so the
    n-th line of a document in file order is its identity - the same rule the outstanding book
    uses (AC-2.2), and necessary rather than cosmetic: `202301-S0001` names `CB4924-CR` twice
    on two different containers, so a content key would merge two real lines into one.
24. **The blank-Doc-No row carries `missing_doc_no`, and caption rows carry `not_a_line`.**
    The 924 rows with a document and no item code are captions inside a document
    ("EXTRA LOADING : "); the single row with figures and no document is the export's
    grand-total. `total_rows == lines + captions + problem rows` is asserted, which is the
    per-channel `processed == total` invariant (amendment 7) restated for this reader.

**Amendments from the S5 review pass.**

25. **BLOCKER, fixed: the outstanding-PO importer could turn history into supply.**
    `purchase_orders` has two writers. `outstanding_import_service._closed_line` revives a
    CLOSED line rather than inserting a second row - correct for its own lines (a line that
    comes back is the same line, and the receipt booked against it belongs to it) - and it
    matched on `(header, product, warehouse, expected_date)` with no source guard. S5 is what
    made that reachable: history lines used to carry NULL warehouse and NULL date, and the
    structured export states both. The sequence was: history writes `202301-S0001` closed,
    an outstanding-PO extract names the same document, `_existing_lines` cannot see the
    closed line so the row reads ADDED, and the revive then sets `line_status='open'` with
    `qty_ordered = received + incoming` - putting a delivered 2023 purchase into
    `scm.po_ordered_v` permanently. The guard is a `source_system NOT IN
    (history stamps)` filter on that one query. The stamps moved to
    `app/services/scm/history_sources.py` so the feed that must not touch history can
    recognise it without importing the feed that writes it (`scm_so_history` is listed too:
    the sales book has the same two-writer shape). Pinned by
    `test_the_outstanding_book_never_revives_a_history_line`, which fails on all three counts
    with the guard removed.
26. **DECISION, accepted not guarded: a history upload rewrites the header of a document
    number it finds, and SPO numbers now occupy the globally-unique `po_number` namespace.**
    Two consequences, both accepted deliberately. (a) If a live purchase order carries a
    number the history book also names, its header (issue date, currency, supplier link) is
    refreshed from the file - the same behaviour the banded report has had since the channel
    shipped, and the file is the system of record for what was ordered. The LINES are not at
    risk: they are keyed per document and the history feed only ever writes closed rows.
    (b) 13,550 `SPO-...` numbers now exist as `purchase_orders.po_number`, which is unique
    across the table, so a future feed cannot create a purchase order under an SPO number
    that history already holds. Both are reversible by narrowing the header write to rows
    this feed's own `source_system` owns; not done now because the captain's book is history
    for a closed year, and refusing to refresh a header would leave a partly-imported
    document that no re-upload could correct.
27. **The `source_system` split has no READER yet.** The PO list collapses both stamps to
    "import" (`purchase_order_service._IMPORT_SOURCES`), so today the split is provenance for
    a future filter ("show me shipping orders") rather than a visible distinction. Noted so
    the next slice does not assume a screen already reads it.

**S1 + S2 ship the agent data with NO surface on it.** `unmapped_agents` is on both the
preview and the apply response, and nothing renders it: the FE `OutstandingPreview` type does
not carry the field, so "new agent, unclassified" (AC-6.4) is true of the API and invisible to
the operator until **S4** adds the section. Likewise the demand class an agent carries can be
set only through `sales_agent_service.set_demand_class`, with no admin screen until **S6**.
Both gaps are deliberate ordering, not oversights, and each is closed by exactly one slice
below.

**Deviation, S2/AC-1.2 (PO + SPO history aliases): NOT built in S2, CLOSED in S5.** The 27
header spellings of `PO & SPO 2023.xlsx` were recorded nowhere this repo could read - the
verified-facts note below stated the column COUNT, not the names - and seeding invented
spellings would have produced alias rows that match nothing while reading as done. The file
was measured on 2026-08-14 and S5 seeds all 27 (migration 358, doc type `po_spo_history`),
alongside the reader that needs them. AC-1.1 (the outstanding-SO file) was built in full in
S2.

## Verified facts the plan is built on (do not re-derive)

- Outstanding SO file: 4,349 rows, 38 distinct agent codes decomposing to 16 people via a
  `(base name, I|III|IV)` split; no `II` exists; suffix maps to NEITHER company nor market
  segment in the DB, so its meaning is not derivable - hence AC-3.3 (seed codes, class NULL).
- 605 duplicate-key groups; 567 differ in qty/price/remaining; 38 byte-identical. No line
  number column exists in the export.
- The reader ALREADY keeps duplicate lines (`result.lines.append` is unconditional); only the
  false RowProblem is emitted. `outstanding_diff.py` already groups by (doc, item, location)
  and pairs exact-date-then-date-order.
- `PO & SPO 2023.xlsx`: one sheet, 27,192 data rows, 27 columns, 13,641 PO (`202...`) +
  13,550 SPO (`SPO...`) + 1 grand-total row with no Doc No. `Shipping Order` flag agrees with
  the prefix except NINE rows (re-measured 2026-08-14; the plan first said ten) - discriminate
  on the Doc No PREFIX, never the flag (a misfiled row would silently become netting supply,
  ADR-337). Of the 27,191 rows that name a document, 924 name no item code: they are captions
  inside a document, not lines. 1,487 distinct documents; 4,239 `(doc, item)` groups repeat,
  up to 111 rows deep, so line identity cannot be a content key. 100% of its item codes
  resolve against the catalogue; 15 of its 19 stock locations do; its 51 creditor names carry
  a trailing `(RMB)` currency marker on some rows and not others.
- `sales_agents` exists (2 rows, no company_id); `salesman_code_users` exists (0 rows,
  user-FK NOT NULL - wrong shape for a master, leave dormant). **Corrected during S1:** the
  table belongs to the UNMERGED AutoCount branch (`sorento_crm-autocount`, model
  `app/models/sales_agent.py`, migration `303_autocount_slice2_masters`), which is why main
  has no model and no migration for it. S1's migration reproduces those five columns verbatim
  and only ADDS to them, so the two chains describe one table. Its 2 rows are `ZZT`-prefixed
  test residue (`ZZT Loh Han Cong`, `ZZT Agnes Tan`), not master data - the captain's
  keep-or-clean question answers itself.
- Current apply routes are fully synchronous (parse + write + commit inline; the sales-history
  504 already proved the failure mode at 72k lines).

## Slices, in build order

### S1 - Agent master (backend only)

1. Migration: `sales_agents` gains `person_label` (nullable), `demand_class` (nullable,
   values validated against the market-segment-to-class vocabulary), `company_id` (nullable
   uuid, NULL = shared master), `source` (varchar, 'manual'|'import'). Seed the 38 codes from
   nothing - they arrive via import (AC-6.4), no hardcoded seed.
2. `sales_orders` gains nullable `sales_agent_id` FK.
3. Service: `sales_agent_service.resolve_or_create(db, code)` - normalised on
   `upper(btrim())`, creates with `source='import'`, returns row. Used by the import task.
4. pytest: resolve-or-create idempotent; unknown code creates + reports; demand_class
   vocabulary enforced.

### S2 - Aliases + reader fix + agent classification (backend)

1. Alias migration for the 7 SO columns (AC-1.1) and the PO/SPO history columns (AC-1.2),
   with deliberately-ignored mappings where no stored field exists. `bootstrap_env` replay.
2. Remove the "stated twice" RowProblem from `outstanding_reader.py` (AC-2.1). The diff layer
   is untouched - it is already correct.
3. `_classify_demand` gains step 4: agent's `demand_class` via the document's agent code
   (AC-3.1/3.2). Unmapped agent -> falls through to the existing report.
4. Outstanding SO apply stamps `sales_agent_id` (AC-6.5).
5. pytest: the captain's duplicate examples (identical pair + differing pair) import both
   halves; re-import reads unchanged (AC-2.3/2.4); SO-shaped fixture with agent-only
   classification resolves; agent unmapped -> reported not defaulted.

### S3 - Async conversion (backend). BUILT

1. New task functions in `app/tasks/import_tasks.py` per channel (outstanding SO, outstanding
   PO, purchase history, sales history, order inquiry), each: `_apply_import_job_scope` ->
   service apply -> `ImportOutcome` per row -> `complete_job(**completion_counts(),
   result=finalize(...))`. `update_job_progress(total_rows=...)` immediately after read.
2. Routes: keep `.../preview` synchronous at request scope (AC-4.2); `.../apply` becomes
   202 + job creation + `store_import_source_file` + enqueue, mirroring
   `app/api/v1/procurement/grn.py`. 400 before any job row when no single-company scope
   (AC-4.3). Job types named per channel (`outstanding_so_import`, `po_history_import`, ...)
   and labelled in `upload_activity` + both FE label maps.
3. The per-row outcome mapping: reader problems -> skipped with codes; diff results ->
   created/updated/unchanged/closed counts. Closed lines are recorded per row (they are the
   destructive half and belong in the job detail).
4. pytest: route 400-without-scope (job table stays empty); 202 + job row + source file;
   task path per-row outcomes land; worker-scope stamping (company snapshot honoured).

### S4 - Standard modal (frontend). BUILT, except the Playwright pass (item 5), which
needs a running stack and the captain's own two files

1. Rework the SCM upload dialogs (outstanding, history, order-inquiry channels) to the
   GRN/SPO behaviour contract: file select does NOTHING; Test button runs preview; Confirm
   queues and calls `notifyImportQueued()` (AC-5.1/5.3).
2. Shared warning/rejected-rows section: extract the component GRN/SPO use (or the customer
   importer's result panel if that is the settled one - the coder reads all three and names
   the winner in the PR) into `components/common/` and use it in BOTH the SCM dialogs and at
   least one existing dialog to prove it is genuinely shared (AC-5.2).
3. **Surface `unmapped_agents` in the Test result (AC-6.4 / AC-3.3).** The backend has
   returned it on BOTH responses since S2 and no screen reads it, so today an upload invents
   master rows the operator is never told about. Concretely:
   `app/(protected)/scm/reorder/services/outstandingImportService.ts` gains
   `unmapped_agents: OutstandingAgentNotice[]` (`{ code: string; is_new: boolean; reason:
   string }`) on `OutstandingPreview` AND on `OutstandingApplyResult` - the backend already
   sends the same key on both, and the commit's copy is the one that says which agents THIS
   upload created. `ProblemSections` in `components/OutstandingUploadDialog.tsx` gains a
   section for it, beside the unmapped-headers / row-problems / resolution-issues ones it
   already renders, worded as the backend words it ("new agent, unclassified") and NOT mixed
   into the rejected-row lists: nothing is skipped and no row failed, so putting it there
   would make a clean file read as a broken one. Empty list = no section.
4. vitest: no-validate-on-drop pinned (dropping a file fires no fetch); test-then-upload
   flow; warning section renders skip vs non-skip warnings without the false "rows are
   skipped" claim (the customer-importer B3 lesson); a preview carrying `unmapped_agents`
   renders the codes, and an empty one renders no section.
5. Playwright MCP verification against a real stack, sidebar-first, on the captain's own two
   files. Prod build for handoff.

### S5 - PO/SPO history split (backend, extends the existing history channel). BUILT

The real header row of `PO & SPO 2023.xlsx`, read from the file on 2026-08-14 (the earlier
draft of this PLAN recorded only the count, which blocked AC-1.2 in S2; the aliases belong
here with the structured reading):

`Item Code, Qty, Transfered Qty, Remaining Qty, Loading Date, Agent, Location, Doc No,
Doc Date, Delivery Date, Ref, Description, Creditor Name, Shipping Order, ICB Name,
Account Book, Is Posted, Running No, Post Gross Figure, Enable Auto Price, ICB To DocNo,
IB From SOKey, Import Post, Desc2, Width, Standard Price, FromSODocList`

1. The purchase-history reader accepts the structured 27-column format alongside the banded
   report format it reads today (detect by header shape). One reader, two writers: rows
   route by Doc No prefix - `SPO...` -> SPO history writer, else PO history writer.
2. SPO history lands closed/fully-received exactly like PO history (this is HISTORY, never
   netting supply - same rule the channel already enforces).
3. pytest: real-shaped fixture with both families; the flag-disagreeing rows follow the
   prefix; totals reconcile (13,641 + 13,550 + 1 grand-total row = 27,192).

**As built.** `app/services/scm/purchase_history_reader.py` is the one entry point:
`read_purchase_history(file_data, resolver)` looks for a row (within the first five)
resolving `Doc No` + `Item Code` + `Qty` together, which the banded report never has -
its `Doc No` is in the header band and its `Item Code` in the line band - and hands the
bytes to the structured parser or to `read_po_listing` accordingly. Both shapes come back
as one `PoListingResult`. `po_history_service` routes each order on
`po_listing_reader.doc_family` and stamps `SOURCE_SYSTEM` / `SPO_SOURCE_SYSTEM`; the write
is otherwise the one it already performed, which is what keeps "closed and fully received"
a single rule rather than two. Migration 358 seeds the 27 headers under doc type
`po_spo_history` (replayed by `bootstrap_env`). See amendments 17-24.

### S6 - The agent master gets a screen (backend + frontend). BUILT, except the browser pass

Everything above assumes the client fills in `demand_class` on 38 rows,
and today the only way to do that is `sales_agent_service.set_demand_class` from a Python
shell. So the classification the whole of AC-3 is built on cannot actually be entered, and
S1's honest report ("this agent carries no demand class") points the operator at a screen that
does not exist.

Deliberately MINIMAL - a list and an edit of the two annotation columns, not a CRUD master:

1. List: DataGrid of `sales_agents` (code, `person_label`, `demand_class`, `source`,
   `is_active`), search on the code. No create and no delete - a row is created by an upload
   meeting a code, which is the only place the codes are known, and deleting one would
   orphan the orders that name it.
2. Edit: modal, two fields, `person_label` free text and `demand_class` a clearable
   `SearchableSelect` over `DEMAND_CLASSES` plus unset. Writes through
   `sales_agent_service.set_demand_class` (which already refuses a word the policy cannot
   weigh, and already refuses to create an agent on the way past) plus the label.
3. **The AutoCount merge is the constraint on where this lands.** That branch already ships a
   read-only mirror page for this table at
   `master-data-management/sales-agents` (list + `[id]` detail), whose backend is
   `app/api/v1/master_data/sales_agents.py` with a `PATCH /{id}/annotation`. Three things must
   not be lost when the two chains meet:
 - `MirrorAnnotationUpdate` allows `internal_note` and `follow_up` ONLY (`extra="forbid"`),
     so `person_label` and `demand_class` must be added to it or the merged page silently
     cannot write them;
 - `SalesAgentResponse` does not declare them either, and FastAPI's `response_model` drops
     any field a schema does not declare, so the values would read as absent on a page that
     is in fact holding them;
 - `_MirrorBase.source` is `Literal["autocount", "manual"]` while S1's `source` column
     carries `manual` or `import`. An import-created agent would fail response validation on
     that page. Widen the literal (or map it) as part of the merge.
   Preferred shape: extend that existing page rather than build a second one, and if S6 ships
   before the merge, build it there so the two are the same surface by construction.
4. pytest: `set_demand_class` route happy path + auth denial + a word outside the vocabulary;
   a `source='import'` row serialises. vitest: the select offers exactly the two classes plus
   clear, and saving invalidates the list.

**What shipped.** Backend: `app/api/v1/master_data/sales_agents.py` (list, detail,
`PATCH /{id}/annotation`) mounted at `/api/v1/master-data/sales-agents` in
`app/api/v1/master_data/__init__.py`, gated `master_data.sales_agents.view` / `.edit` (four
slugs added to `app/rbac/permission_registry.py`, created by the startup `sync_permissions`);
`app/schemas/autocount_mirror.py`, `app/services/autocount_mirror_service.py`, and
`sales_agent_service.annotate`, which writes the class (guarded by `assert_demand_class`)
and the label onto the fetched row in the same transaction. Frontend:
`app/(protected)/master-data-management/sales-agents/` (page, list, edit modal, hook,
service, demand-class vocabulary) plus the sidebar entry under User Management in both
menu blocks (moved there from Product Management on the captain's call, amendment 16).
Tests: `tests/test_sales_agents_master_api.py` (16) and three vitest files (16). Browser
pass done with agent-browser on a prod build: sidebar entry between Market Segments and
Account, list of 40 rows, modal save and clear both round-trip to the DB.

## Sequencing note

S1 and S2 are one PR (agent + classification are the same story). S3 + S4 are one PR (async
and the modal are two sides of one contract change). S5 rides with S3's task work or follows.
S6 is independent of all of them and gated on the captain's go; it is what turns AC-3 from a
mechanism into a feature, so it should not wait behind S5.
Each PR: tests in-phase, browser verification for S4, `/code-review` before handoff.

## Risks

- The async conversion changes the apply response contract; the FE must move to job-based
  outcomes in the same PR or the drawer shows a job the page never linked to.
- The shared warning component touches GRN/SPO surfaces; regression tests on those dialogs
  are part of S4, not optional.
- `sales_agents.company_id` NULL-as-shared echoes the container_size cross-tenant read noted
  in the allowlist; acceptable for a master table, recorded in the migration docstring.
- The demand-class map ships empty: until the captain fills it, SO375073-class documents keep
  reporting unclassified. That is the designed behaviour, not a failure.
- **S6's list is unscoped by company.** Correct today (every row is `company_id IS NULL`, a
  shared master, and `sales_agents` is deliberately not `CompanyScopedMixin` - the mixin's
  auto-filter would hide the whole master). The day a company-OWNED row exists, this page is
  where cross-company visibility first appears: one company's admin would see, and be able to
  classify, another's agent. The route is the place to add the scope filter, and the namesake
  test (amendment 15) is the seam that already builds such a row.
