# PLAN: local supplier routing to Order Inquiry, countries master, borrow source table

Status: in review (PR open 10 Sep 2026; Phases 1-3 complete, reviewed, browser verified; owner runs the supplier country backfill on prod after deploy)
UAC: `local-supplier-oi-routing-acceptance-criteria.md`
Domain: scm (touches master-data, procurement)
Owner decisions: 10 Sep 2026, four grill rounds. Branch `feat/local-supplier-oi-routing`.

## Why

- Products bought from a Malaysian supplier still flow to the Order Inquiry on confirm, so
  purchasing's overseas list carries local buys it must not raise with a China factory.
  The Buy → OI handoff (`ProjectOrderInquiryService.refresh_for_decision`) never reads a
  supplier; OI rows have no supplier column at all.
- `suppliers.country` exists but is NULL on all 1,163 rows and nothing reads it. By name,
  588 of 5,353 products' newest-PO supplier is Malaysian (SDN BHD), the largest being
  MOCHA SDN BHD (459 POs, related company, ruled local).
- The OPTIONS sub-lines ("BRW has nothing to spare for projects", "IR group is 34 short on
  its own book, nothing to spare") repeat what Gives 0 / Whole No already say.
- The Borrow modal's Source table shows On hand / SO / SPO / Available / Free / Committed
  with no way to see WHICH sales orders sit on a source; the Grid Location table already
  shows that ledger. Owner wants the same table in the modal.

## Measured facts (prod copy `sorento_ai_automation_0907`, 10 Sep 2026)

| fact | value |
| --- | --- |
| suppliers, all with NULL country | 1,163 |
| products with a newest-PO supplier | 5,353 |
| ... whose supplier name matches SDN BHD / (KL) / MALAYSIA | 588 |
| PO currency as a local signal | unusable: retired "DO NOT USE" China codes carry MYR |
| home currency constant | `app/services/scm/money.py:28` `BASE_CURRENCY = "MYR"` |
| companies table country column | none |
| alembic head at plan time | `509_merge_508_summary_and_excl_wh` (origin/main after #807) |

## Decisions (owner)

1. Local = supplier country equals the home country. Home country is a module constant
   `HOME_COUNTRY_CODE = "MY"` beside `BASE_CURRENCY`; both companies are in Malaysia, a
   company column buys nothing today. Trigger to add one: a company outside Malaysia.
2. Countries are a NEW reference table with a full CRUD page under Master Data, copying
   Units of Measure. Owner reaffirmed after being offered the existing Lookup Sets
   mechanism. Justification carried with the copy: a reference entity that suppliers
   reference by FK today and customers / users will later.
3. Product origin chain: primary `product_suppliers` link → newest PO supplier → none.
   None, or a supplier with no country, is overseas. Mocha is local.
4. A local Buy creates NO Order Inquiry row. Decision still records Buy. Consequence the
   owner accepted: no reorder demand either (SCM demand reads `order_inquiry_rows`).
5. Indicator: `Local` pill on the Buy option row and in the Suggested / Decided cell,
   local lines only. Overseas unmarked. No trail text, no supplier name on screen.
6. Option reason sub-lines: dropped from the OPTIONS table (frontend stops rendering).
7. Borrow modal: candidate basis unchanged (free > 0 outside the line's own reserve pool,
   plus other-project holds and later-order donors). Source table becomes the Grid
   Location table with radio + Recommended + per-row SO ledger expansion; the
   After-borrow sentence stays. No Location table in the List view expanded row.
8. Backfill: name heuristic → `MY`, rest blank; owner runs on prod.
9. A line raised on the OI before this lane whose product is now local is left alone on
   the next confirm (not re-raised, not cancelled). Purchasing closes it by hand.
10. Countries permissions are derived, not admin-only (Phase 3 fix round ruling):
    `.view` to every role holding `master_data.units_of_measure.view` OR
    `procurement.suppliers.view`; `.add`/`.edit`/`.delete` to every role holding
    `user_management.reference_data.manage` (the shared reference-vocabulary write
    authority from `s6b_reference_data_manage_perm`), not the UoM write slugs.

## Design

### S1 Countries master (BE + FE)

Backend, copy of Units of Measure shape:

- `app/models/country.py`: `Country(Base)` `__tablename__ = "countries"`,
  `__company_shared__ = True` (lesson: a migration-seeded reference table without it is
  invisible to scoped users). Columns: `id` uuid, `code` String(2) NOT NULL with a unique
  index on `lower(code)`, `name` String(100) NOT NULL, `is_active` bool default true,
  `created_at`, `updated_at`. Register in `app/models/__init__.py`.
- Migration `510_countries` (down_revision `509_merge_508_summary_and_excl_wh`, re-parented by
  `./scripts/alembic-reparent.sh` at PR time): create table, seed the ISO 3166-1 alpha-2
  list from a static tuple inside the migration (no new dependency), register the four
  `master_data.countries.{view,add,edit,delete}` slugs and grant each to every role that
  holds the matching `master_data.units_of_measure.<action>` today (derived set, the
  s6b_reference_data_manage_perm pattern).
- `app/rbac/permission_registry.py`: `PERMISSION_REGISTRY.extend(_crud("master_data",
  "countries", "Countries"))` next to units_of_measure.
- `app/schemas/country.py`: `CountryCreate`, `CountryUpdate`, `CountryResponse`,
  `CountrySelectItem`.
- `app/services/country_service.py`: list (page, limit, query on code/name, sort), get,
  create (409 on duplicate code, case-insensitive), update, delete (409 naming the count
  of referencing suppliers). Raise `AppException`.
- `app/api/v1/master_data/countries.py`: `GET /`, `GET /select`, `GET /{id}`, `POST /`,
  `PUT /{id}`, `DELETE /{id}` with `require_permission_with_api_key` on reads,
  `require_permission` on writes. Mount in `app/api/v1/master_data/__init__.py` under
  `/countries`.
- Deferred delete: register `country.delete` in `app/services/record_actions.py` (the
  S6b registry) with the hard-delete window, sharing the 409 guard. The FE list uses
  `useDeferredRowAction({ actionKey: 'country.delete' })` like `UOMList.tsx:61`.
- `list_query_registry.py`: register `countries` for the DataGrid contract, listing key
  `master_data.countries.view`.

Frontend, copy of `master-data-management/units-of-measure/`:

- `app/(protected)/master-data-management/countries/{page.tsx, loading.tsx,
  types/country.types.ts, forms/country-schema.ts, components/CountryList.tsx,
  components/CountryFormDialog.tsx, hooks/useCountries.ts, services/countryService.ts}`.
  Create/edit is a modal (CRUD standard), not the UoM `new/` and `[id]/edit/` pages.
  Columns: Code (size 100), Name (size 280, truncate + title), Active (Badge), actions.
  `tableLayout: { width: 'fixed', columnsResizable: true }`, `columnResizeMode:
  'onChange'`, `buildDataGridParams`, `extractApiError`.
- `config/menu.config.tsx`: Countries under Master Data, beside Units of Measure (both
  menu trees, lines ~436 and ~1703), `moduleKey` `master_data`, permission
  `master_data.countries.view`. Add to `menu.config.test.ts` path list.
- Service contract header (Phase 1 doc): list `DataGridApiResponse<Country>` (`{data, empty,
  pagination: {total, page}}`, the repo's own DataGrid contract), select `[{id, code, name}]`.

### S2 Supplier country FK (BE + FE)

- Migration `511_supplier_country_id`: add `suppliers.country_id` uuid FK `countries.id`
  ON DELETE RESTRICT, nullable, index `ix_suppliers_country_id`; drop `ix_suppliers_country`
  and the `country` text column (NULL on every row, verified). Update the list-query
  metadata row inserted by `101_list_query_metadata.py:149` so field `country` reads
  `country.name` (joined) instead of `supplier.country`.
- `app/models/procurement.py` `Supplier`: replace `country` with `country_id` +
  `relationship("Country")`. `__table_args__` index swap.
- `app/schemas/procurement.py`: `SupplierBase.country_id: Optional[str]`,
  `SupplierResponse` adds `country_code`, `country_name`. 422 on unknown id.
- Supplier service serializers: every manual dict (list, detail, select) emits the three
  fields. Lesson: assert in a test, `response_model` drops what is undeclared.
- `app/services/master_ingest_service.py:351-381` `_supplier_columns`: `country`
  resolves name or code to `country_id` case-insensitively; unresolved → row warning,
  field null, row imports.
- `scripts/backfill_supplier_country.py`: dry-run default, `--apply`. Selects suppliers
  with `country_id IS NULL` whose `supplier_name ~* 'SDN\.? ?BHD|\(KL\)|MALAYSIA'`, sets
  `MY`. Prints per-supplier lines and a count. Imports only code on main after S1/S2 merge
  (runs on the deployed image, same discipline as PR #797's script).
- FE `procurement-management/suppliers/`: `supplier-schema.ts` `country_id: z.string()
  .uuid().optional().nullable()`; `SupplierForm.tsx:334-346` Country becomes
  `SearchableSelect` (clearable) over `countryService.select()`; list column and detail
  header render `country_name`; `supplier.types.ts` gains the three fields.

### S3 Origin resolution + confirm routing (BE + FE pill)

- `app/services/scm/supply_origin.py`:
  - `HOME_COUNTRY_CODE = "MY"` lives in `app/services/scm/money.py` beside
    `BASE_CURRENCY`; `supply_origin` imports it.
  - `buy_origin_by_product(db, product_ids: Iterable[str]) -> dict[str, str]`: one query
    for primary links joined to countries, one `DISTINCT ON (product_id)` query for
    newest-PO suppliers (same ORDER BY as `summary_order_service.py`'s S15 supplier
    lookup, reuse that helper if it is importable), merged in Python. Values `"local"` /
    `"overseas"`.
- Board: `project_fulfilment_board_service.py` collects the product ids of all rows once
  in `build()`, calls `buy_origin_by_product`, and `_contribution()` (near :4476-4630)
  emits `"buy_origin"`. `app/schemas/project_board.py` `BoardContribution.buy_origin:
  Literal["local","overseas"]`. Per-order sheet: `SupplyLine.buy_origin` in
  `app/schemas/project_supply.py`, filled where `borrow_candidates` is filled.
- Confirm: `project_supply_service.py:5600-5646` adds `"origin": origin_by_product.get(
  fact.product_id, "overseas")` to BOTH the checked and the carried `buy_lines` entries.
  `ProjectOrderInquiryService.refresh_for_decision` (`:417`) skips a buy line whose
  `origin == "local"` before the raise / diff pass: it is neither raised nor treated as
  dropped, so an earlier raised row on that line is left untouched (AC-2.17). The header
  is still minted lazily only when an overseas residual exists (existing rule).
- Confirm result: the Buy count and the summary cards count local Buys as Buy (no change).
- FE pill: `FulfilmentBoardListView.tsx` `suggested` (243-291) and `decided` (292-340)
  cells append `<Badge variant="secondary">Local</Badge>` when `contribution.buy_origin
  === 'local'` and the verdict is Buy. `BoardLadderOptionsTable.tsx` Buy row label gets
  the same Badge via a new optional `buyOrigin` prop passed from
  `BoardLineDecisionPanel.tsx:446-452` (and `SupplyLineCard.tsx:181`,
  `BoardTrailPopover.tsx:210` pass nothing, so no pill there). Grid: `BoardCellBreakdownDialog`
  "Contributing lines" grid (:1166+) mirrors the Suggested/Decided pill.
- Contract doc: `_shared/services/fulfilmentPlanningService.ts:325-345` documents
  `buy_origin` and `borrow_candidates[].location`.

### S4 Borrow modal = Location table + ledger (BE + FE)

- Backend: `ProjectSupplyService._borrow_candidates` (`:8507`) attaches
  `candidate["location"]` built by the same location builder the board uses
  (`project_fulfilment_board_service._location()` region `:4271`; if that builder lives
  on the board service, expose a shared function in one place rather than a copy). The
  board mapping at `project_fulfilment_board_service.py:4552-4574` passes `location`
  through. Schema: `BorrowCandidate.location: BoardCellLocation` in both
  `project_board.py` (:756-764) and `project_supply.py` (:93+).
- Frontend `BorrowAddDialog.tsx`: replace the Source radio table (120-249) with
  `CellStockTable` fed by `candidates.map(c => c.location)`, adding two optional props to
  `CellStockTable`: `selectable={{ value, onChange }}` (radio rendered inside the Location
  cell, before the code) and `badges` (`Recommended` / `Same agent` per warehouse id).
  Row expansion already mounts `StockDocumentsPanel` (`CellStockTable.tsx:534-552`) with
  `productId`, `warehouseId`, `lineIds`; pass `lineIds=[line.id]` so `This line` marks the
  current line. Drop `NUMERIC_COLUMNS` 379-412. Keep `openingQty()`, `BorrowImpact`,
  Reason, buttons. Dialog width `max-w-5xl`; body `overflow-x-auto` for 375px.
- `SupplyLineCard.tsx:407` gets the same dialog for free.
- Group subtotal rows: hidden in the modal (`showGroupSubtotal={false}`), a donor list is
  not a group.

### S5 Copy

- `BoardLadderOptionsTable.tsx:85-96`: delete the reason sub-line render and its test
  ids. Backend keeps `reason` in the payload (trail and pytest untouched).

## Slices and order

| slice | scope | depends on |
| --- | --- | --- |
| S1 | Countries table, migration, permissions, CRUD API, Master Data page | none |
| S2 | Supplier `country_id`, form select, ingest resolve, backfill script | S1 |
| S3 | `supply_origin`, board `buy_origin`, confirm skip, pill | S2 |
| S4 | Borrow candidate `location`, modal = `CellStockTable` + ledger | none |
| S5 | Drop option reason sub-line | none |

Phase 1 builds S1, S2, S3-pill, S4, S5 frontends against mocks in one worktree; Phase 2
lands S1 → S2 → S3 backend test-first, then S4 backend. One lane, one PR.

## Testing seams (agreed before Phase 2)

- `buy_origin_by_product` is a pure function of (db rows) → dict; tests seed products,
  suppliers, links, POs via `tests/_pg_fixture.py`, never `LIMIT 1` off existing data.
- `refresh_for_decision` is called with hand-built `buy_lines`; the local-skip test does
  not need the board.
- `CellStockTable` selectable mode is tested in vitest with mocked `useStockDetail`.

## No-motion list

`Local` pill, Countries grid rows, Borrow modal table rows, radio selection. The only
motion is the existing row-expansion in `CellStockTable` and the modal open/close, both
already on `lib/motion.ts` presets. `find-animation-opportunities` not run: no new surface
beyond a copied CRUD page and a table swap; recorded here per the skill.

## Design brief

| surface | density | frequency | must not animate |
| --- | --- | --- | --- |
| Fulfilment planning List view | dense | many times a day | pill, cell text |
| Borrow modal | dense | several a day | table rows, radio |
| Master Data › Countries | standard | rare (setup) | grid rows |
| Supplier form | standard | weekly | select |

## Risks

- Dropping `suppliers.country`: safe (all NULL), but any external reader of the list
  export field `country` keeps its name and now reads the joined name.
- A product whose newest PO is from a retired duplicate code (e.g. `400-F019 DO NOT USE`)
  resolves through that supplier; the backfill only sets the country by name, so a
  retired China code stays overseas. Correct.
- `refresh_for_decision` skip must run before the "absent line = dropped" pass or a local
  line's old row gets cancelled (measured: that pass exists, see `project_supply_service.py
  :5620-5623` comment). AC-2.17 guards it.

## After deploy (owner)

1. `scripts/backfill_supplier_country.py` dry-run, then `--apply`, on prod via docker cp.
2. Spot-check MOCHA SDN BHD and a China supplier on Procurement › Suppliers.
3. Confirm one Mocha-sourced Buy and check it does not appear on the Order Inquiry.

## Follow-ups (backlog)

- Customer / user country onto the same master.
- Origin-aware lead time defaults (local vs overseas) once measured lead times diverge.

## Captain's test list (Phase 2, tester writes these red BEFORE the coder)

Backend, pytest on Postgres via `tests/_pg_fixture.py`, every fixture seeded by the test:

- AC-2.1 `tests/test_countries.py::test_migration_seeds_iso_list` - after `alembic upgrade head` on the scratch DB, `countries` has 249 rows and `MY` reads `Malaysia`.
- AC-2.2 `test_countries.py::test_company_shared_visible_to_scoped_user` - a non-admin user of company B lists countries and sees the seeded rows.
- AC-2.3 `test_countries.py::test_crud_routes_and_permissions` - list/select/get/create/update/delete succeed with the right slug; a role missing each slug gets 403 on that route.
- AC-2.4 `test_countries.py::test_delete_refused_while_referenced` - a supplier references the country; DELETE returns 409 naming `1 supplier`; row still present.
- AC-2.5 `test_countries.py::test_duplicate_code_case_insensitive_409` - POST `my` when `MY` exists is 409; PUT renaming another row to `my` is 409.
- AC-2.6 `test_countries.py::test_permissions_registered_and_granted_like_uom` - the four slugs exist in the registry; every role holding `master_data.units_of_measure.view` holds `master_data.countries.view` after migration (same for add/edit/delete).
- AC-2.7 `test_countries.py::test_deferred_delete_action_registered` - `country.delete` is in the record-action registry and its handler raises the same 409 when referenced.
- AC-2.8 `tests/test_supplier_country.py::test_country_id_column_and_text_column_dropped` - `suppliers.country_id` exists with FK RESTRICT; `suppliers.country` does not exist; list-query metadata field `country` for suppliers points at the joined name.
- AC-2.9 `test_supplier_country.py::test_supplier_payloads_carry_country_fields` - create with `country_id`, then list, detail and select each return `country_id`, `country_code`, `country_name`; unknown id on create is 422.
- AC-2.10 `test_supplier_country.py::test_ingest_resolves_name_or_code` - master ingest rows with `Malaysia`, `my`, and `Atlantis` resolve, resolve, and warn-null respectively; all three rows import.
- AC-2.11 `tests/scm/test_backfill_supplier_country.py::test_dry_run_apply_idempotent_never_overwrites` - seeded names `FOO SDN BHD`, `BAR SDN. BHD.`, `BAZ (KL) SDN BHD`, `QUX MALAYSIA`, `CHAOZHOU X CO LTD`, and one SDN BHD already set to CN: dry-run changes nothing and lists 4; `--apply` sets 4 to MY, leaves CN and the China name null; second `--apply` reports 0.
- AC-2.12 `tests/scm/test_supply_origin.py::test_origin_chain` - three products: primary link to MY supplier = local; no link but newest PO from MY supplier = local; no link, no PO = overseas; link to a supplier with null country = overseas.
- AC-2.13 `test_supply_origin.py::test_primary_link_beats_newer_po` - primary link MY, newest PO CN → local.
- AC-2.14 `tests/scm/test_confirm_local_buy_no_oi.py::test_board_and_supply_carry_buy_origin` - board contribution and `/supply` line carry `buy_origin`; a counter on the origin query proves one call per request.
- AC-2.15 `test_confirm_local_buy_no_oi.py::test_local_buy_records_decision_no_oi_row` - confirm Buy on a local product: decision revision has the Buy, confirm result counts 1 buy, zero `order_inquiry_rows`, zero `order_inquiries`.
- AC-2.16 `test_confirm_local_buy_no_oi.py::test_mixed_order_raises_only_overseas` - two lines, one local one overseas: exactly one row, one header, row belongs to the overseas line.
- AC-2.17 `test_confirm_local_buy_no_oi.py::test_prior_raised_row_on_now_local_line_untouched` - seed a raised ORDER row for the line from an earlier revision, flip the product local, confirm again: the row's verb and state are unchanged and no new row exists.
- AC-2.18 `test_confirm_local_buy_no_oi.py::test_carried_local_line_skipped` - confirm a different line on an order whose earlier decided line is local: the carried local line still raises nothing.
- AC-2.19 `test_confirm_local_buy_no_oi.py::test_scm_demand_sees_no_local_buy` - after AC-2.15's confirm, the demand query for that product returns no project demand from that line.
- AC-2.20 `tests/scm/test_borrow_candidate_location.py::test_candidate_carries_location_in_cell_shape` - board contribution `borrow_candidates[0].location` has the BoardCellLocation keys and its figures equal the Grid Location row for the same warehouse in the same request; `/supply` line likewise.
- AC-2.21 `test_borrow_candidate_location.py::test_stock_detail_cross_group_donor_marks_this_line` - `stock-detail` for a donor warehouse outside the line's group returns the current line's row with `is_this_line` true.

Frontend, vitest (jsdom), mocks at the service boundary:

- AC-1.1 `FulfilmentBoardListView.test.tsx::renders Local pill in Suggested and Decided for local Buy only` - two contributions, one local one overseas: exactly one `Local` badge in Suggested; after a decision, one in Decided.
- AC-1.2 `BoardLadderOptionsTable.test.tsx::never renders option reason sub-line` - option with `reason` set: no `ladder-option-reason-*` element.
- AC-1.3 `BoardLadderOptionsTable.test.tsx::Buy row shows Local pill when buyOrigin is local` - prop `buyOrigin="local"` → badge on the Buy row only; overseas → none.
- AC-1.4 `BorrowAddDialog.test.tsx::renders CellStockTable columns with radio and Recommended` - the nine Location-table headers present, Free/Committed/After borrow absent, radio per row, Recommended on the first.
- AC-1.5 `BorrowAddDialog.test.tsx::expanding a source shows its ledger with This line` - `useStockDetail` mocked; expand row → ledger rows and the `This line` badge.
- AC-1.6 `BorrowAddDialog.test.tsx::after-borrow sentence updates with quantity` - type 2 → sentence reads the new figures.
- AC-1.7 `BorrowAddDialog.test.tsx::empty candidates shows No donor holds this item`.
- AC-1.8 `CountryList.test.tsx::lists, searches, opens edit modal, deferred delete countdown` - `useDeferredRowAction` mocked; delete button starts the countdown, Cancel reverts.
- AC-1.9 `CountryForm.test.tsx::rejects empty and non-2-letter code`.
- AC-1.10 `SupplierForm.test.tsx::country is a clearable SearchableSelect fed by the countries select` - select shows names, submit sends `country_id`, clear sends null.
- AC-1.11 `SupplierList.test.tsx::shows country_name never the id`.

Kill-test candidates for the reviewer: AC-2.15, AC-2.17, AC-2.4.
