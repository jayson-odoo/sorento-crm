# PLAN: SPO Allocations list shows and searches the inbound shipment's container number

Status: PLANNED 11 Sep 2026 (owner ask, screenshot of Procurement > SPO Allocations)
Branch: `feat/spo-list-container-number` (worktree `.claude/worktrees/spo-list-container`, base `origin/main`)
UAC: `spo-list-container-number-acceptance-criteria.md`
Domain: purchasing (SPO Allocations document list)

## Owner ask (11 Sep 2026, verbatim)

> add inbound shipment's container number here and be able to search by the inbound
> shipment container number

"Here" = the SPO Allocations header list (`/procurement-management/spo-allocations`,
columns SPO No, Date, Supplier, Status, Earliest ETA, Total qty, Lines, Balance, Overdue).

## What exists today (measured, local 8 Sep prod copy)

- Header list = `GET /api/v1/procurement/spo-allocations/documents`,
  `SPOAllocationService.list_documents` (`app/services/procurement_service.py:2249-2478`):
  one `GROUP BY spo_number` over `SPOAllocation` OUTER JOIN `InboundShipment` on
  `SPOAllocation.inbound_shipment_id`. Row schema `SPODocumentRow`
  (`app/schemas/procurement.py:684`). No `list_query_registry` entry; export is client-side
  from the grid's accessor columns (`components/ui/data-grid-list-toolbar.tsx:307-360`).
- Two container sources per LINE:
  - `inbound_shipments.shipping_container_number` via `spo_allocations.inbound_shipment_id`:
    2,435 of 77,260 lines, 255 of 3,778 SPOs.
  - `spo_allocations.container_number` (migration 477, written by shipping-order ingest):
    14 lines, every one also linked to a shipment carrying the SAME number. Fallback only.
- One SPO can span several containers: 3 SPOs on the copy carry 2 distinct containers
  (`SPO-2026/07-0026`, `SPO-2026/08-0002`, `SPO-2026/08-0015`).
- Search (`query` param, `procurement_service.py:2330-2371`) ALREADY matches
  `InboundShipment.shipping_container_number` through `MatchLine.inbound_shipment_id`.
  It does NOT match the raw `spo_allocations.container_number` column. Placeholder says
  "Search SPO or product..." so nobody knows container search exists.
- No container column on the list. The detail page shows the FIRST linked shipment's
  container in the linkage strip only.

## Change (simplest thing)

### Backend (`sorento_crm_backend`)

1. `app/services/procurement_service.py` `list_documents`: add one aggregate column
   `container_numbers` = sorted distinct non-null values of
   `coalesce(SPOAllocation.container_number, InboundShipment.shipping_container_number)`
   over the document's VISIBLE lines (same `is_visible` gate the other rollups use).
   SQL shape: `array_remove(array_agg(DISTINCT <expr> ORDER BY <expr>), NULL)`, where
   `<expr>` = `CASE WHEN is_visible THEN coalesce(...) END`. Emit `container_numbers`
   (Python list of str, `[]` when none) on each row dict. Add `sort_map["container_numbers"]`
   = `min(<expr>)` so the column header sorts.
2. Search: append `MatchLine.container_number.ilike(f"%{q_str}%")` to the existing `or_`
   so an ingested-but-unlinked container is findable too. Nothing else changes; the
   shipment-number and shipment-container legs stay.
3. `app/schemas/procurement.py` `SPODocumentRow`: `container_numbers: list[str] = []`
   with a docstring line. (`response_model` drops undeclared fields; the AC-2 field test
   pins the set.)
4. Route docstring in `app/api/v1/procurement/spo_allocations.py` (`get_spo_documents`):
   mention container in the `query` description.

### Frontend (`sorento_crm_frontend/app/(protected)/procurement-management/spo-allocations/`)

5. `types/spoDocument.types.ts` `SPODocumentRow`: `container_numbers: string[]`.
6. `components/SPOAllocationsList.tsx`: new column right after Supplier, id
   `container_numbers`, `accessorFn: row => row.container_numbers.join(', ')` (so the
   client export carries it), header `DataGridColumnHeader title="Container No"`,
   cell = joined string in `<span className="truncate" title={joined}>`, `-` when empty,
   `size: 160`, `meta: { headerTitle: 'Container No' }`. Sorting goes through the grid's
   existing server sort with `sort=container_numbers`.
7. Search placeholder -> `"Search SPO, product or container..."`.
8. `services/spoDocumentService.ts` header comment already lists container; no code change.

No migration, no new table, no registry. Saved column orders merge the new id in via
`mergeColumnOrder` (it lands at the right edge for users with a saved order; expected).

## Out of scope

- Detail page raw `spo_allocations.container_number` display (unlinked containers are
  invisible there too). Separate ask if wanted.
- Container status / ETA tracking (`PLAN-container-status-tracking.md`, DRAFT).

## Tests (tester writes first, red)

pytest `tests/scm/test_spo_allocation_documents.py` (Postgres fixture, seed own chain):
- AC-1 `test_document_row_carries_container_numbers`: two lines on one SPO, one linked to a
  shipment with container `ZZTU1111111`, one with raw `container_number='ZZTU2222222'` and
  no shipment -> row `container_numbers == ['ZZTU1111111', 'ZZTU2222222']` (sorted, distinct).
- AC-2 `test_container_numbers_empty_when_none`: SPO with no container anywhere -> `[]`.
- AC-3 `test_container_numbers_dedupe_and_skip_retired`: two lines both on the same
  container -> one entry; a retired line's container is excluded.
- AC-4 `test_query_matches_raw_allocation_container_number`: line with
  `container_number='ZZTU3333333'`, `inbound_shipment_id NULL`; `?query=ZZTU3333` returns
  the SPO, `?query=ZZTU9999` does not. Existing shipment-container search test stays green.
- AC-5 `test_sort_by_container_numbers`: `sort=container_numbers&dir=asc` orders by the
  first container; SPOs with none sort last.
- Update `test_document_row_declares_every_ac2_field` to include `container_numbers`.

vitest `components/SPOAllocationsList.test.tsx`:
- AC-6 column header "Container No" renders; row cell shows `ZZTU1111111, ZZTU2222222`
  with `title` attribute; empty list renders `-`.
- AC-7 search placeholder reads "Search SPO, product or container...".
- `services/spoDocumentService.test.ts`: no change needed (query string unchanged).

## Pipeline note

Phase 1 FE mock skipped on purpose: the whole FE change is one column and one placeholder
string; the contract (`container_numbers: string[]`) is stated above. Recorded here and in
the PR description.
