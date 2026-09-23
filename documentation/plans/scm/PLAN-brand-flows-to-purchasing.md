# PLAN: a brand can be marked as not flowing to purchasing; its Buys skip Order Inquiries

Status: implemented, awaiting review (23 Sep 2026). Track: full (migration + new field on a master-data form), small in size.
UAC: `brand-flows-to-purchasing-acceptance-criteria.md`
Domain: scm (reuses the local-buy routing seam), touches master data (brands)
Related: `PLAN-local-buy-routing-toggle.md` (built, 18 Sep 2026), `_archive/scm/PLAN-local-supplier-oi-routing.md` (#814)

## Why

Owner, 22 Sep 2026: some brands are bought locally by CS themselves and must never reach
purchasing - TP Enterprise is the named one. The supplier-country rule from #814 was the
wrong key for this: Mocha is a local supplier AND its items do sometimes go to purchasing,
which is why the whole rule went behind a global toggle (off) on 18 Sep. The brand is the
right key. Default is "flows to purchasing" so nothing changes until an admin flips a brand.

Rulings (owner, 22 Sep 2026):

- R4 The brand flag is independent of `system_settings.local_buy_routing_enabled`. That
  toggle keeps gating the supplier-country path only, and stays off.
- R5 A brand-blocked Buy shows the existing `Local` pill. No new pill text.
- R6 The 18 Sep complaint (SO314594, TPE-9204 skipping OI) was NOT about TP Enterprise
  skipping; it was the supplier-country rule catching lines that must flow. TP Enterprise
  items are meant to skip.
- R7 Mocha brand: flows to purchasing (default true). Nothing to set.

## Measured facts (primary checkout, `origin/main` 2280975f9, 22 Sep 2026)

| fact | where |
| --- | --- |
| Origin resolver, one SQL statement when the toggle is on, none when off; returns `{pid: "local" \| "overseas" \| None}` | `app/services/scm/supply_origin.py:27-93` `buy_origin_by_product` |
| Every caller reads `origin_by_product.get(pid, "overseas")` and threads it as `entry["origin"]` / `buy_origin` | `project_supply_service.py:1241-1272,4334-4382,6453-6456`; `project_fulfilment_board_service.py:633,726-728,5018-5020` |
| Header-mint gate `origin != "local"`; row-loop skip `origin == "local"` (retires a raised row instead of raising) | `app/services/project_order_inquiry_service.py:857-861,914+` |
| Schema field `buy_origin: Optional[Literal["local","overseas"]]` | `schemas/project_board.py:730`, `schemas/project_supply.py:226` |
| FE `Local` pill wherever `buy_origin === 'local'` | `FulfilmentBoardListView.tsx:478,531`, `BoardCellBreakdownDialog.tsx:797`, `BoardLadderOptionsTable.tsx:93` |
| Brand model, company-scoped, `is_active` boolean precedent with server default | `app/models/product.py:79-111` |
| Brand schemas `BrandBase / BrandCreate / BrandUpdate / BrandResponse` | `app/schemas/product.py:43-78` |
| Brand routes | `app/api/v1/master_data/brands.py` (list 79, select 110, get 147, create 164, update 181, delete 199) |
| FE brand CRUD: types, zod schema, form, dialog, table | `app/(protected)/master-data-management/brands/{types/brand.types.ts, forms/brand-schema.ts, components/BrandForm.tsx, BrandFormDialog.tsx, BrandTable.tsx}` |
| `Product.brand_id` FK -> `brands.id`, indexed | `app/models/product.py:177,240,272` |
| Board statement-count bound 40 | `tests/test_ladder_v5_edges.py::test_a_board_of_76_lines_does_not_scale_its_query_count_with_the_line_count` |
| Existing tests on the seam | `tests/scm/test_supply_origin.py`, `tests/scm/test_confirm_local_buy_no_oi.py`, `tests/scm/test_local_buy_routing_toggle.py` |
| Alembic head on main | `spec_vocab_close_couple` |

## Design

**One column, one seam.**

1. `brands.flows_to_purchasing` Boolean, not null, server default true. Migration
   `bftp_0001_flows_to_purchasing` (shortened from the plan's original
   `bftp_0001_brand_flows_to_purchasing` - that name is 35 characters, over the 32-char
   revision-id limit, `LESSONS-LEARNT.md`), down_revision `525_committed_v_orderback`
   (the worktree's actual `alembic heads` at implementation time, not the plan's
   `spec_vocab_close_couple` - a later migration landed on top of it before this lane
   started; re-parent again at the pre-PR gate if main has moved further).
   Downgrade drops it.
2. `BrandBase.flows_to_purchasing: bool = True`, `BrandUpdate.flows_to_purchasing:
   Optional[bool]`, `BrandResponse` inherits it. Create/update routes pass it through as
   they do `is_active`. `BrandSimple` (`schemas/product.py:292`) is untouched: the select
   endpoint does not need it.
3. `buy_origin_by_product` gains a brand read BEFORE the toggle gate:

   ```
   blocked = {pid for pid in ids if product.brand.flows_to_purchasing is false}
       # ONE statement: products JOIN brands WHERE p.id = ANY(:pids)
       #                AND b.flows_to_purchasing = false, company-scoped on products
   if toggle off:  return {pid: "local" if pid in blocked else None}
   if toggle on:   supplier-country map as today, then "local" for every blocked pid
   ```

   A brand-blocked product is `"local"` whatever its supplier's country. Nothing else in
   the function moves. With the toggle off this adds one statement per board build where
   there were none; the bound the existing pin asserts is re-measured and bumped by one
   (measured 46 -> 47 at implementation time, not the plan's stale "40" - several other
   lanes raised it since that figure was written; see the pin's own comment history in
   `tests/test_ladder_v5_edges.py`).

   **No degradation (owner, 22 Sep):** the brand read is ONE statement for the whole
   call (`WHERE p.id = ANY(:pids)`), never per line, joined over `products.id` (PK) and
   `products.brand_id -> brands.id` (`ix_products_brand_id` + PK), so it is an index
   lookup per product id. It runs once per board build / sheet build / confirm, in the
   same place the toggle read already runs. It is skipped entirely when `ids` is empty.
   No caching layer, no new table, no per-line branching downstream. The coder asserts
   the statement count in `tests/scm/test_supply_origin.py` (Red 1a: N products, toggle
   off -> exactly 2 statements: the settings read and the brand read; toggle on -> 3).
4. Nothing downstream changes: the OI header gate, the row-loop skip, the carried-entry
   handling, the `buy_origin` payload field and the FE `Local` pill all read the same
   `"local"` value they read today (R5).
5. FE brand form: one `Switch`, accessible name `Flows to purchasing`, default on, placed
   under `Active`. Brand table: one narrow column `Purchasing` showing `Yes` / `No` so an
   admin can see which brands are blocked without opening each. No explanation text on
   screen (guide carries it).

Lines already confirmed as Buys on a brand flipped to "no" keep their raised OI rows until
their next re-confirm, where the row-loop skip retires them (existing #814 decision 9
behaviour). No backfill.

## Not in scope

- Per-product override. One brand, one answer. Trigger for revisiting: a named product
  under a blocked brand that must flow.
- Renaming the `Local` pill (R5).
- Changing `local_buy_routing_enabled` or its supplier-country chain (R4).
- Reorder-plan demand: a brand-blocked Buy is excluded the same way a local Buy was under
  #814 (it never becomes an OI row), no separate rule.
- `/master-data-management/brands/new` and `/brands/<id>/edit` render `BrandForm` but
  nothing links to them; the edit route's zod schema also rejects brand codes
  containing spaces (real data has them). Cleanup trigger: remove or reconcile both
  routes.

## Tests

pytest:

- `tests/scm/test_supply_origin.py` (extend): Red 1 brand `flows_to_purchasing=false`,
  toggle off -> `"local"` for that product, `None` for a product on a default brand. Red 2
  toggle on, MY supplier, brand blocked -> `"local"`; overseas supplier, brand blocked ->
  `"local"`; MY supplier, brand default -> `"local"` (toggle behaviour unchanged). Red 3
  product with no brand -> unchanged answer for the toggle state.
- `tests/scm/test_confirm_local_buy_no_oi.py` (extend, toggle OFF variant): Red 4 confirm
  a Buy on a blocked-brand product -> no OI header when it is the only Buy; Red 5 mixed
  order, blocked-brand Buy plus a default-brand Buy -> header minted, one `ORDER` row for
  the default-brand line only; Red 6 a raised row on a line whose brand is flipped to
  blocked is retired on the next confirm.
- `tests/test_ladder_v5_edges.py` statement-count pin: still under 40 (existing test, run).
- Brand route: Red 7 POST without the field -> `flows_to_purchasing: true` in the response;
  PUT `{flows_to_purchasing: false}` -> persisted, GET reads it back.
- Migration: Red 8 the alembic upgrade/downgrade round trip on the column (existing
  migration-test pattern in `tests/`).

vitest, brands feature:

- Red 9 `BrandForm` renders the `Flows to purchasing` switch on by default for a new brand,
  and submits `flows_to_purchasing: false` after a toggle.
- Red 10 `BrandTable` shows `No` in the Purchasing column for a blocked brand.

## Verification

Browser (agent-browser, via sidebar): Master Data > Brands, edit TP Enterprise, switch off
Flows to purchasing, save; the table shows `No`. Fulfilment planning board on an order with
a TP Enterprise Buy: the Buy carries the `Local` pill; Confirm; Order Inquiries for that
order lists no row for the line. A Mocha-brand Buy on the same board has no pill and its
row is raised.

## Guide

`documentation/user-guides/supply-chain/local-buy-and-borrow-source.md`: the paragraph on
the local toggle gains the brand rule: a brand marked "Flows to purchasing: No" on the
Brands page has its Buys handled by CS locally, shown with the `Local` pill, and never
raised as an Order Inquiry. Brands guide: one line for the new switch.
