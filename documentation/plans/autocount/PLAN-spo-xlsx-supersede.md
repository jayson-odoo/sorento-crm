# PLAN: SPO first-push supersede (xlsx-era rows vs the AutoCount line-set)

Status: IN PROGRESS 2026-09-07. Production incident: every xlsx-loaded shipping order duplicated
on the first ESB push (3,294 documents since 05:15Z). ESB Shipping order task PAUSED until this
ships and the dedupe has run.
UAC: `spo-xlsx-supersede-acceptance-criteria.md` (same folder). Parent lane:
`_archive/autocount/PLAN-ingest-parity-standardisation.md` (D11, AC-P3-5).

## 0. Why

AC-P3-5 promised "no duplicate open allocation for one real SPO line after any sequence of upload
/ push / upload". The sequence it did not cover: xlsx upload, CRM GRN receives the goods (rows
close), then the FIRST ESB push of that SPO. Observed on production, SPO-2026/09-0028: 16 xlsx
rows (aggregated per product + location, closed, received) + 28 appended AutoCount lines (open,
TransferedQty 0). Reorder planning counts the 28 as incoming supply for goods already in the
warehouse.

Two mechanisms, both ours (`shipping_order_ingest_service`):

1. `_split_rows` puts a ref-less row that is already CLOSED into `already_closed`, never into the
   adoption pool (S4 review rule: a new DtlKey must not resurrect retired demand). Every xlsx row
   of a received SPO is closed, so the pool is empty and every line is appended.
2. An xlsx row is an AGGREGATE of N AutoCount lines for one (product, location) and carries the
   received quantity; the adoption passes pair one row with one line and the received guard
   refuses a pairing whose incoming quantities sit below what the row received. Even an open
   aggregate cannot be adopted by N lines.

Truth for planning is the CRM receipt (the xlsx path closes on a Sorento GRN; AutoCount's
TransferedQty lags until the transfer is keyed there). The received guard already encodes
"received never shrinks under a push".

## 1. Decisions

| id | decision |
| --- | --- |
| D25 | **First-push supersede.** When an ESB `shipping_orders` push arrives for an `spo_number` whose existing rows in this company are ALL ref-less (no row carries `source_ref`), the whole ref-less set, open AND closed, is the xlsx-era representation of this document and is SUPERSEDED by the AutoCount line-set. S4's exclusion of closed ref-less rows from adoption applies only when the `spo_number` already has at least one ref row (ESB-era: a closed ref-less row there was retired by absence or deletion and must stay retired). |
| D26 | **Receipt carry per group.** Group ref-less rows and incoming lines by `(product_id, upper(location_code))`. `group_received = sum(quantity_received)` of the ref-less rows in the group; `group_shipment` = the first non-null `inbound_shipment_id` among them. Distribute `group_received` across the incoming lines in `line_number` (AutoCount Seq) order, each line up to its `allocated_quantity`, any remainder onto the LAST line of the group. Each line's `quantity_received = max(carried, incoming qty_received)`; `line_status` = closed when `quantity_received >= allocated_quantity` else open; `receipt_status` = `fully_received` / `pending` on the same test. `inbound_shipment_id` = the line's own container link when it resolves, else `group_shipment`. `spo_line_number` continues from `_max_line_number` as today. |
| D27 | **Links move, rows go.** Rows in `picking_lines`, `scm.order_link_claim`, `projects.order_inquiry_links` whose `spo_allocation_id` names a superseded ref-less row are repointed to the FIRST incoming line of that row's group (Seq order). The superseded ref-less rows are then DELETED. This is an explicit supersede act, distinct from the re-push leftover rule, which still only closes. A ref-less group with NO incoming counterpart (AutoCount lists no line for that product + location) is NOT superseded: it is kept and closed by the existing leftover rule, links untouched. Counted on the verdict as `lines.superseded` (rows removed) so the ESB sees it happened. |
| D28 | **Recompute respects ownership.** `PickingHeaderService.sync_grn_received_to_spo` and `sync_received_for_spo_number` write `quantity_received` only for allocations that have at least one `picking_line`; an allocation with none keeps its stored value (ESB-stated or carried). Named out of scope: a GRN deletion lowering the receipt on an ESB-era line (today it cannot lower below the ESB-stated value either). |
| D25a | **Per group, xlsx rows only** (security review B2 + S3, 2026-09-07). A supersede candidate is a ref-less row with `source_system = 'scm_upload'`; a ref-less row written by the CRM UI or the n8n packing-list route (`source_system` NULL) keeps the adoption path and is never deleted. Eligibility is decided per `(product_id, upper(location_code))` GROUP, not per document: a group with no ref row yet is xlsx-era and is superseded on whichever push first names it; a group that already holds a ref row is ESB-era and S4's closed-row exclusion applies there. |
| D26a | **Guard on the group total; merged shipments surfaced** (S2, S6). If the incoming lines' `sum(allocated_quantity)` for a group is below the group's carried receipt, the group is NOT superseded: rows stay (closed by the leftover rule), the incoming lines are created as usual and the record warns `received_locked`. If the group's xlsx rows carry more than one distinct `inbound_shipment_id`, the supersede proceeds with the first one and the record warns `shipment_merged`; the dropped shipment ids are logged. |
| D28a | **Group-aware recompute for AutoCount-owned lines** (S1). For allocations with `source_system = 'autocount'`, `sync_grn_received_to_spo` / `sync_received_for_spo_number` sum the picking lines of the whole `(spo_number, product, location)` group and distribute that total across the group's lines in `spo_line_number` order with the D26 carry rule (each up to allocated, remainder last), never writing one line's picking total onto that line alone. Rows with `source_system` NULL or `scm_upload` keep today's per-allocation recompute. |
| D30 | **Supersede needs `.delete`** (B1). Removing rows through the ingest is a deletion act: the supersede deletes only when the calling principal holds `DELETE_PERMISSIONS["shipping_orders"]` (`scm.shipping_orders.delete`, the same slug the deletions endpoint demands). Without it the superseded rows are CLOSED, receipts and links still carried, `allocation_notes` set to `superseded by <DocKey>`, and the record warns `superseded_closed_only`. Every supersede logs at INFO the removed or closed row ids with their `(allocated_quantity, quantity_received)` (S7). |
| D27a | **Shipment statuses refreshed** (reviewer S2). Every supersede, ingest or dedupe, calls `InboundShipmentService.refresh_shipment_line_statuses` once per distinct `inbound_shipment_id` it touched (superseded rows' and new lines'), like every other writer of allocations. |
| D29 | **Dedupe = the same rule, run once.** `scripts/dedupe_spo_xlsx_superseded.py --company <code> [--since <ts>] --dry-run|--apply`: for every `spo_number` holding BOTH ref-less rows AND ref rows, treat the existing ref rows (in `spo_line_number` order) as the incoming line-set and apply D26 + D27 to the ref-less rows. Per company under `company_scope`, keyset-paged, one commit per document, prints one line per document (spo_number, ref-less rows removed, lines touched, links moved, groups kept). Idempotent: a second `--apply` is a no-op. Shares the algorithm with the ingest through one function in `shipping_order_rules` / the service, never a second copy. Amended (S5, S8, nit 1): the "incoming" side is the ref rows of the NEWEST `source_doc_ref` only (a retired DocKey's rows are never a repoint target); the script calls `register_company_scope_listeners()` before opening `company_scope`; `--since` is parsed as a naive DB-local timestamp. |

## 2. Design

### 2.1 Where

`app/services/shipping_order_ingest_service.py`:

- `_split_rows(rows)` gains the D25 test: `if not any(r.source_ref for r in rows)` then every
  ref-less row (open and closed) goes into a new `supersede_pool`; `pool` and `already_closed`
  stay empty for that document. Otherwise unchanged.
- `_apply_scoped`: after by-ref matching and before `_adopt_lines`, if `supersede_pool` is
  non-empty call `_supersede_xlsx_rows(unmatched, supersede_pool, counts, ...)`, which creates
  the incoming lines as new rows (D26), moves links and deletes the superseded rows (D27), and
  leaves in `pool` only the ref-less rows whose group had no incoming counterpart so the
  existing leftover sweep closes them. `counts["superseded"]` feeds `lines.superseded`.
- `_supersede_xlsx_rows` is the ONE algorithm; the dedupe script calls the same function with
  the existing ref rows expressed as the "incoming" side (a small adapter that turns rows into
  the `values` dicts `_line_values` would have produced, `line_number = spo_line_number`).

`app/services/procurement_service.py`: D28 in the two recompute methods (skip allocations with
zero picking lines).

`app/api/v1/external/contract.py`: `lines.superseded` added to the verdict vocabulary note.

### 2.2 Verdict shape

`lines: {created, updated, adopted, cancelled, superseded}` on the record; `superseded` = number
of ref-less rows removed. Absent when zero, like `dropped`.

### 2.3 Not touched

Adoption passes 1 to 3 for the ESB-era pool are unchanged. The xlsx importer is unchanged (an
upload after the first ESB push adopts ESB rows by (product, location) as before, AC-P3-5). The
deletion endpoint is unchanged.

## 3. Slices

One slice, one PR. Tester writes the red tests from the UAC first; coder (Opus: the state carries
across adoption, receipts and three foreign keys) makes them green; reviewer + security-reviewer
once; then the dedupe runs on production by the captain with `--dry-run` first.

## 4. Risks

- A superseded row that a picking line pointed at loses nothing: the link moves to the first line
  of its group, and the receipt total is carried. A later `sync_grn_received_to_spo` recomputes
  that first line from its picking lines and, under D28, leaves the other lines alone.
- A group whose xlsx quantity differs from the AutoCount sum (the upload was stale) carries what
  was received, not what the xlsx said was allocated; allocated comes from AutoCount from now on.
- Production dedupe touches ~3,294 documents; `--dry-run` output is reviewed before `--apply`.
- `repoint_allocation_dependants` matches dependants with `company_id` equal to the anchor OR NULL
  (S4: `scm.order_link_claim` and `projects.order_inquiry_links` are nullable on company); the
  captain runs the S4 pre-flight count on production before the dedupe.
- A retired DocKey's rows and an ESB-era group are never supersede targets (D25a, D29 amended).

## 5. Test debt and as-built notes

- AC-X4 revises `tests/test_ingest_review_fixes.py::test_a_closed_ref_less_spo_row_is_not_adopted_by_a_new_dtlkey`:
  its seed is a pure xlsx-era SPO, so under D25 the closed row is superseded, not preserved. The
  S4 property (a retired row is not resurrected) is re-asserted with a ref row present.
- Two more pre-existing tests encoded in-place adoption of a pure xlsx-era SPO and were revised
  under D25 (captain, 2026-09-07): `tests/test_ingest_shipping_orders.py::TestShippingOrderAdoption::
  test_xlsx_era_rows_are_matched_by_product_and_location_and_adopted` (AC-V3-4; id survival moved to
  the ref-row case) and `tests/test_ingest_parity_security_fixes.py::TestSec1AdoptionPathReceivedGuard`
  (SEC-1; the receipt-never-erased property now pinned in two shapes: first push carries the receipt
  onto the AutoCount line, ESB-era push keeps the untouched-row + `received_locked` behaviour).
- As built: D25 is detected with a query on `(company_id, spo_number, source_ref IS NOT NULL)`
  (`_has_ref_row`), not on `_existing_rows`, which deliberately excludes other DocKeys' rows.
  `_adopt_lines` is skipped on a first push: the pool then holds only kept ref-less rows and pass 3
  (position only) could otherwise claim one for an unrelated product. D28 needed a release list:
  GRN unlink / re-point / delete pass the allocations they detached so their receipt drops to what
  the remaining picking lines prove; every other picking-less allocation keeps its stored value.
- Shared algorithm: `shipping_order_rules.plan_xlsx_supersede(incoming, refless_rows) ->
  SupersedePlan` (pure), `carried_received`, `repoint_allocation_dependants`; the ingest creates
  rows from the plan, `scripts/dedupe_spo_xlsx_superseded.py` updates existing ref rows from it.

## 6. Reviewer round cleanups (2026-09-07, not decisions)

- `sync_grn_received_to_spo`'s D28 skip is unreachable (its ids come from the header's own picking
  lines): remove it; D28a's group-aware distribution is what applies there.
- `if superseded:` after a non-empty plan is always true: drop the guard.
- Dedupe report: "groups kept" must count groups; dry run ends with `db.rollback()`; the `--since`
  test runs before the per-document row load.
- A first push with `force_closed` (cancelled document) still supersedes: intended, closed rows.
