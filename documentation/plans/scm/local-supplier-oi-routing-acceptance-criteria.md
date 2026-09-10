# UAC: local supplier routing, countries master, borrow source table

Plan: `PLAN-local-supplier-oi-routing.md`. Grilled 10 Sep 2026 (4 rounds, owner). Slice ids S1-S5 match the plan.

## Journey

Actor: the planner on Project Sales › Fulfilment planning, arriving from the worklist with sales orders selected. The board lists every contributing line with a suggested verdict. The system already knows each product's supplier from PO history (PR #797 backfill) and, after this lane, whether that supplier sits in the home country. The planner confirms Buy exactly as today, with no extra decision. On confirm, only overseas Buys become Order Inquiry rows; a local Buy is saved on the decision as Buy and goes nowhere else, so it reaches neither the OI worklist nor reorder demand. Before confirming, the planner can see which Buys are local from a `Local` pill on the Buy option row and in the Suggested / Decided cell. When a Buy looks wrong, the planner clicks Add a borrow and reads, per source location, the same Location table the Grid view shows, expanding a source to see which sales orders sit on it before picking it. Purchasing maintains a Countries master under Master Data and sets each supplier's Country from it; a one-shot script seeds the obvious Malaysian suppliers.

Decisions the planner makes: none new. Decisions purchasing makes: a supplier's Country, once.

## Phase 1 (frontend, mocked)

- AC-1.1 `[FE]` Given a contributing line whose `buy_origin` is `local`, when the List view row renders, then the Suggested cell reads `Buy 39` followed by a `Local` pill (`Badge`, neutral variant), and the Decided cell shows the same pill once decided. Overseas lines show no pill.
- AC-1.2 `[FE]` Given the expanded row OPTIONS table, when any option row renders, then no reason sub-line is rendered under the option label (the `ladder-option-reason-*` element no longer exists). Applies to `BoardLadderOptionsTable` everywhere it is used (List view, trail popover, per-order sheet).
- AC-1.3 `[FE]` Given a line whose `buy_origin` is `local`, when the OPTIONS table renders its Buy row, then the Buy label carries the same `Local` pill. Overseas: no pill.
- AC-1.4 `[FE]` Given Add a borrow is clicked, when the Borrow modal opens, then the Source section is the Grid Location table (`CellStockTable`) with columns Location · Where · On hand · SO qty · SPO qty · Available · Available for Project · PO qty · Taken, a radio in the Location cell, the `Recommended` badge on the first candidate, and no Free / Committed / After borrow columns.
- AC-1.5 `[FE]` Given the Borrow modal Source table, when a source row is expanded, then the SO ledger (`StockDocumentsPanel`: Type · Document · Customer / supplier · Agent · Delivery / expected · Bin · Quantity · Balance after) renders for that warehouse, with the `This line` badge on the current line. The modal widens to fit the table without horizontal page scroll at 1280px, and scrolls inside its own container at 375px.
- AC-1.6 `[FE]` Given the Borrow modal with a candidate selected and a quantity typed, when the quantity changes, then the sentence "After borrowing N: available X, free Y" still updates below Quantity (unchanged behaviour).
- AC-1.7 `[FE]` Given no candidates, when the modal opens, then the existing "No donor holds this item" empty state renders (unchanged).
- AC-1.8 `[FE]` Given Master Data › Countries in the sidebar, when clicked, then a DataGrid lists Code · Name · Active with search, Add button, row click to edit modal, and a deferred-countdown Delete per the CRUD standard (no confirm dialog). Fixed-width resizable columns.
- AC-1.9 `[FE]` Given the Countries add/edit modal, when saved with an empty or non-2-letter code, then the field shows a validation message and nothing is submitted.
- AC-1.10 `[FE]` Given the Supplier create/edit form, when the Address block renders, then Country is a clearable `SearchableSelect` fed by the countries select endpoint, showing the name, storing the id.
- AC-1.11 `[FE]` Given the Supplier list and detail page, when a supplier has a country, then the country NAME shows (never the id).
- AC-1.12 `[UX]` No new motion. The Borrow modal row expansion reuses the existing `CellStockTable` expansion; the pill is static. Reduced-motion users see no difference from today.

## Phase 2 (backend, test-first)

Countries master (S1)

- AC-2.1 `[BE]` Given migration `510_countries` runs on an empty database, then table `countries` exists (id uuid, code char(2) unique case-insensitive, name, is_active, created_at, updated_at), seeded with the full ISO 3166-1 alpha-2 list (249 rows), and `MY` is `Malaysia`.
- AC-2.2 `[BE]` Given the model, then `Country.__company_shared__ = True` and a scoped (non-admin) user listing countries sees all seeded rows.
- AC-2.3 `[BE]` `GET /api/v1/master-data/countries` (page, limit, query on code or name, sort) requires `master_data.countries.view`; `GET .../countries/select` returns `{id, code, name}` for active rows; `POST` requires `.add`, `PUT /{id}` `.edit`, `DELETE /{id}` `.delete`. Denied role gets 403 on each.
- AC-2.4 `[BE]` Given a country referenced by at least one supplier, when DELETE is called, then 409 with a message naming the count of suppliers, and the row stays.
- AC-2.5 `[BE]` Given a duplicate code (any case), when POST or PUT is called, then 409 and no row is written.
- AC-2.6 `[BE]` Given the permission registry, then the four `master_data.countries.*` slugs are registered and the migration grants them to every role that holds `master_data.units_of_measure.<same action>` today (derived, not typed).
- AC-2.7 `[BE]` Given the deferred record-action registry, then `country.delete` is registered with the hard-delete window and the same 409 guard as AC-2.4.

Supplier country (S2)

- AC-2.8 `[BE]` Given migration `511_supplier_country_id`, then `suppliers.country_id` (uuid FK countries, ON DELETE RESTRICT, nullable, indexed) exists and the free-text `suppliers.country` column is dropped. The supplier list-query metadata field `country` now reads `country.name`.
- AC-2.9 `[BE]` Supplier create / update accept `country_id`; supplier responses (list, detail, select) carry `country_id`, `country_code`, `country_name`. Unknown `country_id` yields 422.
- AC-2.10 `[BE]` Given the supplier master ingest passthrough, when a row carries a country as a name or a 2-letter code, then it resolves to `country_id` case-insensitively; an unresolvable value is reported as a row warning and the field is left null (the row still imports).
- AC-2.11 `[BE]` `scripts/backfill_supplier_country.py`: dry-run by default prints the suppliers whose name matches `SDN BHD` / `SDN. BHD.` / `(KL)` / `MALAYSIA` (case-insensitive, whitespace-tolerant) and currently have no country; `--apply` sets them to `MY`; never overwrites a non-null country; idempotent on a second run (0 changes).

Origin resolution + confirm routing (S3)

- AC-2.12 `[BE]` `supply_origin.buy_origin_by_product(db, product_ids) -> dict[product_id, "local" | "overseas"]`: the supplier is the primary `product_suppliers` link, else the newest PO supplier (`issue_date desc nulls last, created_at desc`, same rule as the order sheet), else none. `local` iff that supplier's country code equals `HOME_COUNTRY_CODE` (`MY`, module constant beside `BASE_CURRENCY`). No supplier, or a supplier with no country, is `overseas`.
- AC-2.13 `[BE]` Given a product whose primary link is a Malaysian supplier but whose newest PO is from a Chinese supplier, then origin is `local` (primary link wins).
- AC-2.14 `[BE]` Given the board endpoint, then every contribution and every `SupplyLine` carries `buy_origin`, computed once per product per request (one query for the whole board, not per line).
- AC-2.15 `[BE]` Given confirm on a Buy line whose product is `local`, then the decision revision stores the Buy (quantity and reason as today), the confirm result counts it as a Buy, and NO `order_inquiry_rows` row is created and no `OrderInquiry` header is minted for it.
- AC-2.16 `[BE]` Given confirm on a mixed order (one local Buy, one overseas Buy), then exactly one OI row is raised, for the overseas line, under one header.
- AC-2.17 `[BE]` Given a line that already has a raised OI row from an earlier revision and whose product is now `local`, when the order is confirmed again, then that row is neither re-raised nor cancelled (a local line is passed through `buy_lines` flagged `origin: "local"` and skipped, never treated as dropped). Test asserts the row's verb and state are unchanged.
- AC-2.18 `[BE]` Given a carried line (decided in an earlier revision, untouched now) whose product is `local`, then the same skip applies.
- AC-2.19 `[BE]` Given SCM demand (`app/services/scm/demand.py`), then a confirmed local Buy contributes nothing, because it has no OI row (regression test: product-grain plan for that product shows no project demand from that line).

Borrow modal data (S4)

- AC-2.20 `[BE]` Each `borrow_candidates[]` entry on the board contribution and on `SupplyLine` carries a `location` object in `BoardCellLocation` shape (same builder as the Location table, same figures: on_hand, so_qty, spo_qty, available, available_for_project, po_qty, taken, where), so the modal renders it without client-side arithmetic. Existing fields stay for the After-borrow sentence.
- AC-2.21 `[BE]` `GET /fulfilment-planning/stock-detail?product_id=&warehouse_id=&line_ids=` for a donor warehouse outside the line's group returns that warehouse's ledger with `is_this_line` set on the current line's rows (existing endpoint, new caller; test the cross-group case).

Copy (S5)

- AC-2.22 `[BE]` Board and supply payloads keep `reason` on option rows (trail and tests unchanged); the FE simply stops rendering it (AC-1.2). No backend change in S5.

## Phase 3 (verification)

- AC-3.1 `[E2E]` agent-browser, sidebar navigation from `/`: Master Data › Countries lists 249 rows, search `mala` finds Malaysia, edit renames and reverts, delete on a fresh test row completes after the countdown, delete on Malaysia is refused with the supplier count.
- AC-3.2 `[E2E]` Procurement › Suppliers › edit MOCHA SDN BHD: Country select shows Malaysia after the backfill dry-run + apply on the lane DB; list column shows Malaysia.
- AC-3.3 `[E2E]` Fulfilment planning, List view, an order with a local product (a Mocha-sourced code) and an overseas product: local row shows `Buy N Local`, overseas shows `Buy N`; expanded OPTIONS shows no reason sub-lines. Confirm both. Order Inquiry worklist shows the overseas row only; the decision trail shows both Buys.
- AC-3.4 `[E2E]` Add a borrow on a line with candidates: Source table has the Location-table columns, radio picks a source, expanding DC1-IR (or the recommended row) lists its S/O rows with `This line` on the current line, Add the borrow succeeds. Checked at 1280px and 375px.
- AC-3.5 `[T]` pytest: `tests/test_countries.py`, `tests/scm/test_supply_origin.py`, `tests/scm/test_confirm_local_buy_no_oi.py`, `tests/test_supplier_country.py`, `tests/scm/test_backfill_supplier_country.py`, `tests/scm/test_borrow_candidate_location.py`. vitest: `CountryList`, `CountryForm`, `SupplierForm` country select, `BorrowAddDialog` table + expansion, `FulfilmentBoardListView` pill, `BoardLadderOptionsTable` no reason.

## Definition of Done

1. Mock swapped for real: pill, Countries page, supplier select, borrow table all read live data on the lane stack.
2. Backfill script run on the lane DB (prod copy); owner runs it on prod after deploy.
3. New permission slugs granted by migration to the derived role set; a non-admin with Master Data rights reaches the page.
4. `country_id` / `country_code` / `country_name` reach the FE on supplier list, detail and select (asserted in tests, not assumed).
5. Verified by sidebar clicks at 375px and 1280px, evidence under `documentation/plans/scm/evidence/local-supplier-oi-routing/`.

## Out of scope

Customer and user country fields; OI worklist changes; a Location table in the List view expanded row; reorder planning reading local Buys; supplier lead time by country.
