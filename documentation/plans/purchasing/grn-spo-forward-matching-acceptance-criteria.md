# UAC - GRN line raw SPO text and forward matching

Status: Phase 1 done (frontend, mocked); Phase 2 (backend) code + tests landed, mock removed;
awaiting the full regression suite and live browser re-verification. Phase 3 (review) not started.
Plan: `documentation/plans/purchasing/PLAN-grn-spo-forward-matching.md`
Classification: CORE, `public` schema (extends the existing procurement base)

## Journey

**Actor.** The procurement office staff member who runs the AutoCount exports into the CRM.
They arrive from Procurement Management, either at the import screen or at a GRN they are
checking.

**What they do not control.** AutoCount emits the SPO allocation file and the GRN detail
listing independently, and the office receives them on whatever schedule the supplier and
the warehouse produce them. A GRN often lands days before the SPO it was received against.
The order of the two uploads is not a decision anybody makes - it is weather.

**What the system already knows.** The GRN detail sheet states, on each line, the SPO the
line was received against ("Our PO No."), and the GRN header states it too ("Transfer
from"). Both are already parsed today. Nothing extra has to be asked for.

**Step 1 - they upload whichever file arrived.** One decision: which file. No SPO number is
ever typed, no line is ever hand-linked.

**Step 2 - they open the GRN.** Every line shows what the system knows. A line the system
could match shows a link to its SPO allocation. A line the system could not match yet shows
**the SPO number the sheet stated, marked as not yet matched** - because a dash reads as "the
sheet said nothing", which is false and sends the user hunting for a problem that is not
there.

**Step 3 - the other file arrives, and they upload it.** Same single decision. Nothing else
is asked of them.

**Step 4 - they open the GRN again.** The lines that were stated-but-unmatched are now links.
They did not go back, did not re-upload the GRN, did not ask an engineer to run a script.

**What they hold at the end.** A GRN whose every line either links to the allocation it drew
from or says, in the sheet's own words, which SPO it claims and that no allocation covers it
yet. **The upload order left no trace** - the same two files in either order produce the same
links.

**What every other stakeholder is told automatically.** Linking a line moves stock-received
truth: the SPO allocation's `quantity_received` and `receipt_status`, and the inbound
shipment's line statuses, refresh as part of the link, exactly as they do when the GRN
arrives second.

---

## Phase 1 - Frontend (mocked)

### AC-FM-1 [FE] A matched line still links to its allocation

**Given** a GRN line whose `spo_allocation` is present
**When** the GRN detail line table renders
**Then** the SPO Allocation cell is a link to `/procurement-management/spo-allocations/{id}`
labelled with the allocation's `spo_number`, unchanged from today.

### AC-FM-1b [FE] A matched line never shows a UUID

**Given** a matched line whose allocation has a null `spo_number`
**When** the cell renders
**Then** the link is labelled with `spo_number_raw` if present, otherwise the literal
`SPO allocation` - never the allocation's id.

This deviates from today's `alloc.spo_number ?? alloc.id`, which puts a raw UUID on screen.
"No UUIDs in the UI" is a `PRINCIPLES.md` hard-fail rule, so the old behaviour is a bug the
shared cell fixes rather than preserves.

### AC-FM-2 [FE] A stated-but-unmatched line shows the stated SPO, not a dash

**Given** a GRN line with no `spo_allocation` and `spo_number_raw = "SPO-2026/07-0012"`
**When** the cell renders
**Then** it shows `SPO-2026/07-0012` in muted text with an "Unmatched" label, and no link.

### AC-FM-3 [FE] A line that stated nothing still shows a dash

**Given** a GRN line with neither `spo_allocation` nor `spo_number_raw`
**When** the cell renders
**Then** it shows `-`.

### AC-FM-4 [FE] One cell, both listings

**Given** the GRN detail line table and the Picking Lines listing
**When** either renders its SPO Allocation cell
**Then** both call the same shared component, so the three states above cannot drift apart.

---

## Phase 2 - Backend

### Storing the stated text

### AC-FM-5 [BE] The stated SPO is stored on a line that could not be matched

**Given** a GRN detail sheet whose line states `SPO-2026/07-0012`
**And** no `spo_allocations` row exists for that SPO number and product
**When** the GRN lines import runs
**Then** the picking line is created with `spo_allocation_id IS NULL`
**And** `spo_number_raw = "SPO-2026/07-0012"`, character for character as the sheet stated it.

### AC-FM-6 [BE] The stated SPO is stored on a line that WAS matched

**Given** the same sheet and a matching allocation
**When** the import runs
**Then** the line carries both `spo_allocation_id` and `spo_number_raw`.

### AC-FM-7 [BE] The header fallback is stored when the line states nothing

**Given** a GRN line whose "Our PO No." is blank
**And** whose GRN header's `spo_number` names exactly one SPO
**When** the import runs
**Then** the line's `spo_number_raw` is that header value.

### AC-FM-8 [BE] A multi-SPO cell stores nothing

**Given** a GRN header whose `spo_number` is `"SPO-A, SPO-B"` and lines that state nothing
**When** the import runs
**Then** the lines' `spo_number_raw` is NULL, because a joined value names no single SPO and
storing it would display a claim the matcher can never honour.

### AC-FM-9 [BE] A re-import refreshes the stored text

**Given** a GRN imported when its sheet stated `SPO-2026/07-0012`
**When** a corrected sheet stating `SPO-2026/07-0013` is imported over it
**Then** the same picking line row now carries `spo_number_raw = "SPO-2026/07-0013"`
**And** no duplicate line was created.

### AC-FM-9b [BE] Editing a GRN does not destroy the stated text

**Given** an imported GRN whose lines carry `spo_number_raw`
**When** the GRN is updated through `PickingHeaderService.update_grn` - which deletes and
recreates its picking lines, both on the "payload supplied" branch and on the
"rebuild and FIFO-link on approval" branch
**Then** every recreated line still carries a `spo_number_raw`
**And** a line whose stated SPO was carried in the update payload keeps that exact value.

### AC-FM-9c [BE] Lines created by the GRN UI / external API state their SPO too

**Given** a GRN with a single-SPO header created through `create_grn`, or approved through
`_create_grn_lines_with_spo_fifo`
**When** its lines are written
**Then** each line's `spo_number_raw` is that header SPO, so a GRN that arrives through the
UI or the external API before its SPO is also forward-matchable.

**And** this holds from CREATE, not only from approval: a draft GRN is the state a
just-arrived receipt sits in, and it is exactly the GRN whose SPO has not landed yet.

**And** on the external API (`POST /api/v1/external/grn`) the stated text is the line's own
`spo_allocation` field, carried through to `spo_number_raw`. That route builds its
`PickingLineCreate` by hand, and `create_grn` deliberately drops `spo_allocation_id` (a GRN links
on approval, not on create), so without it every n8n / AutoCount line was left neither linked nor
stated.

**Still rejected, deliberately:** that route 400s a line naming an SPO allocation that does not
exist for its (spo_number, product, warehouse) triple. So a GRN posted through the external API
BEFORE its SPO lands is refused at the door rather than stored as stated-but-unmatched - the
import and the UI are the paths that tolerate the two orders. Relaxing that 400 would change what
the integration is told about a receipt it cannot yet reconcile, which is a separate decision
from this one; it is recorded here so the document matches what ships.

### AC-FM-10 [BE] Existing rows are backfilled

**Given** picking lines that existed before this change
**When** the migration runs
**Then** a line with an allocation carries that allocation's `spo_number` as `spo_number_raw`
**And** an unlinked line under a single-SPO GRN header carries that header's `spo_number`
**And** an unlinked line under a multi-SPO header carries NULL.

### Forward matching

### AC-FM-11 [BE] Creating the allocation links the waiting lines

**Given** an unlinked GRN line with `spo_number_raw = "SPO-2026/07-0012"` and product P
**When** an `spo_allocations` row for that SPO number and product P is created
**Then** the line's `spo_allocation_id` is set to that allocation
**And** the allocation's `quantity_received` and `receipt_status` are re-synced.

### AC-FM-12 [BE] Matching is tolerant of separator style, and only of that

**Given** an unlinked line stating `SPO-2026/07-0012`
**When** an allocation numbered `SPO-202607-0012` is created
**Then** the line is linked, because both reduce to the same `_spo_match_key`
**And** an allocation numbered `SPO-2026/07-0013` links nothing.

### AC-FM-13 [BE] Only unlinked lines are touched

**Given** a GRN with one linked and one unlinked line under the same SPO
**When** forward matching runs
**Then** the linked line's `spo_allocation_id`, quantities and `updated_at` are unchanged.

### AC-FM-14 [BE] The pool is drawn FIFO, oldest allocation first

**Given** allocations A (created first, 60 available) and B (created second, 100 available)
for the same SPO and product, both in the line's warehouse
**And** one unlinked line of quantity 130
**When** forward matching runs
**Then** 60 is linked to A and 70 to B
**And** no unlinked remainder row exists.

### AC-FM-15 [BE] The line's own warehouse is preferred over age

**Given** allocation A (older, warehouse W2) and allocation B (newer, warehouse W1), both
with capacity, and an unlinked line in warehouse W1
**When** forward matching runs
**Then** B is drawn first, matching the import's two-pass rule (same warehouse, then any).

### AC-FM-16 [BE] An uncovered remainder stays stated-but-unmatched

**Given** allocations totalling 160 available and one unlinked line of quantity 200
**When** forward matching runs
**Then** the line is split into linked rows totalling 160 plus one row of 40 with
`spo_allocation_id IS NULL`
**And** that remainder row still carries `spo_number_raw`, so it still reads as stated.

### AC-FM-17 [BE] Forward matching never over-draws

**Given** an allocation of 50 already fully drawn by a line on a different GRN
**When** an unlinked line of quantity 20 for the same SPO and product is forward matched
**Then** it stays unlinked, and the allocation's drawn total is still 50.

### AC-FM-17b [BE] A rejected GRN is never forward matched

**Given** an unlinked line on a GRN whose `picking_status` is `rejected`
**When** forward matching runs for its stated SPO
**Then** the line stays unlinked, because a rejected receipt must not consume allocation
capacity. A `draft` GRN IS matched - that is the normal state of an imported GRN, and it is
the state the import itself links in.

### AC-FM-17c [BE] Approving a GRN never over-draws what a draft already took

**Given** allocation A of 100 under SPO S
**And** a DRAFT GRN whose line is already linked to A for 60 (the normal state of an imported
GRN)
**When** a second GRN for 100 of the same product and SPO is approved through
`PickingHeaderService.update_grn`
**Then** that GRN draws only the remaining 40 from A, and the other 60 is written as a line
with `spo_allocation_id IS NULL` that still states SPO S
**And** the total drawn on A is 100, never 160.

This is a **behaviour change**, and a deliberate one. `_create_grn_lines_with_spo_fifo` sized
availability with `compute_received_for_allocation`, which counts APPROVED headers only, so a
draft GRN's draw was invisible to it and approving through the screen could over-draw an
allocation a draft had already consumed. It now measures capacity the way the shared pool does
(every non-rejected header, drafts included), which is the same strictly-safer arithmetic the
import already gained. Unchanged: this path still LINKS only when the GRN is approved - that is
`update_grn`'s decision, and a separate one from how capacity is measured.

**And** the rebuild does not compete with itself: re-approving a GRN whose lines are already
linked leaves them linked to the same allocations, because that GRN is excluded from its own
consumption exactly as the import excludes itself.

**And** that holds for a GRN that is ALREADY approved. Editing the lines of an approved GRN
releases its allocations (`_unlink_grn_from_spo`) BEFORE the old lines are deleted, exactly as
the approved-to-draft transition does. The pool's self-protection cancels the stored
`quantity_received` with the caller's own linked rows, and those rows have to still exist for it
to work: delete first and this GRN's own approval-written receipt reads as an outsider's,
swallowing the allocation it came from. The line then comes back UNLINKED, and
`sync_grn_received_to_spo` walks only linked lines, so the allocation is left reporting a receipt
that no picking line explains and is un-drawable by every later pool build. Nothing self-heals.

### AC-FM-18 [BE] Repeated forward matching changes nothing

**Given** forward matching has already run for an SPO
**When** it runs again for the same SPO
**Then** no line's `spo_allocation_id` changes, no picking line row is created or deleted,
and the allocations' drawn totals are unchanged.

### AC-FM-19 [BE] Order independence - the point of the feature

**Given** the same GRN sheet and the same SPO allocation FILE, the file holding SEVERAL
allocations (two products/warehouses under one SPO is the normal shape)
**When** run as (GRN import, then SPO import) in one database
**And** as (SPO import, then GRN import) in another
**Then** the resulting picking lines are the same multiset of
`(product, source_warehouse, spo_allocation_id, quantity_expected, spo_number_raw)` - the same
allocation, not merely "some allocation".

The multi-allocation file is the case that matters: matching fired once per allocation ROW runs
before the rest of the file exists, so the line is placed against whichever allocation was
written first instead of the one covering its warehouse. Matching therefore runs once per
`spo_number`, when the whole file has landed.

**And** the same rule at the SCM allocation suggestion. Approving a suggestion writes one
allocation PER SPLIT - several warehouses under one SPO number, in one action - so it is a
multi-allocation writer, not a single-allocation one. It suppresses the per-row hook and sweeps
once after its loops; otherwise a waiting line of 100 in W2 came out split 30 against W1's
allocation and 70 against W2's, instead of drawing its whole 100 from the one covering its own
warehouse.

### AC-FM-20 [BE] A re-import after forward matching is a no-op

**Given** a GRN whose lines were linked by forward matching
**When** the same GRN sheet is imported again
**Then** the same rows are updated in place, with the same allocations and quantities
**And** no duplicate picking line is created.

### AC-FM-21 [BE] Forward matching is best-effort and never fails the allocation write

**Given** forward matching raises
**When** an SPO allocation is created
**Then** the allocation is still created and committed, the caller gets a success response,
and the failure is logged as a warning.

### AC-FM-22 [BE] Every allocation creation path triggers it

**Given** an unlinked line waiting on SPO S
**When** the allocation is created by the SPO Excel import, by the SPO allocation UI/API
create, by the external bulk `POST /api/v1/external/spo-allocations`, or by approving an SCM
allocation suggestion
**Then** the line is linked in all four cases.

### AC-FM-23 [BE] Raising an allocation's quantity releases the waiting lines

**Given** an unlinked line of 40 and an allocation whose capacity is fully drawn
**When** a corrected SPO file re-imports that allocation with a larger `allocated_quantity`
**Then** the freed capacity is forward matched to the waiting line.

### AC-FM-24 [BE] The stated text reaches the frontend

**Given** a picking line with `spo_number_raw` set
**When** the GRN detail and the picking lines listing are fetched
**Then** both responses carry `spo_number_raw`
**And** the picking lines listing search matches on it.

### AC-FM-25 [BE] Header multi-SPO semantics are untouched

**Given** this whole change
**When** `picking_headers.spo_number` holds a joined multi-SPO value
**Then** it is still display-only and still never used for scalar allocation matching.

### AC-FM-27 [BE] Matching never crosses a company boundary

**Given** an unlinked GRN line belonging to company B
**And** an allocation for the same SPO and product belonging to company A
**When** forward matching runs on the `X-API-Key` path, whose company scope is NULL
("all companies") and therefore constrains nothing
**Then** the line stays unlinked
**And** when a company-B line IS split against a company-B allocation, every row the split
creates carries company B - not the incumbent company the insert hook would otherwise stamp,
which would leave the row invisible on its own GRN while still consuming that GRN's allocation.

**And** the same holds at the APPROVAL writer: approving a company-B GRN under that same NULL
scope confines the pool to company B's allocations AND writes every row it creates - the chunk
that drew, and the remainder no allocation covered - carrying company B.

**And** at the GRN lines IMPORT. It confines its pool to the header's company, so
`upsert_grn_line_for_import` is given that company too rather than leaving it to the insert hook -
an import job with no company snapshot runs system-scoped ("all companies"), where the hook
stamps the incumbent. A mis-stamped row is doubly wrong there: the consumption query filters on
`company_id` as well, so the row never counts as consumption and the next import of the same file
over-draws.

Both halves, at every writer, or neither: a path whose pool is confined to the right company
but whose rows are stamped with the incumbent one is worse than a path that is consistently
wrong, because it draws correctly and then shows none of what it drew.

### AC-FM-28 [BE] One column means "the quantity this row drew"

**Given** a picking line written by ANY of the three GRN-line writers (the import,
`_create_grn_lines_with_spo_fifo`, forward matching)
**When** the allocation pool measures consumption, and `compute_received_for_allocation` writes
`spo_allocations.quantity_received`
**Then** both read the same column, `quantity_picked`
**And** a split chunk that drew 70 consumes 70 and reports 70, rather than the whole receipt
being charged to the first allocation and nothing to the rest.

**And** the shipment agrees with the allocation. `InboundShipmentService.get_received_quantities_by_product`
- which PERSISTS `inbound_shipment_lines.quantity_received` and `line_status`, and feeds the
packing-list response - measures `quantity_picked` too, on BOTH its linked and its orphan branch.
It was the last reader still summing `quantity_expected`, so a receipt of 60 against an expected
100 reported 60 on the SPO allocation and 100 on the shipment line, and the container read as
fully received while 40 of it never arrived.

### AC-FM-30 [BE] Forward matching does not erase a short receipt

**Given** an unlinked line with `quantity_expected = 100` and `quantity_picked = 60`
**When** forward matching places all 60 against ONE allocation
**Then** the line keeps `quantity_expected = 100`, so its discrepancy survives
**And** when the same receipt is SPLIT across two allocations, every chunk states the quantity it
drew in both columns.

A split cannot carry an expected-vs-picked discrepancy, because the split IS a fact about what
arrived and each chunk is one allocation's share of it. An unsplit line still can, and it is the
ordinary way a short delivery is visible to the office. Overwriting `quantity_expected` on every
link, split or not, dropped `quantity_discrepancy` to 0 and lost the 40 that never came.

### AC-FM-29 [BE] Two lines of one product on one GRN cannot draw the same capacity

**Given** an approval whose payload holds TWO lines of the SAME product, their quantities
together exceeding what the SPO's allocations can cover
**When** the GRN is approved
**Then** the second line draws only what the first one left
**And** the uncovered remainder is written as an unlinked line, not dropped
**And** the total drawn across both lines never exceeds the allocation's capacity.

The approval writer builds ONE pool per product and draws it down across the payload, which is
load-bearing rather than an optimisation: it excludes the GRN it is rewriting from its own
consumption (so a re-approval does not compete with itself), and therefore a pool rebuilt per
line would not count the rows the previous line just wrote and would hand the same capacity
out twice.

### Shared matcher

### AC-FM-26 [T] All three writers run the same code

**Given** the three things that place a GRN line against an allocation - the GRN lines import,
the forward-matching backfill, and `_create_grn_lines_with_spo_fifo` (the UI / external-API
approval path)
**When** any of them builds an allocation pool or draws from it
**Then** all three call the same `build_allocation_pool` / `draw_fifo` functions, none carries
its own inline two-pass loop, and a `grep` for the two-pass warehouse-then-age rule returns
exactly ONE implementation in the backend (`grn_spo_matching.draw_fifo`).

The third writer is the one this AC turned out to be really about. A second copy of the rule is
how the directions come to disagree; a third copy, measuring availability with a DIFFERENT
reader (`compute_received_for_allocation`, approved headers only) than the shared pool uses, is
how they came to disagree about capacity rather than merely about order - see AC-FM-17c.

---

## Out of scope (deliberate)

- Auto-creating SPOs or allocations from the GRN side. Forward matching links to allocations
  that legitimately appear, and creates nothing.
- Changing the multi-SPO header semantics (AC-FM-25 pins them).
- The bundle-card / neighbour-code guard issues in the flyer importer.
- A manual "relink" action in the UI. If forward matching is right, nobody needs one.
- A persisted Playwright spec. This change adds no new user-facing flow, no new page and no
  new action - it changes one table cell and what a background import stores. The flow is
  verified with Playwright MCP against the running stack instead, and this deviation is
  recorded in the PR description per `.claude/skills/feature/SKILL.md`.
