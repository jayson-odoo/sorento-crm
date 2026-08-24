# PLAN - GRN line raw SPO text and forward matching

Status: Phase 1 done (frontend, mocked); Phase 2 (backend) code + tests landed, mock removed;
Phase 3 review findings applied (unsplit short-receipt discrepancy preserved; rejected GRNs
release pool capacity). Browser re-verification at 375px/1280px deliberately NOT performed
(E2E login is on the Mocha company, the stated-but-unmatched corpus is Sorento's, and a company
switch writes a user-level row pending a captain decision) - recorded as a known gap in the PR;
in its place: live API returning `spo_number_raw`, the migration backfill, and the
`SpoAllocationCell` vitest cases.
UAC: `documentation/plans/purchasing/grn-spo-forward-matching-acceptance-criteria.md`
Classification: **CORE**, `public` schema. This extends the procurement base (GRN lines and
SPO allocations are core entities every install has); no new module key, no route guard change.

## The problem, stated precisely

The GRN lines import already reads the line-level "Our PO No." and falls back to the header's
"Transfer from" (`_resolve_line_spo`, `app/tasks/import_tasks.py:1593`). It resolves that to a
single SPO (`_single_spo_or_none`) and matches it to `spo_allocations` with `_spo_match_key`.

Two things are missing:

1. **The resolved text is thrown away when it does not match.** `PickingLine`
   (`app/models/procurement.py:428`) carries only `spo_allocation_id`. A line whose SPO has no
   allocation yet is written with `spo_allocation_id = None` and nothing else, so the sheet's
   claim is gone the moment the import ends.
2. **Nothing revisits an unlinked line.** No code path re-runs matching when an allocation
   appears later. Confirmed by reading every `SPOAllocation(...)` construction site and by the
   fact that the only repair is a hand-run script
   (`scripts/backfill_grn_spo_allocation_links.py`), which can only work from the GRN
   **header's** SPO number and only for GRNs whose header names one.

So the two files' arrival order decides whether the link is ever made. That is the bug.

## Design, derived backwards from the journey

The journey asks for exactly two things: the system must **remember what the sheet said**, and
it must **act on that memory when the other half arrives**. Everything below is one of those
two, plus the discipline that both directions run the same matcher.

### 1. `picking_lines.spo_number_raw`

One nullable column, `VARCHAR(255)` (same width as `picking_headers.spo_number`), holding the
single SPO the import resolved for that line - the line's own "Our PO No." when populated,
otherwise the header's single-SPO fallback. Faithful to the sheet: no case folding, no
separator rewriting. `_spo_match_key` does the tolerating at match time; the stored value is
evidence, and evidence is not normalised.

**Multi-SPO cells store NULL** (AC-FM-8). `_single_spo_or_none` already returns None for them,
and it stays the only source. Storing `"SPO-A, SPO-B"` would put a claim on screen that the
scalar matcher can never honour, and it would leak the display-only header semantics into a
matching column. AC-FM-25 pins that the header stays display-only.

**Index.** A partial functional index over the match key of unlinked lines, which is exactly
the forward-matching query:

```sql
CREATE INDEX ix_picking_lines_spo_number_raw_key
  ON picking_lines (upper(regexp_replace(spo_number_raw, '[^A-Za-z0-9]', '', 'g')))
  WHERE spo_allocation_id IS NULL;
```

Both `upper` and `regexp_replace` are IMMUTABLE, so the expression is indexable - verified
against the live local Postgres (index created inside a rolled-back transaction, and the SQL
expression agreed with `_spo_match_key` on every separator variant in
`tests/test_lessons_learnt_regressions.py`). The Python
`_spo_match_key` and this SQL expression MUST strip the same set - `[^A-Za-z0-9]` then
uppercase - and a test asserts they agree (the container-number normalizers already carry this
same Python/SQL twin obligation, and the same failure mode: a candidate found in SQL that the
Python comparison then rejects).

### 2. One matcher, two directions

New module `app/services/grn_spo_matching.py`. It owns the pool and the draw, and every writer
that places a GRN line against an allocation calls it: the import going forwards, the
forward-matching backfill going backwards, and `_create_grn_lines_with_spo_fifo` (the UI /
external-API approval path). The import's inline two-pass loop (`import_tasks.py:2400-2465`)
and `_create_grn_lines_with_spo_fifo`'s own copy (`procurement_service.py:2500-2560`) are both
deleted and replaced by these calls - AC-FM-26 fails if a second copy survives, and `grep` for
the two-pass rule must return exactly one hit (`grn_spo_matching.draw_fifo`).

```python
@dataclass
class PoolEntry:
    allocation_id: str
    warehouse_id: Optional[str]
    available: int          # mutated in place as it is drawn

@dataclass(frozen=True)
class Draw:
    allocation_id: Optional[str]   # None = the remainder no allocation covers
    quantity: int

def build_allocation_pool(
    db, *, product_id, spo_number, exclude_header_ids=(), company_id=None
) -> list[PoolEntry]
def draw_fifo(pool, *, warehouse_id, quantity) -> list[Draw]
def forward_match_grn_lines_for_spo(db, spo_number, *, company_id=None) -> ForwardMatchResult
```

`company_id` confines both to one company. The session scope normally does that, but the
`X-API-Key` principal resolves to a NULL scope ("all companies") and then adds no predicate at
all, so passing it is how the caller states which company's capacity it is asking about
(AC-FM-27).

`draw_fifo` is the existing two-pass rule, extracted verbatim in behaviour: allocations whose
warehouse equals the line's warehouse first, in pool order; then the rest, in pool order; then
a single trailing `Draw(None, remainder)` when quantity is left. It decrements `available` in
place so one pool serves a whole group of lines. Pool order is `created_at ASC` (FIFO),
tie-broken by `id` so it is deterministic.

#### Availability: the one behaviour change, and why it is required

Today the import computes `available = allocated_quantity - quantity_received` from the
**stored** column, and the backfill script uses `compute_received_for_allocation` (approved
GRNs only). Neither is safe for forward matching:

- Stored `quantity_received` is only written on GRN approval
  (`sync_grn_received_to_spo`) or by an explicit re-sync. An imported GRN is typically not
  approved, so a line already linked to an allocation leaves `quantity_received` at 0, and a
  forward match would draw the same capacity a second time. That is exactly the double-link
  AC-FM-17 and AC-FM-18 forbid.
- `compute_received_for_allocation` counts approved headers only, so it has the same hole.

`build_allocation_pool` therefore computes, per allocation, in one grouped query over picking
lines joined to `goods_received` headers, **regardless of approval status**:

```
linked_all      = SUM(quantity_picked) over lines linked to this allocation
linked_excluded = the same sum restricted to headers in exclude_header_ids
linked_other    = linked_all - linked_excluded
external_recv   = max(0, (allocation.quantity_received or 0) - linked_all)
consumed        = linked_other + external_recv
available       = max(0, allocated_quantity - consumed)
```

#### Which column is "the quantity this row drew"

**`quantity_picked`.** Every writer also sets `quantity_expected` to the same value on the rows
it creates by splitting one receipt across allocations, so the import and
`_create_grn_lines_with_spo_fifo` produce the same rows for the same receipt (AC-FM-19 compares
`quantity_expected`). The **readers** - `build_allocation_pool` and
`compute_received_for_allocation` / `get_computed_received_map` - measure `quantity_picked`,
because it is the only column that is right on the rows already in the database:
`_create_grn_lines_with_spo_fifo` used to leave the whole document quantity on a split's first
chunk and write 0 on every later one, so a reader summing `quantity_expected` charged the entire
draw to the first allocation and nothing to the rest. That re-issued capacity that had already
been given up (the pool) and reported a partial receipt as `fully_received` (the stored
`quantity_received`). `quantity_picked` always held the per-chunk draw, so this choice needs no
backfill of the existing corpus.

The cost, stated plainly: a receipt **split** across allocations can no longer carry an
expected-vs-picked discrepancy, because the split is a fact about what arrived. An unsplit line
still can, and `_create_grn_lines_with_spo_fifo` writes the caller's two quantities untouched
when no allocation covered any of the line. Forward matching likewise never RAISES a row's
`quantity_expected` when that value is 0 - such a row was written by the old splitter and its
sibling chunk already states the quantity, so raising it would state the same quantity twice on
one GRN.

`external_recv` is the receipt an integration recorded on the allocation that no picking line
explains; it must still consume capacity. Subtracting `linked_all` before taking it prevents
double-counting the lines that stored `quantity_received` was itself derived from - without
that subtraction, re-importing an **approved** GRN would see an empty pool and unlink its own
lines.

`exclude_header_ids` is what makes a re-import idempotent: a GRN never competes with itself.
Across different GRNs the exclusion does not apply, so a second GRN correctly sees the first
one's draw.

**The two REWRITING writers pass it; forward matching does not.** An earlier draft of this plan
had forward matching exclude the header whose lines it was placing too. That was wrong, and the
implementation correctly did not follow it. The writers differ in what they do to existing
rows: the import and `_create_grn_lines_with_spo_fifo` both DELETE and recreate their GRN's
lines, so those rows must not count as capacity somebody already took; forward matching only
ever ADDS a link to a line that has none, so a linked line on the same header is a genuine
prior draw. Excluding it would hand that capacity out a second time and the second run over an
SPO would keep re-drawing what the first one already placed - breaking AC-FM-18. This is a
difference in how the pool is CALLED, not in what it does, so the shared matcher is still the
single source of the rule (AC-FM-26).

This strictly improves the import too: two draft GRNs against one SPO used to over-draw it
silently. That is an intended consequence, called out here so review does not read it as
scope creep, and pinned by AC-FM-17.

### 3. Forward matching

```python
def forward_match_grn_lines_for_spo(db, spo_number) -> ForwardMatchResult
```

1. `key = _spo_match_key(spo_number)`; return an empty result when falsy.
2. Select candidate lines with the **ORM** (never raw SQL - `PickingLine` and `PickingHeader`
   are `CompanyScopedMixin`, and the scope listener only applies to ORM queries):
   `spo_allocation_id IS NULL`, `spo_number_raw IS NOT NULL`,
   `func.upper(func.regexp_replace(PickingLine.spo_number_raw, '[^A-Za-z0-9]', '', 'g')) == key`,
   joined to a `goods_received` header. Ordered `header.created_at, header.picking_number,
   line.created_at, line.id` so the draw order is deterministic and oldest-GRN-first.
3. Group by `(picking_header_id, product_id)`. For each group in that order, build a pool with
   NO exclusion (see the note above) and skip the group when the pool is empty (nothing is
   touched, so AC-FM-18's second run is free). Flush at the end of each group so the next
   group's pool query sees the links this one just made.
4. Per line, `qty = quantity_picked or quantity_expected` - the DRAWN quantity first, falling
   back to the expected one for a line that has not been picked yet (see the convention note in
   `grn_spo_matching`); `draws = draw_fifo(pool,
   warehouse_id=str(line.source_warehouse_id) if set else None, quantity=qty)`.
 - No linked draw -> leave the line completely untouched (AC-FM-17).
 - Otherwise the **existing row takes `draws[0]`** (set `spo_allocation_id` and
     `quantity_picked` = that draw's quantity). `quantity_expected` is overwritten **only when
     the receipt was actually SPLIT** (`len(draws) > 1`): a split cannot carry an
     expected-vs-picked discrepancy because the split IS the fact, but an unsplit line still
     can, and rewriting it on a single draw would erase a genuine short receipt (100 expected,
     60 received would come out expecting 60, with `quantity_discrepancy` at 0). A row the OLD
     splitter wrote carries 0 in `quantity_expected` because its sibling chunk carries the whole
     document quantity, and it stays 0. `draws[1:]` become
     new `PickingLine` rows on the same header copying `product_id`, `source_warehouse_id`,
     `destination_warehouse_id`, `uom_id`, `picked_condition` and `spo_number_raw`. The
     trailing unlinked remainder is one of those rows, so it still reads as stated (AC-FM-16).
     This reproduces exactly the row shape a fresh import would have written, which is what
     makes AC-FM-19 and AC-FM-20 hold.
5. Commit, then `PickingHeaderService(db).sync_received_for_spo_number(spo_number)` so stored
   `quantity_received`, `receipt_status` and the inbound shipment line statuses agree with the
   new links (the journey's "what every other stakeholder is told automatically").
6. Return counts for the caller's log line.

### 4. Where it fires

Every path that brings an `spo_allocations` row into existence, established by reading every
construction site of `SPOAllocation(...)`:

| path | site | hook |
| --- | --- | --- |
| SPO Excel import | `import_tasks.py` -> `SPOAllocationService.upsert_allocation(..., forward_match=False)` | ONCE per distinct `(spo_number, company_id)` at the END of `process_spo_import` |
| SPO allocation UI / API create | `SPOAllocationService.create_allocation` (`procurement_service.py`) | end of `create_allocation` |
| external bulk n8n / AutoCount | `POST /api/v1/external/spo-allocations` (`add_all` + commit) | after the commit, once per distinct `(spo_number, company_id)` |
| SCM allocation suggestion | `scm/allocation_suggestion_service.approve` -> `create_allocation(..., forward_match=False)` per split | ONCE per distinct `(spo_number, company_id)` at the END of `approve` |
| `scripts/scm_sim/world.py` | simulator only | no hook |

**Once per file, never per allocation row.** The SPO Excel import upserts one allocation per
`(product, warehouse)` group, so a hook fired inside `upsert_allocation` runs while the rest of
the file does not exist yet: a waiting GRN line is placed against whichever allocation happened
to be written first rather than the one covering its warehouse, and the resulting rows differ
from the ones the same two files produce in the other order. That is AC-FM-19 failing, so the
import passes `forward_match=False` and sweeps once at the end - the shape
`POST /api/v1/external/spo-allocations` already had.

**The SCM allocation suggestion is the same shape, not a single-allocation one.** Approving a
suggestion writes one allocation PER SPLIT - several warehouses under one SPO number, in one
action - so it suppresses the per-row hook and sweeps once after its loops, exactly as the SPO
Excel import does. `create_allocation`'s own hook stays for the paths that really do write ONE
allocation (the UI / API create), and `upsert_allocation`'s `"updated"` branch keeps it for the
same reason - a re-import raising
`allocated_quantity` frees capacity waiting lines should get (AC-FM-23), and that sweep is now
the file-level one. The `"unchanged"` branch writes nothing and so triggers nothing.

**Every hook passes the allocation's `company_id`.** The `X-API-Key` principal resolves to a
NULL scope ("all companies"), where the scope layer adds no predicate at all - so without it the
candidate query offers company B's lines to company A's allocations, and the picking lines a
split creates are stamped with the INCUMBENT company rather than their own GRN's (they now pass
`company_id=line.company_id` explicitly). AC-FM-27.

`update_allocation` (a manual UI edit) is **deliberately not hooked**. Forward matching is a
consequence of an allocation arriving or an import correcting it, not of hand-editing; adding
it there widens the blast radius of an interactive save for no journey step. Recorded here so
the omission is a decision rather than an oversight.

Every call is **post-commit and best-effort** - `try/except Exception` with
`logger.warning(..., exc_info=True)`, never re-raised (`PRINCIPLES.md`: a side effect after the
main row commits must not turn a successful write into a 500, because the retry takes the
idempotent path and never backfills the missed effect). AC-FM-21 pins it.

### 4b. The other GRN-line writers, which would otherwise erase the column

The import is not the only thing that writes picking lines, and the others are destructive.
`PickingHeaderService.update_grn` (`procurement_service.py:2114`) **deletes every picking line
and recreates them** on two branches - when the caller supplies a `picking_lines` payload, and
when a GRN becomes approved and its lines are rebuilt to FIFO-link. Left alone, a single GRN
edit would wipe `spo_number_raw` off an imported GRN and un-forward-matchable it. That is a
silent regression, so it is in scope (AC-FM-9b, AC-FM-9c):

- `_create_grn_lines_with_spo_fifo(grn_id, spo_number, payload)` writes
  `spo_number_raw = _single_spo_or_none(spo_number)` on every line it creates, unless the
  payload row carries its own value.
- `_create_grn_lines_with_spo_fifo` also draws through the shared matcher rather than its own
  copy of the rule - see "The third writer" below.
- `create_grn` applies the SAME rule (`_stated_spo_for_line`) to the lines it builds from its
  payload. Without it a UI- or external-API-created DRAFT GRN states nothing and is not
  forward-matchable until somebody approves it - which is the wrong way round, since the GRN
  arriving before its SPO is the case this feature exists for (AC-FM-9c).
- The `update_grn` **rebuild** branch (no payload, GRN just approved) already reconstructs a
  payload from the existing rows - add `spo_number_raw` to the dict it copies, so it survives
  the delete.
- The `update_grn` **payload** branch keeps whatever the client sent, falling back to the
  header's single-SPO value. `spo_number_raw` is on `PickingLineBase`, so `PickingLineCreate`
  accepts it and the FE `GRNForm` round-trips it exactly as it already round-trips
  `spo_allocation_id` (`GRNForm.tsx:138` and `:216`).

`_unlink_grn_from_spo` (de-approving a GRN) clears `spo_allocation_id` but leaves
`spo_number_raw`, so those lines correctly fall back to reading as stated-but-unmatched. They
then become forward-match candidates again, which is the consistent answer: a fresh import of
that same GRN would link them too, and order independence is the whole point. Only a
`rejected` GRN is excluded from forward matching (AC-FM-17b) - a rejected receipt must not
consume allocation capacity. `draft` is included, because that is the normal state of an
imported GRN and the state the import itself links in.

### 4c. The third writer, and the behaviour change it carries

`_create_grn_lines_with_spo_fifo` was a THIRD hand-rolled copy of the two-pass
warehouse-then-age rule, and it sized availability with `compute_received_for_allocation` -
**approved GRNs only**. The shared pool deliberately counts every non-rejected header, drafts
included, because that is what makes forward matching safe (section 2 above). So this branch
made the two furthest apart, and the divergence is a consequence of this branch rather than
something it inherited.

What that cost, in the office rather than in the code: allocation A of 100 under SPO S, a
draft imported GRN already linked for 60, and then a UI GRN for 100 approved through the
screen. This splitter saw `compute_received = 0` (the draft is not approved), offered the full
100 and linked it. 160 units drew on a 100-unit allocation, with nothing on either GRN saying
so.

The method now calls `build_allocation_pool` and `draw_fifo`, exactly as the import does:

- **`exclude_header_ids={grn_id}`.** This path DELETES and recreates its own GRN's lines, so it
  must not see the rows it is about to replace as capacity somebody else took - the same reason
  the import excludes itself. Without it, re-approving an already-linked GRN would find an empty
  pool and unlink its own lines.
- **`company_id` = the GRN header's own company**, stated rather than assumed, because the
  `X-API-Key` principal runs under a NULL scope ("all companies") where the scope layer adds no
  predicate at all (AC-FM-27's reasoning, applied here).
- **One pool per product**, shared by every payload line for that product. The old code rebuilt
  its pool per line and got away with it only because `compute_received_for_allocation` counted
  the rows it had just flushed (the GRN is approved on this branch); with the GRN excluded from
  its own consumption, a per-line rebuild would hand the same capacity out twice.

**Behaviour change, called out so review does not read it as a refactor:** approving a GRN can
no longer over-draw an allocation that a DRAFT GRN has already consumed. In the example above
the approval now draws the remaining 40 and leaves 60 unlinked (stated-but-unmatched), instead
of drawing 100. It is the same strictly-safer arithmetic the import already gained, now applied
to the screen path, and it is pinned by AC-FM-17c.

What is deliberately NOT changed: this path still links **only when the GRN is approved**
(`update_grn` decides that, and it is a separate decision from how capacity is measured), and
a line no allocation covers at all is still written with the caller's own
`quantity_expected` / `quantity_picked` untouched, discrepancy and all.

### 5. Migration

`alembic/versions/324_grn_line_spo_number_raw.py`, `revision = "324_grn_line_spo_number_raw"`,
`down_revision = "322_merge_dealer_kit_customers"` (the committed head; confirm with
`alembic heads` before writing, and re-chain if main moved). The parallel container-status lane
(`323_cs_company_backfill`) chains onto that same `322` head, so once both branches land the DAG
has two heads and is resolved with an `alembic merge`, per `PRINCIPLES.md`.

1. `add_column("picking_lines", Column("spo_number_raw", String(255), nullable=True))`
2. The partial functional index above.
3. Backfill existing rows (DoD gate 2), two `UPDATE ... FROM` statements:
 - linked lines take their allocation's `spo_number`;
 - unlinked lines under a `goods_received` header whose `spo_number` is non-blank and
     contains none of `, ; CR LF` or a run of two spaces (the import's `_GRN_SPO_SEPARATORS`
     set, i.e. single-SPO headers only) take that header value.

   Both are guarded `WHERE spo_number_raw IS NULL`. At migration time every row is NULL so this
   is identical to the "set where mismatch" form `PRINCIPLES.md` prefers; the `IS NULL` guard is
   chosen because on any re-run a value written by a later import is more authoritative than a
   value re-derived from the header, and must not be clobbered.

   Note this backfill only makes the **existing** GRN corpus display honestly; it does not
   itself run forward matching. Operators who want the historical links repaired keep using
   `scripts/backfill_grn_spo_allocation_links.py`, which is unchanged.

4. `downgrade`: drop the index, drop the column.

Local caveat: this worktree's shared Postgres is stamped at a revision from another branch
(`353_project_order_inquiry_rename`), so `alembic current` fails here. That does not block the
work - `tests/_pg_fixture.py::blank_session` builds the schema with `Base.metadata.create_all`,
not with alembic. Do not "fix" the local stamp.

### 6. Surfacing

Backend:
- `spo_number_raw` on `PickingLineBase` (so `PickingLineCreate` and `PickingLineResponse` both
  carry it, and `list_picking_lines`, which serialises through `PickingLineResponse`, needs no
  further change).
- `list_picking_lines` search gains `PickingLine.spo_number_raw.ilike(q_str)` in its existing
  `or_`, so an operator can find stated-but-unmatched lines by SPO number. Sort is untouched.
- `upsert_grn_line_for_import` gains a `spo_number_raw` parameter, written on **both** the
  create and the update branch, so a re-import refreshes it (AC-FM-9). It is NOT part of the
  match filter - the row identity stays `(header, product, source_warehouse, spo_allocation_id)`.

Frontend (component-library discipline: the cell is shared, not duplicated):
- New `components/common/SpoAllocationCell.tsx` taking
  `{ allocation?: {id, spo_number} | null; statedSpoNumber?: string | null }` and rendering the
  three states of AC-FM-1..3: link, muted text plus a small "Unmatched" `Badge`, or `-`.
- `GRNDetail.tsx` line table and `PickingLinesList.tsx` both render it. `PickingLinesList`'s
  `accessorFn` falls back to `spo_number_raw` so its own search and sort see the stated value.
- `spo_number_raw?: string | null` added to the `PickingLine` types in
  `grn/types/grn.types.ts` and the picking-lines list item type.
- No explanatory prose in the UI - the "Unmatched" badge is a label, and the only extra
  affordance is a `title` on the cell.

## Phases

### Phase 1 - frontend, mocked (`coder`)

Build `SpoAllocationCell` and wire it into both call sites, driven by mock line objects. The
field is optional, so with today's API the rendering is byte-identical to current behaviour -
Phase 1 cannot break the live screens. Verify in a real browser via Playwright MCP, navigating
by sidebar clicks from `/` (Procurement Management -> GRN -> a GRN with lines; and Procurement
Management -> Picking Lines), at 375px and 1280px. Screenshot all three cell states. Check
`browser_console_messages`. **No backend code, no tests yet.**

Contract documented at the top of `grnService.ts`: `PickingLineResponse` gains
`spo_number_raw: string | null`.

### Phase 2 - backend, test-FIRST (`coder` + `tester`)

Red-green-refactor per unit, in this order:

1. Model column + migration + its backfill (AC-FM-10).
2. `grn_spo_matching.py`: `build_allocation_pool` + `draw_fifo`, with the pool arithmetic
   (AC-FM-14, 15, 16, 17) tested directly before any caller uses them.
3. Import writes `spo_number_raw` (AC-FM-5..9), and its inline two-pass loop is replaced by
   `draw_fifo` (AC-FM-26). The other line writers preserve it (AC-FM-9b, 9c).
3b. `_create_grn_lines_with_spo_fifo`'s own copy of the two-pass loop is replaced by the same
   two calls, closing AC-FM-26 across all three writers and AC-FM-17c with it (section 4c).
4. `forward_match_grn_lines_for_spo` (AC-FM-11..13, 18).
5. The three call-site hooks, best-effort (AC-FM-21, 22, 23).
6. Schema + service + FE swap off mocks (AC-FM-24).
7. Order independence (AC-FM-19) and re-import (AC-FM-20) as the closing end-to-end pins.

### Phase 3 - review

`reviewer` agent, then `/code-review`. Then the DoD gate.

## Tests

Backend, Postgres only, every test seeding its own chain (CI's database is empty - never
`LIMIT 1` off an existing table).

- `tests/test_grn_spo_forward_matching.py` - new. Pool arithmetic, forward matching, FIFO and
  warehouse preference, over-draw refusal, repeat no-op, best-effort failure, the three call
  sites, and the two order-independence / re-import end-to-end cases. AC-FM-19 runs the same
  inputs in both orders in two `blank_session` schemas and compares the resulting multisets.
- `tests/test_grn_line_spo_end_to_end.py` - extend. It already drives the real
  `process_grn_lines_import` over `tests/fixtures/grn_detail_listing_our_po.xlsx` with both
  branches (line SPO wins; header fallback). Add the `spo_number_raw` assertions for AC-FM-5,
  6, 7 there rather than building a second fixture.
- `tests/test_grn_listing_multi_spo.py` - extend for AC-FM-8 and AC-FM-25.
- `update_grn` preservation (AC-FM-9b, 9c): both the payload branch and the
  approve-and-rebuild branch, asserting `spo_number_raw` survives the delete-and-recreate.
- The third writer (section 4c), in `tests/test_grn_spo_forward_matching.py`: a draft GRN
  linked for 60 against a 100 allocation, then a second GRN for 100 approved through
  `update_grn`, drawing only the remaining 40 (AC-FM-17c); the approval path calling the shared
  `build_allocation_pool` / `draw_fifo` at all (AC-FM-26); the approval not competing with the
  GRN it is rewriting; and a split receipt producing the SAME rows through the approval path as
  through the real import, so the swap is provably behaviour-preserving where both writers can
  express the case.
- Migration backfill (AC-FM-10): run the migration's backfill statements against a scratch
  schema seeded with the three shapes (linked line, single-SPO header, multi-SPO header).
- Python/SQL normalizer agreement: `_spo_match_key(x)` equals the SQL expression's result for
  the same input, over the separator variants `test_lessons_learnt_regressions.py` already uses.

Frontend:
- `SpoAllocationCell` vitest for AC-FM-1..3.
- Playwright MCP re-verification against the live stack after Phase 2, at 375px and 1280px.
  No persisted spec - see the UAC's out-of-scope note, and record the deviation in the PR body.

## The one backfill this change does NOT need, and the evidence

Converting the readers from `quantity_expected` to `quantity_picked` (review item S1) changed how
`InboundShipmentService.get_received_quantities_by_product` computes a figure that
`refresh_shipment_line_statuses` **persists** onto `inbound_shipment_lines.quantity_received` and
`line_status`. By `PRINCIPLES.md` DoD gate 2 that normally demands a backfill, because rows written
under the old sum would sit stale until something re-triggered the refresh.

Measured against the live corpus before deciding:

```
picking_lines where quantity_picked <> quantity_expected : 0
  of those, linked to an allocation                      : 0
inbound_shipment_lines total                             : 124
```

The two columns are equal on every existing row, so the old and new sums return the identical
number for the whole corpus and every persisted `quantity_received` is already correct. A backfill
migration would rewrite 124 rows to the values they already hold. Skipped deliberately, with the
measurement recorded here so a reviewer can re-run it rather than take it on trust; the divergence
the conversion fixes is only reachable by receipts written AFTER this change (a genuine short
receipt, or a split chunk).

## Definition of Done

1. Mock swapped to real - the FE reads `spo_number_raw` from the API, verified on a GRN whose
   line states an SPO with no allocation.
2. Existing rows backfilled - the migration's two `UPDATE`s.
3. No new permission, so no grant sweep.
4. The new column reaches the FE - it is on `PickingLineBase`, and `PickingLineResponse` is
   built by `model_validate`, not by a manual dict, so nothing silently drops it. Confirmed by
   AC-FM-24 hitting both endpoints.
5. Verified from the user's perspective by sidebar clicks at 375px and 1280px, on a prod build
   for the handoff.
