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
| D29 | **Dedupe = the same rule, run once.** `scripts/dedupe_spo_xlsx_superseded.py --company <code> [--since <ts>] --dry-run|--apply`: for every `spo_number` holding BOTH ref-less rows AND ref rows, treat the existing ref rows (in `spo_line_number` order) as the incoming line-set and apply D26 + D27 to the ref-less rows. Per company under `company_scope`, keyset-paged, one commit per document, prints one line per document (spo_number, ref-less rows removed, lines touched, links moved, groups kept). Idempotent: a second `--apply` is a no-op. Shares the algorithm with the ingest through one function in `shipping_order_rules` / the service, never a second copy. |

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

## 5. Test debt

- AC-X4 revises `tests/test_ingest_review_fixes.py::test_a_closed_ref_less_spo_row_is_not_adopted_by_a_new_dtlkey`:
  its seed is a pure xlsx-era SPO, so under D25 the closed row is superseded, not preserved. The
  S4 property (a retired row is not resurrected) is re-asserted with a ref row present.
