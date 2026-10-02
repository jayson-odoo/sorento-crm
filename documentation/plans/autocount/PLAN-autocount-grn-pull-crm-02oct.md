# PLAN: GRN pull from AutoCount with PO/SPO line linkage (GRN-PULL-CRM)

Status: **plan + UAC + red tests drafted; behaviour card with the owner (crew-ask on PR
#1427); no implementation until answered.** Track: full L (new permission slug + grant
migration, prod data linkage, cross-repo with shared-service lane GRN-PULL-SS). Branch
`claude/grn-pull-crm-2pnmf9` (the sandbox's designated branch; the brief named
`crew/grn-pull-crm`), base `main` 066b966e. UAC: `autocount-grn-pull-crm-02oct-acceptance-criteria.md`
(AC-GP-01 onward). Rules that wait on an owner answer are marked **(pending Qn)**; each is
written to the recommendation and changes only if the owner rules otherwise.

Scope: Goods Receive Notes pulled on request by DocDate, same path as the DO pull
(shared-service snapshot -> CRM preview/compare -> review -> user confirms). Push stays OFF.
Never writes to AutoCount. Confirm applies through `AutocountDocIngestService` (one writer).

Paths: `be/` = `sorento_crm_backend/`, `fe/` = `sorento_crm_frontend/`.

## 0. Scout (measured on `main` 066b966e)

| Thing | Where | State |
| --- | --- | --- |
| DO pull, end to end | `be/app/services/autocount_pull_service.py:39-67` (entity maps), `be/app/tasks/autocount_pull_tasks.py:691` (`_do_ingest`), `:706` (`_ingest_rows`), `:719` (`_tally_delivery_orders`), `:795` (`_preview_delivery_orders`), `:833` (`_apply_delivery_orders`), `be/app/api/v1/integrations/autocount_pull.py:332-414` (rows / download / compare dispatch), `be/app/services/autocount_pull_compare.py` | Merged (#1383). GRN is a fourth entity on the same machinery. |
| Snapshot book | `autocount_pull_service.py:697` (`snapshot_book`) | Reads the prefix before the first `:` of `source_ref`; not DO-specific, so `{book}:GRN:{DocKey}` works unchanged. |
| GRN ingest | `be/app/services/autocount_doc_ingest_service.py:932` (`_apply_grn`) | Exists. Lands on `picking_headers` / `picking_lines`, status `approved` (`cancelled` when `Cancelled`), adopts an Excel GRN by number, never unsets a link. |
| GRN line exact link | same file `:966-970`, `_po_or_spo_line` `:775` | `FromDocDtlKey > 0`: one `source_ref` match across PO lines + SPO allocations, else `po_line_unresolved`. |
| GRN line, key 0 | `:176` (`_link_key`), `:971-978` | 0 = no key. Only `OurPONo` is read: header-level `purchase_order_id` (PO) or `from_doc_type='SPO'`; **line link stays null; `FromDocNo` is stored but never resolved**. Live GRN lines carry `OurPONo` null (ingest plan 29 Sep, line 55), so today a key-0 line links nothing at all. |
| GRN receipt hook | `be/app/api/v1/external/ingest.py:741` (`_run_grn_receipt_hook`) | Route-level, post-commit: recomputes `touched_allocation_ids`. The DO apply has no hook (`autocount_pull_tasks.py:833` docstring); the GRN apply must run this one. |
| GRN Excel upload linkage | `be/app/tasks/import_tasks.py:2177` (`process_grn_lines_import`), line SPO columns `:1683` ("Our PO No." first, then "From Doc No", "SPO Number", "Transfer From"), header fallback `:2346`, group key `:2369`, draw `:2532-2544` | **SPO only, never PO lines.** Matcher `be/app/services/grn_spo_matching.py`: `build_allocation_pool` `:96` (SPO key normalised, product, company, FIFO by age, capacity = allocated - other GRNs' drawn qty - unexplained receipt) + `draw_fifo` `:224` (same warehouse first, then any, remainder unlinked). One receipt may SPLIT into several picking lines. The Excel's "Our PO No." column is the GRN listing report's rendering of the line's source document, i.e. the API's `FromDocNo` (the API's own `OurPONo` is null). |
| Split vs AutoCount line identity | `be/app/models/procurement.py:840` | `uq_picking_lines_header_dtl_key`: one picking line per AutoCount DtlKey; an AutoCount line cannot be split the way an upload line is. |
| Cancelled GRN and SPO capacity | `grn_spo_matching.py:185,292` | Pool excludes `rejected` only, so a cancelled GRN's linked lines still consume SPO capacity. `compute_received_for_allocation` counts `approved` only (`procurement_service.py:4499`), so the receipt figure is already right. |
| Shared-service GRN snapshot | crew, 2 Oct | Not on ss main (`pull_gateway_service.py:54-59`). Lane GRN-PULL-SS adds it to the contract in 1.2. `From*` line keys seen only in an ss fixture; live presence unverified, so absent keys must behave as blank. |

## 1. Design

### 1.1 Entity `goods_receive_notes`

| Map | Value |
| --- | --- |
| `ENTITY_PERMISSIONS["goods_receive_notes"]` | `procurement.grn.autocount_pull` (new registry slug, "Pull Goods Receive Notes from AutoCount") |
| `JOB_TYPES` | `autocount_grn_pull` |
| `APPLY_JOB_TYPES` | `autocount_grn_apply` |
| Router gate | add `"procurement"` to `require_any_module_enabled(...)` (`be/app/api/v1/__init__.py`; verify the module key) |
| `scope` | accepted for `delivery_orders` and `goods_receive_notes` (`autocount_pull.py:88`) |
| Migration | `grn_pull_0001_perm`: insert the slug if absent, sweep onto roles holding `procurement.grn.import` (integration roles excluded), grant `admin`. The `do_pull_0001_perm` statements with two names changed. |

### 1.2 Snapshot contract (GRN-PULL-SS, as posted on #1427 and accepted by crew 2 Oct)

`POST /api/v1/autocount/snapshots {"companyCode", "entity": "goods_receive_notes", fromDay?, toDay?, docNo?}`.
Rows = the raw vendor GRN dict verbatim (`Details` intact) + `source_ref` `{book}:GRN:{DocKey}`.
Same build / status / rows calls, `ready` header, contentHash, 409 `BUILD_IN_FLIGHT`, 10,000
document cap. The CRM strips `source_ref` before the ingest (`_ingest_rows`, DO review S1).
Line keys `FromDocType` / `FromDocNo` / `FromDocDtlKey` / `OurPONo` may be ABSENT: absent =
null = blank (pinned).

### 1.3 Line linkage (the ingest change; one resolver used by push, pull and the waiting fill)

Source document of a line: `FromDocNo`, else `OurPONo` **(pending Q3)**. Order of rules:

| Rule | Condition | Result |
| --- | --- | --- |
| R1 exact | `FromDocDtlKey > 0` | `_po_or_spo_line` unchanged; none or several: `po_line_unresolved`. |
| R4 type | `FromDocType` present and not `PO` | Unlinked, `from_doc_type_unsupported`. `FullTransferOption` / `FullTransferFromDocList` stay in `source_record` only. |
| R2a SPO | source doc's `_spo_match_key` matches an `spo_allocations.spo_number` in the anchor company | Reuse `build_allocation_pool(product, spo, exclude_header_ids={this GRN}, company)` + `draw_fifo(pool, warehouse=Location, qty)`. One draw from one allocation covering the whole qty: `spo_allocation_id`. Exactly one allocation of that product in the SPO: link to it even past its capacity, warning `spo_over_receipt`. Else unlinked, `spo_line_ambiguous` **(pending Q1)**. `spo_number_raw` = the source doc (so the forward matcher and the Excel upload read the same statement). |
| R2b PO | source doc equals a `purchase_orders.po_number` in the anchor company | PO lines of that PO with the line's product; several: narrowed to `warehouse_id == Location`. One: `po_line_id` (+ `purchase_order_id`). Several: `po_line_ambiguous`. None: `po_line_unresolved` **(pending Q2)**. `purchase_order_lines.qty_received` is never written (the PO feed owns it). |
| R2c neither | source doc in neither table | Unlinked, `purchase_order_unresolved`; the end-of-batch fill retries it. |
| R3 none | no `FromDocNo`, no `OurPONo` | Unlinked, no warning. |

PO is tried before SPO only when the number is an exact `po_number` (SPO and PO share one
AutoCount table, `:775-777`; their numbers do not collide in practice: `PO-...` vs `SPO-...`).
A number matching both is `po_line_ambiguous` (no guess).

Pool consumption within one GRN: lines of the same GRN draw from ONE pool per (SPO, product),
built once per document, so two lines of one GRN cannot both take the same capacity (the
upload's rule, `procurement_service.py:4427-4431`).

Cancelled GRN (R6): pool excludes `cancelled` as well as `rejected` **(pending Q4)**; the
cancelled GRN keeps its links for audit.

Waiting-link fill (`_fill_waiting_links`, `:1109`): the GRN branch adds lines with
`from_doc_no` set, both links null, no `from_dtl_key`, ordered newest first, bounded by
`MAX_WAITING_LINKS`, resolved with the same R2 resolver.

Warnings join `CONTRACT_2_7_WARNINGS` and the pull's human wording map: `spo_line_ambiguous`
"SPO line ambiguous", `spo_over_receipt` "received more than the SPO line has left",
`po_line_ambiguous` "PO line ambiguous", `from_doc_type_unsupported` "source document type
not linked".

### 1.4 Preview / apply

`_preview_goods_receive_notes` / `_apply_goods_receive_notes` = the DO pair with the entity
passed through (`_do_ingest`, `_ingest_rows`, `_tally_*` generalised by entity; the message
says "GRN created / updated / adopted by number"). Counts as DO plus `lines_linked`,
`lines_unlinked`, `lines_ambiguous` (sum of line counters + records with an ambiguous
warning). Apply: after `db.commit()`, `_run_grn_receipt_hook(db, ingest)` (moved to a shared
helper both callers import, no copy). Audit actor as DO (job actor scope).

### 1.5 Rows, download, compare

- **Excel view / download**: one row per GRN line in the GRN lines sheet's shape: `doc_no,
  doc_date, creditor_code, creditor_name, item_code, description, location, qty, uom,
  from_doc_no, link` where `link` is the preview's verdict for the line (`PO line` / `SPO line` /
  `unlinked` / `ambiguous`; read from the stored outcome identity, not recomputed).
- **Compare (pending Q5)**: `source=lines` = the GRN lines sheet, keyed (Doc No, Item Code,
  Location) using the upload's own header aliases (`import_tasks.py:2239-2242`), Qty summed per
  key, plus "stated source" (Excel "Our PO No." / line SPO columns `:1683`) vs `FromDocNo`,
  `_spo_match_key`-normalised; `source=headers` = the GRN listing sheet keyed by Doc No on
  Date and stated SPO ("Transfer From"). Windowed by the pull's DocDate window exactly as DO
  (`pull_window`, `_excel_day`). Only-in either side is a difference, never a delete.

### 1.6 Frontend (reuse, no new UI)

A fourth value in the existing switches: `AutocountPullEntity`, counters, columns, labels,
job page ("AutoCount GRN Pull", Back to Goods Receive Notes), the GRN list's Actions menu
(`fe/app/(protected)/procurement-management/grn/page.tsx`) gets the button + the existing
`PullScopeDialog`. If the GRN list has no Actions menu yet, that is new UI: static mock first.

### 1.7 Not built, and the trigger

- Splitting an AutoCount line across SPO allocations: the owner choosing Q1 (b).
- Writing PO `qty_received` from GRNs: the PO feed stops carrying it.
- Push enable for GRN: the owner, after a clean compare on a real window.

## 2. Build order (tests first)

1. This plan + UAC + red tests (`be/tests/test_autocount_pull_goods_receive_notes.py`,
   `be/tests/test_ingest_autocount_grn_line_link.py`). **Done before the owner's answer.**
2. Owner answers -> adjust the pending rules and their tests.
3. Backend: ingest R2/R4 + pool `cancelled` + waiting fill; maps + slug + migration + gate;
   preview / apply / hook; rows / download / compare.
4. Frontend switches + vitest.
5. Kill tests, reviewer + security-reviewer (permission slug, external data), hand-test script.
6. Compare on a real DocDate window against the users' GRN Excel: 0 unexplained differences.
