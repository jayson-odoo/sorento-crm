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
| D26a | **Guard on the group total; merged shipments surfaced** (S2, S6). If the incoming lines' `sum(allocated_quantity)` for a group is below `min(group carried receipt, group xlsx allocated)`, the group is NOT superseded (amended round 3: an over-receipt such as 50 received against 47 ordered must still supersede a line-set that covers the 47 in full, with the excess carried onto the last line per D26 / AC-X32; the guard exists for the AC-X15 shape, where the line-set covers neither what was ordered nor what was received): rows stay (closed by the leftover rule), the incoming lines are created as usual and the record warns `received_locked`. If the group's xlsx rows carry more than one distinct `inbound_shipment_id`, the supersede proceeds with the first one and the record warns `shipment_merged`; the dropped shipment ids are logged. |
| D28a | **Group-aware recompute for AutoCount-owned lines** (S1). For allocations with `source_system = 'autocount'`, `sync_grn_received_to_spo` / `sync_received_for_spo_number` sum the picking lines of the whole `(spo_number, product, location)` group and distribute that total across the group's lines in `spo_line_number` order with the D26 carry rule (each up to allocated, remainder last), never writing one line's picking total onto that line alone. Rows with `source_system` NULL or `scm_upload` keep today's per-allocation recompute. |
| D30 | **Supersede needs `.delete`** (B1). Removing rows through the ingest is a deletion act: the supersede deletes only when the calling principal holds `DELETE_PERMISSIONS["shipping_orders"]` (`scm.shipping_orders.delete`, the same slug the deletions endpoint demands). Without it the superseded rows are CLOSED, receipts and links still carried, `allocation_notes` set to `superseded by <DocKey>`, and the record warns `superseded_closed_only`. Every supersede logs at INFO the removed or closed row ids with their `(allocated_quantity, quantity_received)` (S7). |
| D27a | **Shipment statuses refreshed** (reviewer S2). Every supersede, ingest or dedupe, calls `InboundShipmentService.refresh_shipment_line_statuses` once per distinct `inbound_shipment_id` it touched (superseded rows' and new lines'), like every other writer of allocations. |
| D28b | **Group floor** (delta security review, blocker 1). The group-aware recompute never lowers a group below what its non-released members already hold: `group_total = max(sum(approved picking lines), sum(stored quantity_received of members not being released))`. A released member (its GRN unlinked or deleted) contributes nothing to the floor, so its receipt still drops to what remaining picking lines prove. |
| D25c | **Every non-AutoCount ref-less row is Excel-era; group by warehouse** (production dedupe, 2026-09-08). D25a is revised: the candidate set is a ref-less row whose `source_system` is `scm_upload` OR NULL. Evidence: SPO-2026/09-0028 (the incident example) was skipped by the dedupe because its rows came from the Procurement Upload SPO / n8n packing-list writers, which set `warehouse_id` and `inbound_shipment_id` but neither `source_system` nor `location_code`. Both are Excel aggregates, not "one line for one real line". The D26 group key becomes `(product_id, warehouse_id)` whenever both sides carry a warehouse (measured: every AutoCount row has one, and its warehouse code equals its location code on all 68,537 rows), with `(product_id, upper(location_code))` as the fallback. `storage_zone_id` carries like `inbound_shipment_id`. The security S3 concern (deleting CRM-written rows) is answered by the same evidence: the CRM UI writes no SPO allocations in practice; every NULL-source row on a pushed document is an upload. The S4 rule (no supersede once the SPO has a ref row) and the received guard still apply. **Amended (security round 6):** a ref-less row carrying `po_line_id` is never a candidate, and rows with any `source_system` other than `scm_upload` / NULL are never candidates; the two SCM writers that raise one row per PO line (`spo_conversion_service`, `allocation_suggestion_service`) stamp `crm_spo`. The carry also covers `uom_id`, `quantity_rejected` (group sum, first line) and `allocation_notes` (appended, first line). |
| D25b | **No positional adoption in a supersede push** (delta security review, blocker 2). Adoption passes 1 and 2 (keyed on product + location) still run beside a supersede; pass 3 (position alone, counts agree) is skipped in any push that superseded a group, so a NULL-source CRM / n8n row can never be rewritten as an unrelated product's line. |
| D30a | **Delete is opt-in.** `ShippingOrderIngestService(..., may_delete=False)` is the default; the route passes the resolved `.delete` grant, the dedupe script passes True explicitly. `repoint_allocation_dependants` takes `company_id` as a required keyword and flushes outside the disabled-scope read block. |
| D28c | **Stated receipt is the floor** (reviewer round 3, MB1 / MB2). `quantity_received` alone cannot tell an ESB-stated receipt from a GRN-derived share, so a GRN delete either destroyed AutoCount's TransferedQty on the released line (MB1) or left a redistributed share stranded on a sibling with no GRN behind it, closed, invisible to reorder planning (MB2). New column `spo_allocations.stated_received` (nullable integer, NULL reads 0), written ONLY by the declarers of an AutoCount line's receipt: the ESB push (max rule), the supersede carry and the dedupe carry. The group recompute distributes the approved picking total across the non-released members in Seq order and writes each line `max(stated, share)`; a released member is written `max(stated, its own remaining picking lines)`. This replaces the D28b stored-sum floor (the stored sum was the thing that could not be trusted). The recompute reopens a line it had closed by receipt (`receipt_status fully_received`) when its receipt falls below its allocation; a `cancelled` line or one closed by the leftover sweep is never touched. Migration 488 backfills `stated_received = quantity_received` on `autocount` rows (on production those hold ESB values only: no GRN has ever pointed at an AutoCount line, they all point at the xlsx rows). |
| D28d | **Retirement is explicit** (reviewer kill-test round 5). A line the ESB has stopped naming - by absence in a re-push of the same DocKey, or because the document was deleted and re-created under a NEW DocKey - is closed and otherwise indistinguishable from a live, fully received line, so it rejoined its `(spo_number, product, location)` group: it took a Seq-order share of a sibling's GRN and REOPENED when that GRN was deleted (58 open units against a 29-unit order). New column `spo_allocations.retired_at` (nullable timestamptz, migration 488). TWO setters: the leftover sweep, for the ref rows a re-push no longer names, alongside the D28c freeze; and the DocKey-change path, for the other DocKey's rows once `_guard_spo_number_conflict` has established they are all closed. ONE clearer: `_write_row`, on any row the payload names. The group recompute excludes a retired row from membership, from every share and from every write; a release recorded against a retired line still opens its group's gate, because the live lines were sharing that receipt. The dedupe script marks the DocKeys it passes over, so production ends consistent rather than waiting for a push that may never come. |
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
  SupersedePlan` (pure), `carried_received`, `distribute_received`, `repoint_allocation_dependants`;
  the ingest creates rows from the plan, `scripts/dedupe_spo_xlsx_superseded.py` updates existing
  ref rows from it, and D28a's group recompute reuses `distribute_received` for the same carry.
- As built, round 2 (D25a to D30):
  - `_has_ref_row` is replaced by `_esb_group_keys(payload)` - the `(product, upper(location))`
    keys of this number's ref rows. A group not in that set is xlsx-era (D25a); an EMPTY set is
    also D25's document-level first-push test, which the verdict's `created` reads.
  - `SupersedePlan` gained `kept_groups` / `locked_groups` (D26a) plus `kept_row_ids` and
    `groups_kept` properties, so the operator report can count GROUPS.
  - Rows the plan leaves alone are handed to `already_closed`, not `pool`: that bucket already
    means "reaches the leftover sweep, never an adoption candidate", which is what D25a/D26a want
    for a row the supersede has already ruled on. Adoption now runs in the same push as a
    supersede of a different group (AC-X13 needs it to).
  - D30's `may_delete` is a constructor bool the route computes
    (`ingest._principal_may_delete` -> `UserPermissionService`); it DEFAULTS TO TRUE, because the
    default is for callers with no principal to check at all (a maintenance script, a test) and
    every HTTP caller has its answer computed by the route. AC-X11 and SEC-1a both construct the
    service directly and expect the removal.
  - D27a's refresh runs in the route's own post-commit hook
    (`_run_shipping_order_shipment_refresh_hook`, off `service.shipment_ids_touched`), NOT inside
    `_supersede_xlsx_rows`: `refresh_shipment_line_statuses` COMMITS, and the supersede runs in a
    per-record savepoint, so calling it there would land half a batch and make a dry run write.
    The dedupe calls it per document after its own commit.
  - S4's repoint reads under `company_scope(db, None)` with an explicit
    `company_id = anchor OR IS NULL` predicate: the ambient filter compiles to `IN (anchor)` and
    would drop a NULL-company dependant silently.
- Test debt, round 2:
  `tests/test_ingest_parity_security_fixes.py::TestSec1AdoptionPathReceivedGuard::
  test_sec_1a_first_push_supersede_carries_the_received_quantity_forward` seeds its ref-less row
  with NO `source_system`, which D25a (written after that test) excludes from supersede - so the
  row takes the adoption path, the guard refuses it, and the new line reads 0 rather than the
  carried 5 the test asserts. Its intent ("a ref-less xlsx-era row") needs
  `source_system="scm_upload"` on the seed; verified out of band that the one-line change makes
  every assertion in it pass. Not edited by the coder (tester's file).

- Round 3 as-built (2026-09-07, coder on Opus, commit 52e83bffc): D28b floor lives in
  `procurement_service._sync_group_received` (picking total <= floor leaves the group alone, only
  released members move; the "group has a picking line" gate joins approved `goods_received`
  headers only). D25b is `_adopt_lines(..., allow_positional=)` with the call site passing
  `"superseded" not in counts`. D30a: `may_delete=False` default; the route is the only production
  construction site, the dedupe never constructs the service. `repoint_allocation_dependants`
  requires `company_id`, its flush sits outside the `company_scope(db, None)` block;
  `scripts/backfill_grn_spo_allocation_links.py` registers scope listeners and runs under one
  pinned company (`--company`, default incumbent). `_write_received` writes `line_status` from the
  same `fully_received` test (AC-X33). `_autocount_group_members` filters company, spo_number and
  product in SQL (AC-X34). Captain reverted the coder's zero-count omission from the verdict: the
  shipping-order verdict keeps the fixed key set the sales / purchase order verdict has, so the ESB
  sees no shape change; AC-X29 asserts `adopted` absent-or-0 instead.
- Security round 3 (clean) left two tightenings, applied by the captain: the group redistribution
  writes a RELEASED member from its own remaining picking lines and distributes only the rest of
  the picking sum over the non-released members (so a sibling's proven receipt is never handed to
  a line whose GRN was just deleted); the dedupe flushes before the repoint widens its read under
  the disabled company scope, the same structural rule the ingest already follows.

- Round 4 as-built, D28c (2026-09-07, coder on Opus): `spo_allocations.stated_received`, nullable
  INTEGER, NO server default, migration `488_spo_alloc_stated_received` on
  `487_chatbot_warehouse_cue` (single head; the lane DB took the DDL through the migration's own
  `apply(bind)` because that database converges by `create_all` and `alembic upgrade head` trips
  on an older chatbot revision - the documented drift in `sorento_crm_backend/CLAUDE.md`).
  - FOUR writers, and only these: the ESB push (`_write_row`, each line's own declared
    `qty_received`, read BEFORE the `quantity_received` clamp so a GRN-derived stored figure can
    never be captured as a statement), the first-push supersede carry, the dedupe carry, and
    RETIREMENT (F2: the leftover sweep freezes a REF row's receipt as stated, so a line the GRN
    alone had received and AutoCount stopped naming cannot be revived by a later GRN delete). The
    GRN recompute never writes it.
  - Only a POSITIVE statement is recorded: NULL reads 0 everywhere, so writing a 0 would say
    nothing extra while making an ESB row differ from an xlsx row on a column neither declared
    anything on - which `tests/test_ingest_parity_s3_shipping_orders.py` compares literally.
  - The floor is MONOTONIC by design, exactly like `quantity_received` under `received_guard`: a
    re-push stating a lower TransferedQty never lowers it. The supported correction for an
    AutoCount keying error is the deletion endpoint followed by a re-push; there is no lowering
    path and no UI for one. On the by-ref update path a refused line (`received_locked`) records
    nothing, which is the same answer the max rule would give.
  - `_sync_group_received`: the approved `goods_received` gate stays; a RELEASED member is written
    `max(stated, its own approved picking lines)`; the LIVE non-released members
    (`_is_live_group_member`: not cancelled, and not closed for any reason other than a receipt)
    take `distribute_received(full picking sum of the non-released side, their allocated list in
    Seq order)` and are each written `max(stated, share)`. A non-live member gets no share and no
    write at all (AC-X41), while a receipt drawn against one still flows to the lines that are
    standing. D28b's stored-sum floor is deleted: the stored sum was the untrustworthy figure.
  - `_write_received(alloc, total, *, may_reopen=False)` reopens (open + pending) only when
    `total < allocated` AND the row was `closed` + `fully_received` before the write, and only on
    the group path. The per-allocation path for `scm_upload` / NULL-source rows is unchanged.
  - Closed-only supersede (`may_delete=False`): the NEW AutoCount lines carry `stated_received`
    (they are the live representation); the kept, annotated xlsx row keeps whatever it holds and
    gets none. Its receipt already duplicated the carry before this column existed - the known
    cost of the closed-only path, not a D28c regression.
  - Not exposed on any API surface: `SPOAllocationResponse` exposes `quantity_received` (computed
    on read), but nothing needs the provenance figure, so the column stays server-side.
  - Round 4b (security finding, AC-X42): the live members share the picking total of the LIVE
    members only. A non-live (retired, cancelled) member keeps its own approved draws AND its own
    stored receipt, so counting those draws again for the standing lines made the group report one
    GRN twice (a retired line holding 10 with its own 10-unit GRN also handed 10 to a live
    sibling: 20 reported for one receipt).
- Round 5 as-built, D28d (2026-09-07, coder on Opus): `retired_at` (nullable `TIMESTAMP WITH TIME
  ZONE`) joins `stated_received` in migration 488 - both `ADD COLUMN IF NOT EXISTS`, both dropped
  by `revert`, and the `stated_received` backfill unchanged. `retired_at` is deliberately NOT
  backfilled: no existing row can be known retired retrospectively, and the two setters stamp it
  the next time the document is pushed (or the dedupe walks it).
  - Setters: the leftover sweep (ref rows, `autocount` only, alongside the freeze) and
    `_retire_other_dockey_rows(payload)`, called right after `_guard_spo_number_conflict` because
    that guard is what establishes the old DocKey's rows are all closed. The other DocKey's rows
    are queried explicitly - `_existing_rows` excludes them BY DESIGN, which is exactly why
    nothing had ever marked them. Both setters are idempotent and never overwrite an existing
    `retired_at`. Clearer: `_write_row`, one line, so any row the payload names is live again.
  - `_autocount_group_members` filters `retired_at IS NULL` in SQL and re-checks
    `str(row.product_id) == str(alloc.product_id)` in Python (AC-X47);
    `_is_live_group_member` is false for a retired row (AC-X48); and
    `_sync_received_for_allocations` skips a retired row as a group anchor, so a retired row is
    never written even when a GRN deleted off it puts it in the released set.
  - ADDED beyond the ruling, and required by it: `_sync_group_received` gained
    `group_released`. With retired rows out of membership, a GRN deleted off a RETIRED line no
    longer put anything in the group's `released_ids`, so the D28 ownership gate ("no approved
    line, nobody released") closed and the live sibling kept a share of a GRN that no longer
    existed - AC-X40's own sibling assertion (drops to 0, reopens) went red. The caller now
    computes which group KEYS a release touched, retired members included, from the allocations
    it already holds (`_spo_allocation_group_key`, one definition shared with the visit-once
    set), and passes that as the gate's third way in. Nothing else about the retired row changes:
    it takes no share and is never written.
- Round 6 as-built, D25c (2026-09-08, coder on Opus): `is_xlsx_era_row` takes `source_system` in
  (`scm_upload`, NULL); the dedupe's own page query takes the same pair in SQL
  (`or_(source_system == 'scm_upload', source_system IS NULL)`), which is the line that had made
  the production sweep skip SPO-2026/09-0028. `supersede_group_key(product_id, warehouse_id,
  location_code)` returns `(product, 'wh:<id>')` when the side carries a warehouse and
  `(product, 'loc:<UPPER CODE>')` otherwise, tagged so an id can never be compared against a code,
  and `(product, None)` when the side carries neither (the pre-D25c product-only grouping, which
  several documents still rely on).
  - ADDED beyond the ruling, and required by it: `supersede_match_keys(...)`, the tuple of EVERY
    identity a side answers to. A per-side key alone does not group the two sides when they name
    the destination differently, and that is the common case, not the corner: an AutoCount line
    always resolves both halves, while the Procurement / n8n rows carry a warehouse and no
    location and the SCM upload carries both with a free-text code ("brw"). So the INCOMING lines
    are indexed under both of their identities and each Excel row under its own one, with
    warehouse-keyed row groups considered first and a claimed line never offered twice (otherwise
    two row groups naming one destination differently would both create it). `_esb_group_keys`
    uses the same function, so S4's "no supersede once the group carries a DtlKey" holds whichever
    way the Excel row beside it is keyed. Measured basis for preferring the id: all 68,537
    AutoCount rows on the lane database carry a warehouse whose `warehouse_code` equals
    `upper(location_code)`.
  - `storage_zone_id` carries exactly like `inbound_shipment_id` (group's first non-null, onto a
    line that resolved none), in the ingest and in the dedupe.
  - `_adopt_lines`' own coarse key is deliberately untouched (product + location): adoption is a
    different rule with a different failure mode, and D25b already stops its positional pass in a
    supersede push.
  - Named residual, key asymmetry (reviewer round 6, accepted): the two sides are indexed
    asymmetrically on purpose. Incoming lines go in under every identity they answer to, each
    Excel row under its one preferred identity. So an incoming line whose `location_code`
    resolves to no warehouse row cannot match a warehouse-keyed Excel row: the line offers only
    `loc:` and the row asks only for `wh:`. That combination is unreachable on measured data (all
    68,537 AutoCount rows on the lane database resolve a warehouse whose code equals
    `upper(location_code)`), and symmetrising the row side is the worse trade, because a row
    indexed under both keys can be claimed by two different groups that name one destination
    differently. The consequence of the residual is a skipped supersede (rows stay, the push
    appends, the dedupe or a re-push corrects it), never a wrong merge.
  - Retirement and the receipt freeze are unchanged: both only ever touch `autocount` rows.
- Round 7 as-built, D25c amended plus security round 6 (2026-09-08, coder on Opus): a row carrying
  a `po_line_id` is never a supersede candidate. `is_xlsx_era_row` returns False for it before any
  other test, and the dedupe's page query adds `po_line_id IS NULL` in SQL. Reason measured by the
  security reviewer: of the five writers that produce ref-less rows, two are not aggregates but one
  row per PO line - `app/services/scm/spo_conversion_service.py::_write_allocations` and
  `app/services/scm/allocation_suggestion_service.py` - and the ingest never carries `po_line_id`,
  so superseding one of those rows would sever the PO linkage silently.
  - Second guard, so the first does not have to hold alone: `SPOAllocationCreate` gained
    `source_system`, and both SCM writers stamp `crm_spo` (one constant,
    `shipping_order_rules.CRM_SPO_SOURCE_SYSTEM`, re-exported as `spo_conversion_service.
    SOURCE_SYSTEM`). A stamped row fails `is_xlsx_era_row` on the source test as well as the
    `po_line_id` test.
  - `_receipt_is_computed` therefore accepts `crm_spo` alongside NULL
    (`shipping_order_rules.COMPUTED_RECEIPT_SOURCE_SYSTEMS`): a `crm_spo` row is still a CRM-raised
    allocation whose receipt is computed from approved picking lines, and the four call sites that
    gate on it would otherwise stop showing its approved-GRN receipt on the read path the moment we
    started stamping it.
  - Carry completed: `uom_id` joins `inbound_shipment_id` and `storage_zone_id` (group's first
    non-null onto a line that resolved none), and the group's own statements - `quantity_rejected`
    and `allocation_notes` - land on the group's FIRST line, the row the links move to.
  - Both carries are idempotent, because they can run twice: a close-only supersede (no
    `scm.shipping_orders.delete`, D30) leaves the Excel rows standing, so the dedupe re-selects the
    same document later. `quantity_rejected` is `max(existing, group total)`, never a sum, and
    `append_note` appends only the fragments not already present (splitting the addition on ";").
  - Named residual: an accepted allocation suggestion that produced no PO line stays a supersede
    candidate until it is stamped. Both guards miss it only for rows written before this change;
    superseding one loses nothing but its id and `created_by`, since the receipt, shipment, zone,
    uom, rejection and notes all carry.
- Round 8 as-built, security round 7 (2026-09-08, coder on Opus): the `crm_spo` stamp round 7
  introduced falsified every predicate that spelled "a row this system raised" as
  `source_system IS NULL`. `CRM_RAISED_SOURCE_SYSTEMS` now names that concept in
  `shipping_order_rules`, deliberately a separate name from `COMPUTED_RECEIPT_SOURCE_SYSTEMS`
  (which it aliases today) because one answers "who raised this row" and the other "who states
  its receipt", and a future value could join one without joining the other. Each SQL site keeps
  the two-arm spelling `or_(col.is_(None), col == CRM_SPO_SOURCE_SYSTEM)`, because `IN (NULL,
  'crm_spo')` never matches a NULL row in SQL.
  - `app/api/v1/external/grn.py` (allocation resolution by spo_number + product + warehouse):
    without the second arm every SCM-raised allocation became invisible to an incoming GRN, which
    would have fallen through to the number-plus-capacity path or to no match at all.
  - `app/api/v1/external/spo_allocations.py` (n8n bulk-create duplicate check): without it the
    endpoint stops seeing a `crm_spo` row and creates a SECOND allocation beside it, the same
    duplicate-supply shape this whole lane exists to remove.
  - `app/services/procurement_service.py::upsert_allocation`: `crm_spo` joins the match `or_`
    (NULL, `crm_spo`, `scm_upload`, `autocount`), and the "last writer wins" line right below it
    now clears the stamp only when it is NOT `crm_spo`. That stamp is not a writer's claim on the
    row, it is the marker that the allocation belongs to a purchase-order line, and clearing it
    would hand the row straight back to the supersede sweep, which reads an unstamped ref-less row
    as Excel-era (D25c). A quantity correction does not change what the row IS.
  - The stamp is a SERVICE argument, not a request field (reviewer nit, same round).
    `source_system` came off `SPOAllocationCreate` and `create_allocation` gained a
    keyword-only `source_system: Optional[str] = None` that only the two SCM writers pass.
    As a request field it was settable through `POST /api/v1/procurement/spo-allocations` by
    any authenticated user, and this column decides which rows the first-push supersede
    replaces and whose receipts the group recompute pools: posting `autocount` would have
    joined a hand-made row to a document's group receipt, and posting nothing on a row that
    should carry `crm_spo` would have offered it to the sweep. `create_allocation` now writes
    the column itself, so the screen, the n8n packing-list route and the Excel import get NULL
    by construction rather than by trust.
  - `allocation_suggestion_service` imports `CRM_SPO_SOURCE_SYSTEM` from the rules module
    directly instead of through `spo_conversion_service`'s re-export (reviewer nit): it has no
    other reason to depend on that module, and the stamp is a shipping-order rule.
  - AC-X59 audit, every other `source_system` read on `SPOAllocation` in `app/`, all left alone
    with the reason: `shipping_order_ingest_service.py:625`, `procurement_service.py:4195`, `:4354`
    and `:4359` test `== autocount` (retirement and the group recompute), which `crm_spo` must not
    join; `scm/outstanding_import_service.py:1607` tests
    `in_([scm_upload, autocount])`, the upload channel's own writer set, which already excluded
    NULL and must keep excluding `crm_spo`; `rules/shipping_order_rules.py:414`
    (`is_xlsx_era_row`) excludes `crm_spo` on purpose, that is round 7's guard. The other
    `source_system IS NULL` predicates in `app/` are on different tables (`SalesOrder`,
    `PurchaseOrderLine`, project order inquiries) and no writer stamps `crm_spo` on those. No raw
    SQL reads `spo_allocations.source_system`.
- Scope note on D28 / D28c, documented boundary: the floor only ever over-states, never
  under-states. A carried floor on a NON-RELEASED sibling is not clawed back when the GRN behind
  the original xlsx receipt is later deleted - the carry was a statement about that line at
  supersede time, and nothing in this design lowers a statement (see the monotonic-floor note
  above). The direction of the residual error is therefore over-stating a receipt, never losing
  one; the correction is the same as for a keying error, the deletion endpoint followed by a
  re-push.
- Test debt, round 4:
  `tests/test_spo_xlsx_supersede.py::TestAcX33GroupRecomputeKeepsLineStatusConsistent::
  test_a_line_closed_by_the_leftover_sweep_is_never_reopened` seeds its closed member as `closed`
  + `fully_received` with NO `stated_received` and no picking line, and relies on the D28b
  stored-sum floor its own docstring names to keep it at 29. D28c deletes that floor, and that
  seed is now the exact signature of "closed by a receipt nothing states and no GRN backs", which
  MB2 / AC-X35 require to reopen. Either `stated_received=29` on the seed (then it is AC-X36's
  property: a stated receipt is the floor and the line stays closed) or `receipt_status="pending"`
  (then it is AC-X41's property: closed for a reason other than a receipt, excluded from the
  group entirely) makes it green. Not edited by the coder (tester's file).

## 6. Reviewer round cleanups (2026-09-07, not decisions)

- `sync_grn_received_to_spo`'s D28 skip is unreachable (its ids come from the header's own picking
  lines): remove it; D28a's group-aware distribution is what applies there.
- `if superseded:` after a non-empty plan is always true: drop the guard.
- Dedupe report: "groups kept" must count groups; dry run ends with `db.rollback()`; the `--since`
  test runs before the per-document row load.
- A first push with `force_closed` (cancelled document) still supersedes: intended, closed rows.
- Delta round: `scripts/backfill_grn_spo_allocation_links.py` registers the company-scope listeners
  and pins one company, otherwise its closing recompute now compiles to `false()` under an UNSET
  scope and silently reads nothing; `allocation_notes` is appended to, never overwritten; the
  receipt-ownership comment in procurement_service names all three rules (read path trusts a
  stamped row; write path per-allocation for NULL / scm_upload rows; group-aware with floor for
  autocount rows).
