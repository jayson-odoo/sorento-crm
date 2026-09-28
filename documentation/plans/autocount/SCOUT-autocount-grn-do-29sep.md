# SCOUT: AutoCount Goods Receive Note and Delivery Order integration (#1354)

Status: **scout report, design only, no code.** Written 29 Sep 2026 (MYT) against `origin/main`
`484d0364d59c22615a1a112afce7e90687ccf508`. Alignment page:
`documentation/plans/autocount/ALIGN-autocount-grn-do.html`. Next step: owner answers the open
questions in section 8, vendor answers the questions in section 3.4, then a PLAN + UAC per lane.

Paths: `be/` = `sorento_crm_backend/`, `fe/` = `sorento_crm_frontend/app/(protected)/`.

**Reach of this scout.** The session's GitHub access is scoped to `jayson-odoo/sorento-crm` only,
so `jayson-odoo/foundryx-shared-service` (sprint-4 plans 13, 14, 16, 22 and its code) could not be
read, the same limit the finance scout hit (`documentation/plans/finance/PLAN-finance-billing-documents-27sep.md`
section 2.5). Everything said below about the shared service is taken from what this repo quotes of
it (the cross-repo contract, Appendix A of plan 22, and the pull client) and is marked
**[assumed]** where it is not quoted. The shared-service session confirms or corrects those.

## 0. The ask, in the owner's words

> "just got a list of API from the autocount ... think the useful one will be just GRN and DO for
> now, need to learn how we did for products, stock balance, CRM side need to have a pull from
> autocount button for verification, and also ingestion endpoint for automated push from shared
> service after pull is verified, this one for GRN and DO i think abit tricky cause it is by doc
> date, so meaning we need to loop by doc date to check? any design we can do to cater this ah? and
> the DO is abit tricky also cause yeah DO has a lot of field and we need to store pretty much
> everything there ya, including the branch name, also the reference to the sales order line also
> need to store, the GRN the reference to SPO/PO also need to store, but i think the API macam tak
> ada I am asking the vendor, basically we need to link the DO back to the SO and GRN back to the
> PO / SPO, the uploading of order tracking is still needed after the integration cause only the
> order tracking stores the transporter, actual delivery time and date, driver, lorry number etc i
> believe"

## 1. In plain words

- **No looping by doc date on every run.** The API has three doors per document: by DocDate, by
  LastModified, and JustNow (last hour). The shared service polls **JustNow every 10 minutes**,
  sweeps **LastModified for yesterday and today every night** as a safety net, and keeps a
  per-book cursor so an outage is caught up by walking only the days it missed. DocDate is used
  twice only: the one-off backfill, and a "re-pull this one day" button.
- **Same two-step as products and stock balance.** Pull for verification on the CRM (a review
  screen showing what would change, with an Excel view and a compare against the Excel you upload
  today), then the owner switches the push on in the shared service. Same endpoint family, same
  envelope, same verdicts.
- **DO lands on the delivery order you already have** (`orders` / `order_lines`, the table the
  tracking upload writes). Every field AutoCount sends is kept: the fields the CRM uses as columns,
  the whole record as sent in one JSON column, the branch code and branch name on the header, and
  each DO line pointing at the sales order line it came from.
- **GRN lands on the GRN you already have** (`picking_headers` / `picking_lines`), each line
  pointing at the PO line or the SPO line it received against.
- **The link depends on one vendor answer.** AutoCount itself records, on every DO and GRN line,
  which document line it was transferred from (`FromDocType`, `FromDocNo`, `FromDocDtlKey`). If the
  vendor's API returns those three, the link is exact. If not, section 3.4 asks for them and names
  the fallback.
- **The order tracking upload stays**, and owns transporter, driver, lorry, actual delivery date
  and time, checker and trips. AutoCount owns everything else on the DO. Both write the same
  delivery record, matched on the DO number, in either order.

## 2. Today: how products and stock balance flow, end to end

### 2.1 Two directions, one integration row

| Direction | Who calls whom | Door |
| --- | --- | --- |
| Pull (verification) | CRM calls the shared service | `POST /api/v1/autocount/snapshots`, `GET /snapshots/{id}`, `GET /snapshots/{id}/rows?page=` (`be/app/services/foundryx_autocount_client.py:166`, `:176`, `:185`) |
| Push (automated) | Shared service calls the CRM | `POST /api/v1/external/ingest/{entity}` (`be/app/api/v1/external/ingest.py:722`) |

Both use the one `integrations` row named `foundryx-esb`: `config_json.base_url` plus the
Fernet-encrypted `credentials_json.api_key` for the pull (`foundryx_autocount_client.py:54`,
`:82-111`), and an `integration_api_keys` hash resolving to the integration's `act_as_user_id` for
the push (`be/app/dependencies.py:560-587`). Configured in Integration Management with a Test
button (`fe/integration-management/integrations/components/IntegrationDetailView.tsx:60-79`,
route `be/app/api/v1/integrations/admin.py:64-92`).

### 2.2 The pull button and the review screen (CRM)

1. **Button.** "Pull from AutoCount" beside Import on Products
   (`fe/master-data-management/products/components/ProductsList.tsx:183`, `:1001-1007`) and Stock
   Balance (`fe/inventory-management/stock/components/StockBalanceGrid.tsx:92`, `:364-370`), via
   `useAutocountPullAction` (`fe/system-management/import-jobs/autocount-pull/hooks/useAutocountPull.ts:224-248`).
   Permission-gated per entity (`master_data.products.autocount_pull`,
   `inventory.stock.autocount_pull`, `be/app/services/autocount_pull_service.py:38-41`). The label
   turns into "Review pull" when the user has an open one.
2. **Start.** `POST /api/v1/autocount/pulls` (`be/app/api/v1/integrations/autocount_pull.py:147`)
   asks the shared service for a snapshot of the whole entity for one company
   (`{companyCode, entity}`). A pull is ONE `import_jobs` row (`job_type`
   `autocount_products_pull` / `autocount_stock_pull`); its state lives in
   `job_metadata["autocount_pull"]` (`autocount_pull_service.py:198-212`). No staging table.
3. **Advance.** A scheduler tick every 30 s (`be/app/scheduler/task_scheduler.py:551-561`,
   `advance_building_pulls` at `autocount_pull_service.py:308-350`) moves a building pull on when
   the snapshot is ready, so nobody has to keep the tab open.
4. **Preview.** RQ `imports` queue, `preview_autocount_pull` (`be/app/tasks/autocount_pull_tasks.py:119`)
   pages every snapshot row (cap 100 pages, `foundryx_autocount_client.py:194-215`) and runs the
   SAME ingest service with `dry_run` (`:431`), writing per-row verdicts to `import_job_rows`.
   Phase becomes `review`.
5. **Review screen** (`fe/system-management/import-jobs/[id]/page.tsx:28-40`,
   `AutocountPullReview.tsx`): three tabs, **Changes** (the dry-run verdicts), **Excel view** (the
   pull in the manual upload template's columns), **Compare with my Excel** (the operator's own
   workbook, parsed in the browser, compared by key; `be/app/services/autocount_pull_compare.py:70-221`).
   Compare is advisory, not a gate.
6. **Confirm** (`autocount_pull.py:286`) creates a second `import_jobs` row
   (`autocount_*_apply`, `autocount_pull_service.py:746-778`) and runs the real ingest.
   **Discard** (`:302`, service `:786-809`) is immediate, no dialog, idempotent.
7. **Push switch.** There is **no "verified" or "push enabled" flag in the CRM.** The mode lives
   in the shared service, which refuses a pull with 409 `PUSH_ACTIVE` / `PULL_NOT_ENABLED` once
   the push is on (`fe/.../autocount-pull/services/autocountPullService.ts:118-119`). A confirmed
   pull records nothing that switches the push on; the owner does that in the shared service.

### 2.3 The ingest endpoint (shared service pushes)

- `POST /api/v1/external/ingest/{entity}?dry_run=`, `/ingest/{entity}/deletions`,
  `/read/{entity}`, `GET /external/contract` (`ingest.py:722`, `:853`, `:1001`;
  `be/app/api/v1/external/contract.py:230`). Contract version **2.6** (`ingest.py:251`).
- Auth `X-API-Key`; permission slug per entity and per verb (`.edit` / `.view` / `.delete`,
  `ingest.py:88-147`, `be/app/api/v1/external/permissions.py:61-99`).
- **Company anchor**: `companyCode` in the body or the integration's `config_json.company_code`;
  four 422 codes (`be/app/api/v1/external/company_anchor.py:135-174`).
- **Envelope** `{"companyCode": "SRT", "records": [...]}`; 1000 records max (413
  `BATCH_TOO_LARGE`), 2000 lines per document; `extra="forbid"` everywhere
  (`be/app/schemas/canonical_masters.py:25-47`, `be/app/schemas/canonical_documents.py:188-192`).
- **Response** always 200: `{dry_run, summary{total, created, updated, failed, retryable,
  unchanged?}, records[{source_ref, outcome, entity_id, errors?, warnings?, diff?, lines?}]}`
  (`be/app/services/master_ingest_service.py:167-285`). One SAVEPOINT per record, so one bad record
  never sinks the batch.
- **Idempotency key** = the record's `source_ref`, never a header. Masters and document headers:
  `integration_references` unique on `(source_system, entity_type, source_ref, company_id)`
  (`be/app/models/integration_reference.py:77-97`). Document lines: `source_ref` column on the line
  table, format `{database}:{DocKey}:{DtlKey}`. Stock balances: keyed by (item, location), ref only
  echoed (`be/app/services/stock_balance_ingest_service.py:6-9`).
- **Provenance**: `source_system='autocount'`, `source_ref`, `source_doc_no` on headers and in
  `integration_references` with `first_seen_at` / `last_synced_at`. Only `billing_documents` also
  carries `source_modified_at` (AutoCount LastModified) and uses it as a **stale guard**: an older
  push answers `unchanged` with warning `stale_ignored` (contract plan section 12,
  `be/app/models/finance.py:125`). No other entity has a version guard today.
- **Deletes**: `/deletions` hard-deletes when nothing references the row, else cancels in place
  (verdict `deactivated`), via `be/app/services/dependent_probe.py`.
- **Mirror tables**: none. `autocount_mirror_service.py` is a reader for `sales_agents` only
  (`be/app/services/autocount_mirror_service.py:23-84`); every entity writes straight into the CRM
  domain table.
- **Explicit exclusion today**: "delivery orders, GRNs, invoices and stock stay upload-only"
  (`PLAN-ingest-parity-standardisation.md:18`, D21 `:45`). Stock and invoices have since moved; this
  scout is the proposal to move DO and GRN.

### 2.4 The shared service side [assumed, quoted]

- Plan 22 (`sprint-4/22-autocount-db-etl.md`) Appendix A is the document contract; its
  `SorentoSink` (`service_backend/modules/autocount/sinks_sorento.py`) is coded against it
  (`PLAN-autocount-cross-repo-contract.md:1-16`).
- Its ETL "already watermarks on" a last-modified timestamp for documents (contract plan A3,
  `:562`). A first live run minted master refs with the watermark in the key (`:338`), so a
  watermark exists there and was once mishandled.
- The HTTP source (`sprint-5/08-autocount-http-source.md`, cited at
  `PLAN-autocount-brands-ingest.md:7`) exposes no numeric item key (`PLAN-ingest-products-code-wins.md`,
  contract section 11). That is the vendor HTTP API #1354 lists, so **whether it exposes DocKey
  and DtlKey on documents is not known from here** (vendor question V3).
- The pull mode switch per entity (`PULL_NOT_ENABLED`, `PUSH_ACTIVE`) and the 24 h snapshot store.

### 2.5 What already exists for DO and GRN in the CRM

| Thing | Where | State |
| --- | --- | --- |
| DO header | `orders` (`be/app/models/order.py:287-358`), unique `(company_id, order_number)` | Fed by the tracking upload (Master sheet) and the DO detail import. No `source_ref`, no SO link (only free-text `customer_ref`). Has `debtor_code`, `debtor_name`, `agent`, `salesman`, `is_cancelled`, money columns, `warehouse`. |
| DO line | `order_lines` (`order.py:361-425`), unique `(order_id, line_sequence)` | `sales_order_line_id` FK is declared "filled by the DO integration" (`order.py:391-403`), read by `be/app/services/sales/achievement_service.py:342`, `:610`, **written by nothing**. |
| DO detail import | `POST /order-management/orders/import-order-lines` (`be/app/api/v1/order_management/orders.py:1350`) | Upserts by (order, product, warehouse) (`be/app/services/order_service.py:3422-3424`). |
| Tracking upload | `POST /order-management/orders/import-tracking` (`orders.py:1279-1340`), parser `order_service.py:2707` | Sheets "Master" + "Overall Tracking"; matches on DO number case-insensitively (`:2838-2844`); writes transporter, driver, lorry, date + time, checker, trips, W/H; sets delivered + KPI (`:3130-3198`). |
| GRN header | `picking_headers` with `picking_type='goods_received'` (`be/app/models/procurement.py:633-689`) | `picking_number` = GRN DocNo; `spo_number` display only; no PO ref, no container. |
| GRN line | `picking_lines` (`procurement.py:701-769`) | `spo_allocation_id` FK (the SPO line), `spo_number_raw`, `po_line_id` FK **written by nothing**. |
| GRN to SPO matcher | `be/app/services/grn_spo_matching.py:96-403` | FIFO by (product, normalised SPO number); never uses the PO number or container. Forward-match runs when an SPO arrives (`ingest.py:447-474`). |
| GRN imports | `be/app/api/v1/procurement/grn.py:150-197`, listing core `:1779`; external `POST /external/grn/` (`be/app/api/v1/external/grn.py:27`) | Manual uploads plus an older external route under `pin_scope_to_companies`, not the anchor. |
| SPO line | `spo_allocations` (`procurement.py:442-629`) | `source_ref` = AutoCount DtlKey, `source_doc_ref` = DocKey, `po_line_id`, `container_number`. |
| SO / PO lines | `sales_order_lines.source_ref` (`order.py:575`), `purchase_order_lines.source_ref` (`procurement.py:845`) | DtlKey refs, so a `from_line_ref` resolves by one indexed lookup. PO/SPO lines already accept `from_so_line_ref` / `from_po_line_ref` (`canonical_documents.py:128-156`, `:317-319`), sourced from AutoCount's `FromSODtlKey`: the precedent for DO and GRN. |
| Branch | nothing | No branch table or column anywhere. `orders.shipping_address_id` is a bare UUID with no FK (`order.py:306`). |

## 3. Design

### 3.1 Sync without looping doc dates

The vendor's three doors, per document type (GRN `(13)`, DO `(15)`; SO and PO the same shape):

| Door | Filter | Use in this design |
| --- | --- | --- |
| `...JustNow` | LastModified in the last hour | **Near-real-time path.** Every 10 minutes. The one-hour window gives 50 minutes of overlap, so a missed tick or two is harmless. |
| `...byLastModified?lastModified=yyyyMMdd` | LastModified on that day (or since that day: **V1**) | **Incremental cursor and safety net.** Nightly for yesterday and today. After an outage, walks from the cursor day to today: the number of calls equals days missed, not documents or doc dates. |
| `...bydocdate?DocDate=yyyyMMdd` | DocDate on that day | **Backfill only** (oldest first, one day per call, from the start date) and the **manual "re-pull one day"** action. Also the deletion sweep in 3.3. |

**Cursor state** (shared service, per company book and per document type)
[shared-service design, assumed shape]:

```
cursor = {book: "db1", doc_type: "DO", last_complete_day: "2026-09-27",
          last_justnow_at: "2026-09-28T09:40:00+08:00", backfill_done_through: "2026-09-27"}
```

- **Nightly (02:00 MYT):** for `d` in `last_complete_day - 1 day` .. `today`: call
  byLastModified(d), push every document whose `(source_ref, LastModified)` differs from the last
  pushed pair, then set `last_complete_day = today - 1`. The one-day overlap covers a document
  modified just before midnight and a clock or timezone skew between AutoCount and the service
  (**V1** asks which zone LastModified is in).
- **JustNow (every 10 min):** push every document whose `(source_ref, LastModified)` is new. It
  never moves `last_complete_day`: only a completed day sweep does, so a JustNow outage longer than
  an hour is repaired by the next night without anyone noticing it.
- **Dedupe before push, stale guard at the CRM.** The shared service skips a document whose
  LastModified equals the last one it pushed (saves traffic). The CRM keeps `source_modified_at`
  and answers `unchanged` for an identical or older push (billing precedent, 2.3), so JustNow and
  the nightly sweep can overlap freely and a replayed batch is safe.
- **Backfill:** DocDate from the start date to the go-live day, oldest first, one day per call,
  batches of up to 1000 documents, GRN and DO in parallel streams. Resumable from
  `backfill_done_through`. After it finishes, one byLastModified sweep from the backfill's first
  day catches documents edited during the backfill.
- **Manual re-pull of one day:** DocDate(d) for the one day, pushed as normal; used when the
  operator suspects a day. On the CRM it is the pull screen's date picker (3.4.1).

If **V1** answers that byLastModified is "on or after the day", the nightly loop is one call per
night and the outage walk disappears. Nothing else changes.

### 3.2 Edits after posting, cancels, reruns

- **Edit** bumps LastModified (**V5** to confirm it does for detail-only edits), so the next
  JustNow or sweep re-sends the WHOLE document. The CRM upserts header and lines by their refs; a
  line not in the push is deleted, or cancelled in place when something references it (the
  document-ingest rule, contract section 3). Line ids survive re-pushes.
- **DocNo changed in AutoCount**: the ref is DocKey-based, so the row follows; `source_doc_no` and
  `order_number` / `picking_number` update. A DocNo change that collides with another row's number
  in the company is `failed` with `errors.doc_no` (the SO ladder's `ReferenceConflict` rule).
- **Cancelled** (AutoCount Cancelled flag, **V6** for the field name): an update, `is_cancelled`
  on the DO, `picking_status='cancelled'` on the GRN; the row and lines stay.
- **Rerun** of any batch or any day: safe (refs + stale guard).

### 3.3 Deletions

AutoCount hard-deletes a document; neither LastModified nor JustNow can show an absence.

- **Ask first (V6):** a deleted-document log or endpoint from the vendor. If one exists, the
  shared service calls `/ingest/{entity}/deletions` with the refs.
- **Fallback, no vendor change:** a nightly **reconciliation sweep** by DocDate over a trailing
  window (recommend 45 days, Q9): for each day, DocKeys in AutoCount vs refs the shared service has
  pushed for that doc date; the difference goes to `/deletions`. The CRM hard-deletes an
  unreferenced DO or GRN, and cancels one that something references (a DO line an invoice line
  points at, a GRN line counted in a receipt). Deletions older than the window are caught by a
  monthly full sweep of the window's older months, or accepted as a known gap (stated in Q9).

### 3.4 Data model

**Principle:** store what AutoCount sends, all of it, without a migration per new field: typed
columns for the fields the CRM reads, plus the full record as sent in one JSONB column
(`source_payload`). A field that later needs a column is promoted from the JSON by a data
migration. This is how "store pretty much everything" is met without guessing a 60-column schema
before the vendor has shown one real record (Q1).

#### 3.4.1 Delivery Order -> `orders` + `order_lines` (existing tables, new columns)

Header (`orders`), AutoCount-owned. `*` = new column.

| Column | From AutoCount (expected name, **V3/V7**) | Notes |
| --- | --- | --- |
| `source_system`* | constant `autocount` | provenance |
| `source_ref`* | `{db}:DO:{DocKey}` | idempotency key, also in `integration_references` (entity `delivery_orders`) |
| `source_modified_at`* | `LastModified` | stale guard |
| `source_payload`* (JSONB) | the whole header record as sent, lines excluded | every field kept |
| `order_number` | `DocNo` | existing; match key for the tracking upload |
| `order_date` | `DocDate` | existing |
| `customer_id`, `debtor_code`, `debtor_name` | `DebtorCode`, `DebtorName` | existing; resolve within company, keep code when unresolved (billing rule, warning `customer_unresolved`) |
| `branch_code`*, `branch_name`* | `BranchCode` on the DO; name from the branch table `(11)` by (`DebtorCode`, `BranchCode`) | shared service resolves the name; CRM stores both as delivered (Q2) |
| `delivery_address`* (JSONB) | `DeliverAddr1..4`, `DeliverPostCode`, `DeliverContact`, `DeliverPhone1` [assumed names] | as sent |
| `agent`, `salesman` | `SalesAgent` | existing |
| `customer_ref` | `Ref` | existing column, today free text from the upload |
| `remarks` | `Description` / `Remark1..4` | existing |
| `warehouse` | header `SalesLocation` if any | existing |
| `is_cancelled` | `Cancelled` | existing |
| `subtotal_amount`, `tax_amount`, `total_amount`, `currency_code`*, `currency_rate`* | `NetTotal`, `Tax`, `Total`, `CurrencyCode`, `CurrencyRate` | existing money columns become usable (finance plan 2.3 calls them unusable today) |
| `so_numbers`* (text[]) | derived: distinct `FromDocNo` over lines where `FromDocType='SO'` | display and search; the link itself is per line |

Lines (`order_lines`):

| Column | From AutoCount | Notes |
| --- | --- | --- |
| `source_ref`* | `{db}:DO:{DocKey}:{DtlKey}` | line identity across re-pushes |
| `line_sequence` | `Seq` | existing, NOT NULL, unique per order |
| `product_id` (+ `item_code`*) | `ItemCode` | resolve within company; keep code when unresolved |
| `warehouse_id` (+ `location_code`*) | `Location` | `warehouse_unresolved` rule |
| `quantity`, `uom`* | `Qty`, `UOM` | |
| `unit_price`, `discount`, `total`, `tax`, `total_excluding_tax`, `total_including_tax` | `UnitPrice`, `Discount`, `SubTotal`, `Tax`, `SubTotalExTax`, `SubTotal` [assumed] | existing |
| `description`* | `Description` | |
| `from_doc_type`*, `from_doc_no`*, `from_line_ref`* | `FromDocType`, `FromDocNo`, `{db}:{FromDocKey}:{FromDocDtlKey}` | kept as sent, always |
| `sales_order_line_id` | resolved from `from_line_ref` against `sales_order_lines.source_ref` | existing FK, finally written; null + warning `so_line_unresolved` when the SO line has not arrived; when that SO line lands later, the SO ingest fills it by matching `order_lines.from_line_ref` (the billing `against_doc_no` precedent), since an unchanged DO is never re-sent (Q10) |
| `source_payload`* (JSONB) | the whole line as sent | |

Header-level SO link: none as a single FK. A DO in AutoCount can combine lines from more than one
SO, so the truth is per line; `so_numbers` is the header summary.

#### 3.4.2 Goods Receive Note -> `picking_headers` + `picking_lines` (existing, new columns)

Header (`picking_headers`, `picking_type='goods_received'`):

| Column | From AutoCount | Notes |
| --- | --- | --- |
| `source_system` | `autocount` (new value beside `ui` / `import` / `external_api`) | existing column |
| `source_ref`*, `source_modified_at`*, `source_payload`* | `{db}:GRN:{DocKey}`, `LastModified`, whole header | as DO |
| `picking_number` | `DocNo` | existing, unique per company |
| `picking_date` | `DocDate` | existing |
| `supplier_id`* (+ `creditor_code`*, `creditor_name`*) | `CreditorCode`, `CreditorName` | resolve within company, keep code |
| `ref`* | `Ref` | may be the container number when the GRN is against an SPO (V8) |
| `container_number`* | derived: `Ref` through `extract_container_number` (`be/app/services/rules/shipping_order_rules.py:33-63`) when the GRN's source lines are SPO | same rule the SPO feed uses |
| `supplier_do_no`* | `SupplierDONo` [assumed] | the supplier's paper DO |
| `spo_number` | derived: distinct `FromDocNo` of SPO-family lines, comma-joined | existing display column, same meaning as today |
| `picking_status` | `Cancelled` -> `cancelled`, else `received` [confirm the value set used by GRN screens] | |

Lines (`picking_lines`):

| Column | From AutoCount | Notes |
| --- | --- | --- |
| `source_ref`* | `{db}:GRN:{DocKey}:{DtlKey}` | |
| product / warehouse | `ItemCode`, `Location` | `destination_warehouse_id` |
| `quantity_picked` | `Qty` | `quantity_expected` = the source PO/SPO line's outstanding at receipt, or null |
| `from_doc_type`*, `from_doc_no`*, `from_line_ref`* | `FromDocType`, `FromDocNo`, `{db}:{FromDocKey}:{FromDocDtlKey}` | kept as sent |
| `po_line_id` | `from_line_ref` against `purchase_order_lines.source_ref` | existing FK, finally written |
| `spo_allocation_id` | `from_line_ref` against `spo_allocations.source_ref` | exact; SPO and PO share one AutoCount table, so ONE ref resolves against either, whichever holds it |
| `spo_number_raw` | `FromDocNo` when SPO family | existing; feeds the FIFO matcher only when `from_line_ref` is absent |
| `source_payload`* | whole line | |

**SPO vs PO.** The vendor note: an SPO is a PO with `ShippingPO='T'`, container in `Ref`, DocNo
starting `SPO`, but users forget the flag or the container. The CRM already classifies SPO by the
PO feed (`is_shipping_order`, `SPO-` prefix refusal under `purchase_orders`,
`canonical_documents.py:295-299`), so the GRN does not decide it: its `from_line_ref` resolves to
whichever table the source line landed in. When the container arrives later on the SPO, the GRN's
`container_number` is refreshed by the nightly `relink_allocations_for_container` pass
(`shipping_order_rules.py:94`, `:134`).

#### 3.4.3 Where the API may lack the link, and what could carry it

| Link | Best (exact) | Fallback 1 | Fallback 2 |
| --- | --- | --- | --- |
| DO line -> SO line | `FromDocDtlKey` (+ `FromDocKey`) on the DO line | `FromDocNo` + `ItemCode` + position: unique when the SO has one line of that item (the `from_so_numbers` claim rule, contract section 9 item 9) | header `Ref` or `Description` naming the SO number (free text; unreliable) |
| GRN line -> PO / SPO line | `FromDocDtlKey` on the GRN line | `FromDocNo` + `ItemCode` -> existing FIFO matcher (`grn_spo_matching.py`) | header `Ref` = container -> `spo_allocations.container_number` + item |
| DO -> branch name | `BranchCode` on DO + branch table | DO delivery address block as sent | none |

#### 3.4.4 Vendor questions (exact wording to send)

- **V1.** For `...byLastModified?lastModified=yyyyMMdd`: does it return documents last modified
  ON that day only, or on and AFTER that day? Which time zone is LastModified in (MYT or UTC)?
  Does each returned document carry the full LastModified timestamp (date and time)?
- **V2.** Do the document endpoints (GRN, DO, SO, PO) page like the branch table
  (`page`, `pageSize`, max 1000)? If not, what is the most documents one call returns, and what
  happens on a day with more?
- **V3.** Does each GRN and DO record include its detail lines in the same response? For the
  header, please confirm `DocKey`, `DocNo`, `DocDate`, `LastModified`, `Cancelled`; for each
  line, `DtlKey` and `Seq`. **And please include, per line, `FromDocType`, `FromDocNo`,
  `FromDocKey`, `FromDocDtlKey` (the transfer-from fields of `DODtl` / `GRNDtl`).** These are what
  link a DO line to its SO line and a GRN line to its PO / SPO line.
- **V4.** Do the SO and PO endpoints return `DocKey` and each line's `DtlKey`? (The CRM keys SO and
  PO lines on DtlKey today; a DO line's `FromDocDtlKey` only helps if it matches.)
- **V5.** Does `...JustNow` cover edits (LastModified in the last hour) or only new documents
  (created in the last hour)? Does an edit to a detail line alone update the header's LastModified?
- **V6.** When a GRN or DO is deleted in AutoCount, is there any way to see it (a deleted log,
  an audit table, an endpoint)? What is the Cancelled field called and what values does it take?
- **V7.** On the DO header, which field holds the branch (`BranchCode`?), and is the branch table
  keyed by (`AccNo`, `BranchCode`)? Please confirm the delivery address field names on the DO.
- **V8.** On the GRN header: `CreditorCode`, `Ref`, `SupplierDONo` present? Is the SPO container
  number ever on the GRN `Ref`, or only on the SPO?
- **V9.** `db1` is which company book (SRT or MOCHA)? What is the path for the other one?
- **V10.** Rate limits and auth for `hapi.sorento.cc.cd`; can a call run every 10 minutes per
  document type per book?
- **V11.** Can one DO line be transferred from more than one SO line (combined), or is it always
  one source line? Same for a GRN line and PO lines.

### 3.5 The CRM side

#### 3.5.1 Pull for verification, GRN and DO

Same machinery as 2.2, two new pull entities: `delivery_orders` and `goods_receive_notes`.

| Aspect | Products / stock | GRN / DO | Why different |
| --- | --- | --- | --- |
| Scope of a pull | whole entity, one company | **one company + a DocDate range**, default yesterday, max 31 days | a whole-book document snapshot is years of rows; the snapshot request gains `docDateFrom` / `docDateTo` |
| Where the button is | Products list, Stock Balance grid | **Delivery Orders list** (`fe/order-management/orders/components/OrdersList.tsx`, beside Import tracking) and **GRN list** (`fe/procurement-management/grn/`, beside Import) | same placement rule: beside the upload it will replace |
| Changes tab | dry-run verdicts | same, per document, with `lines{created, updated, deleted, cancelled}` and link warnings (`so_line_unresolved`, `po_line_unresolved`) | |
| Excel view | the manual template's columns | the DO detail import's columns (Doc No, Item Code, Location, Qty...) and the GRN listing + lines columns | the operator recognises the sheet |
| Compare with my Excel | key = item code | key = (DocNo, ItemCode, Location), compares Qty and the link (SO no. / PO-SPO no.) | |
| Link coverage line | none | new headline: "N of M lines linked to a sales order line" / "... to a PO or SPO line" | this is the thing the owner is verifying |
| Confirm | applies | applies (lands the range) | |
| Permission | `.autocount_pull` per entity | `order_management.orders.autocount_pull`, `procurement.grn.autocount_pull` [slug names to confirm against the registry] | |

The push switch stays in the shared service, per entity and per company, exactly as products
(Q5). The CRM adds nothing that records "verified".

#### 3.5.2 Ingestion endpoint contract (proposed contract 2.7)

Same door, two new entities: `POST /api/v1/external/ingest/delivery_orders`,
`/ingest/goods_receive_notes`, their `/deletions` and `/read`. Same envelope, same anchor, same
1000 / 2000 caps, same verdicts, same error shape.

```json
{
  "companyCode": "SRT",
  "records": [
    {
      "source_ref": "db1:DO:55120",
      "source_modified_at": "2026-09-27T16:42:10+08:00",
      "doc_no": "DO-2609/0077",
      "doc_date": "2026-09-27",
      "status": "posted",
      "customer_ref": "db1:300-R009", "customer_code": "300-R009", "customer_name": "...",
      "branch_code": "KL01", "branch_name": "KLCC SITE OFFICE",
      "delivery_address": {"line1": "...", "line2": "...", "postcode": "...", "contact": "...", "phone": "..."},
      "agent_code": "SEAN I",
      "ref": "THE MET KL", "description": "...",
      "currency_code": "MYR", "currency_rate": 1,
      "net_total": 1000.00, "tax_total": 0, "total": 1000.00,
      "raw": { "...every header field exactly as AutoCount returned it...": "" },
      "lines": [
        {
          "source_ref": "db1:DO:55120:1", "line_number": 1,
          "product_ref": "db1:ABC-1", "product_code": "ABC-1", "description": "...",
          "warehouse_code": "BRW", "uom": "PCS", "quantity": 10,
          "unit_price": 100.00, "discount_amount": 0, "net_amount": 1000.00, "tax_amount": 0,
          "from_doc_type": "SO", "from_doc_no": "SO-2609/0012", "from_line_ref": "db1:1234:1",
          "raw": { "...every line field as returned...": "" }
        }
      ]
    }
  ]
}
```

GRN is the same shape with `supplier_ref` / `supplier_code` / `supplier_name`, `supplier_do_no`,
`ref` (no branch, no delivery address), and lines with `from_doc_type` `PO` (SPO is a PO in
AutoCount), `from_doc_no`, `from_line_ref`.

- **Idempotency key:** `(company, entity, source_ref)` via `integration_references` + a partial
  unique index `(company_id, source_ref)` on `orders` and `picking_headers`; lines by their own
  `source_ref` within the header.
- **Provenance:** `source_system`, `source_ref`, `source_doc_no`, `source_modified_at`,
  `integration_references.last_synced_at`, `raw` stored as `source_payload`.
- **Stale guard:** billing rule verbatim (older or identical `source_modified_at` -> `unchanged`,
  `stale_ignored`; a push without it always applies and clears it).
- **Adopt by number (first sync):** a DO whose `doc_no` matches an existing `orders.order_number`
  with no `source_ref` (created by the tracking Master sheet or the DO detail import) is ADOPTED,
  not duplicated: the row keeps its id and its tracking columns (3.6). Lines adopt by the D11 passes
  (contract section 9 item 6). Same for GRN on `picking_number`.
- **Link resolution:** `from_line_ref` -> SO line / PO line / SPO line within the anchor; when it
  does not resolve, the line lands with the FK null, the three `from_*` values kept, warning
  `so_line_unresolved` / `po_line_unresolved`; never `retryable` (the billing rule; a DO must not
  wait for an SO that may never come). When the SO, PO or SPO line lands later, its own ingest
  fills the waiting FKs by matching the stored `from_line_ref`, one indexed update per push.
- **`raw`:** a free JSON object, the one deliberate hole in `extra="forbid"`; size cap 32 KB per
  header and 8 KB per line, over the cap the record `failed` with `errors.raw`.
- **Error shape:** unchanged (`errors: {field: reason}`, `_` for internal).
- **Post-write hooks:** DO -> SO line `qty_delivered` is NOT recomputed from DOs (the SO push stays
  its source; Q11). GRN -> the existing SPO forward-match does not run for linked lines.

**Where it cannot match products and stock balance:** (a) the pull is date-scoped, not whole-entity;
(b) the payload carries `raw`; (c) a version guard exists (like billing, unlike SO/PO); (d) the
deletion feed is a reconciliation sweep, not a snapshot diff.

#### 3.5.3 What the shared service must add

1. HTTP source for `(11)` branch, `(13)` GRN, `(15)` DO against `hapi.sorento.cc.cd`, per book.
2. Cursor store and the three schedules in 3.1 (JustNow 10 min, nightly LastModified sweep,
   nightly DocDate deletion sweep) plus backfill and one-day re-pull.
3. Branch name lookup by (`DebtorCode`, `BranchCode`) from `(11)`, cached, refreshed daily.
4. Mapping to the 2.7 records, refs `{db}:DO|GRN:{DocKey}[:{DtlKey}]`, `from_line_ref` in the same
   `{db}:{DocKey}:{DtlKey}` form the SO/PO lines carry.
5. Snapshot support for `delivery_orders` / `goods_receive_notes` with a DocDate range, and the
   per-entity pull / push mode (`PULL_NOT_ENABLED`, `PUSH_ACTIVE`).
6. `SorentoSink` entries for the two entities and their `/deletions`.

### 3.6 DO and order tracking on one delivery record

One `orders` row per (company, DO number). Column ownership, written down and tested:

| Owner | Columns |
| --- | --- |
| AutoCount (ingest) | `order_number`, `order_date`, customer / debtor, branch, delivery address, agent / salesman, `customer_ref`, `remarks`, money, `is_cancelled`, all lines, all `source_*` |
| Tracking upload | `actual_delivery_date`, `pickup_time` (the time), `transporter_id` / `transporter`, `driver_name`, `lorry_plate`, `checker`, `trips`, `delivery_days`, `kpi_warning`, the delivered status |
| Either, first writer wins | `warehouse` (upload W/H column vs AutoCount location) |

Rules:
- The ingest never writes a tracking column; the upload never writes an AutoCount column on a row
  whose `source_system='autocount'` (its Master sheet still creates rows that do not exist yet,
  Q8).
- **Order independent.** Tracking first: the Master sheet creates the row, the DO push adopts it by
  number (3.5.2). DO first: the tracking row finds it by number as it does today.
- The **DO detail import** retires once the DO push is on (the push is the source of lines);
  the **tracking upload stays** and becomes tracking-only in effect.
- Measured quirk to carry into the plan: `orders.actual_delivery_date` is declared `Date`
  (`order.py:299`) while the upload builds a datetime from Date + Time (`order_service.py:3135-3144`);
  the time survives in `pickup_time` (String). The owner wants "actual delivery time and date":
  confirm the live column type before the plan, and if it is `date`, show the time from
  `pickup_time`.

## 4. Slices

| # | Slice | Repo | Needs vendor first | Track | Est. |
| --- | --- | --- | --- | --- | --- |
| V0 | Send V1 to V11; get one real DO and one real GRN JSON per book | none (owner) | - | - | 0 |
| S1 | HTTP source for branch, GRN, DO; cursor store; snapshot entities with a DocDate range | shared | V1, V2, V3, V9 | full | 1 lane |
| S2 | Contract 2.7: `delivery_orders` + `goods_receive_notes` ingest, read, deletions; migration (new columns on `orders`, `order_lines`, `picking_headers`, `picking_lines`); link resolution; adopt by number; column ownership vs tracking upload | CRM | V3 (field names; can start on the proposed shape) | full (migration, new ingest surface, security-reviewer) | 1.5 lanes |
| S3 | Pull for verification for both entities: date-range pull, Excel view, compare, link coverage headline; permission slugs | CRM | none beyond S1's snapshot shape | full (new permissions) | 1 lane |
| S4 | Sink, JustNow 10 min, nightly sweeps, deletion reconciliation, backfill runner, one-day re-pull | shared | V5, V6, V10 | full | 1 lane |
| S5 | DO detail page shows SO number / SO line per line and the tracking block; GRN page shows PO / SPO line per line; retire the DO detail import and the GRN lines import after the push has run clean (Q7) | CRM | none | small fix / standard | 0.5 lane |

Order: V0 now; S2 can start on the proposed shape in parallel with V0 (the `raw` column absorbs
field-name surprises); S1 after V1/V2/V3/V9; S3 after S1's snapshot shape; S4 after S2 is on main;
S5 last. **Estimate: about 5 lanes, 3 CRM (S2, S3, S5) and 2 shared service (S1, S4).**

## 5. Risks

1. **The API has no transfer-from fields (V3).** Then the link is by number and item, which cannot
   tell two lines of the same item on one SO apart; the verification pull's link coverage headline
   shows the damage before the push is switched on.
2. **byLastModified means "on that day" and LastModified is date-only or in another zone (V1).**
   Handled by the one-day overlap, but a date-only LastModified makes the stale guard weaker (two
   edits the same day compare equal); then the CRM compares a content hash of `raw` instead.
3. **No paging on document endpoints (V2)** and a heavy day (month-end DOs) truncates silently.
4. **Deletions invisible (V6).** The 45-day sweep leaves older deletions undetected.
5. **Adopt by number mis-adopts** a DO the Master sheet created with a typo'd number; the verify
   pull's Changes tab shows "adopted" per document so the operator catches it before the push.
6. **Two writers on one row** (ingest and tracking upload) racing on the same DO. Column ownership
   makes the writes disjoint; the risk is a future edit that forgets the rule, so S2 pins it with a
   test per column list.
7. **SPO flag forgotten in AutoCount.** The GRN does not classify; it follows its source line, so
   it inherits whatever the PO feed decided. A mis-flagged SPO stays wrong on both until fixed in
   AutoCount; that is today's behaviour, unchanged.
8. **Backfill volume.** Years of DOs at one call per day is thousands of calls; paced by V10.
9. **Shared-service assumptions in this report are unverified** (section 2.4); the shared-service
   session must read this and answer before S1.

## 6. Not built, and the trigger for each

- **A CRM branch table.** Trigger: a screen that lists or edits branches, or a second consumer of
  the branch master.
- **Recomputing SO line `qty_delivered` from DOs.** Trigger: the SO push's `qty_delivered`
  measured wrong against the DOs on a real day.
- **Promoting fields from `source_payload` to columns.** Trigger: a screen or report needs one.
- **A CRM-side "push verified" flag.** Trigger: the owner wants the CRM, not the shared service,
  to hold the switch.

## 7. Glossary

- **DocKey / DtlKey**: AutoCount's internal numeric keys of a document header / line; stable
  across edits, unlike DocNo.
- **FromDocType / FromDocNo / FromDocDtlKey**: AutoCount's record of which document line a line was
  transferred from (DO from SO, GRN from PO).
- **Cursor**: the last day the shared service has fully swept by LastModified, per book and type.
- **Overlap window**: re-reading the day before the cursor so an edit at the day boundary is never
  missed; harmless because the push is idempotent.

## 8. Open questions for the owner (recommendation in bold)

1. How to "store pretty much everything" on the DO and GRN? (a) typed columns for what the CRM
   uses + the full record as sent in one JSON column; (b) a typed column for every API field.
   **(a): nothing is lost, and no migration each time the vendor adds a field.**
2. Branch name: (a) the shared service looks it up from the branch table and the DO stores code +
   name as delivered; (b) the CRM keeps its own branch table. **(a); a CRM branch table waits for
   a screen that needs it.**
3. Where the DO lands: (a) the existing delivery order (`orders`, the row the tracking upload
   writes); (b) a new AutoCount DO table. **(a): one delivery record, tracking and AutoCount on
   the same row.**
4. Where the GRN lands: (a) the existing GRN (`picking_headers`); (b) a new table. **(a).**
5. Who holds the push switch: (a) the shared service, per entity and company, as products and
   stock today; (b) a CRM flag. **(a).**
6. Backfill start date for DO and GRN: (a) 1 Jan 2023, same as invoices; (b) go-live only.
   **(a): an invoice line points at a DO line, so the DO history should reach as far back.**
7. Retire the DO detail import and the GRN lines import: **(a) yes, once the push has run a week
   with the verification pull showing no differences**; (b) keep both.
8. A tracking upload for a DO that AutoCount has not sent yet: (a) the Master sheet creates the
   row as today and the push adopts it by DO number; (b) refuse the row until the DO arrives.
   **(a): the tracking team is never blocked by sync timing.**
9. Deleted documents while the vendor has no delete log: (a) nightly sweep of the last 45 days by
   doc date; (b) also a monthly sweep of older months; (c) accept the gap. **(a), and (b) only if
   a deletion older than 45 days is ever found.**
10. A DO line whose SO line has not arrived yet: (a) land it unlinked, and the SO's own push links it when it arrives;
    (b) hold the whole DO. **(a).**
11. SO delivered quantity: (a) keep taking it from the SO push; (b) recompute it from DOs.
    **(a); (b) only if the two are ever measured apart.**
12. JustNow cadence: **every 10 minutes**; say if you want faster.
