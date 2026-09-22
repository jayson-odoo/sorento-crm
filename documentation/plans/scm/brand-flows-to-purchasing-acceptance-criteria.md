# UAC: brand "Flows to purchasing"

Plan: `PLAN-brand-flows-to-purchasing.md`
Owner rulings: 22 Sep 2026, R4 to R7

## Column and API

- AC-1 `brands.flows_to_purchasing` exists, boolean, not null, server default true.
  Migration `bftp_0001_brand_flows_to_purchasing` adds it; downgrade drops it. Every
  existing brand reads true after upgrade.
- AC-2 POST `/api/v1/master-data/brands` without the field creates a brand with
  `flows_to_purchasing: true`; with `false` it stores false. Response carries the field.
- AC-3 PUT `/api/v1/master-data/brands/{id}` with `{ "flows_to_purchasing": false }`
  persists it; GET list and GET by id read it back. PUT without the field leaves it alone.
- AC-4 `GET /brands/select` is unchanged (no new field required there).

## Resolver (`buy_origin_by_product`)

- AC-5 Toggle OFF (default): a product whose brand has `flows_to_purchasing = false`
  answers `"local"`; a product on a default brand answers `None`; a product with no brand
  answers `None`.
- AC-6 Toggle ON: a blocked-brand product answers `"local"` regardless of its supplier's
  country; a default-brand product answers by supplier country exactly as today
  (`tests/scm/test_supply_origin.py` still passes unchanged).
- AC-7 The brand read is one statement for the whole call. The board statement-count pin
  (`test_ladder_v5_edges.py`, bound 40) still holds with the toggle off.
- AC-8 The brand read is scoped to the caller's company through the products predicate.

## Confirm and Order Inquiries (toggle OFF)

- AC-9 Confirming a Buy on a blocked-brand product mints NO Order Inquiry header when it is
  the order's only Buy, and the line has no `ORDER` row.
- AC-10 Mixed order: one blocked-brand Buy and one default-brand Buy -> the header is minted
  and exactly one `ORDER` row is raised, for the default-brand line.
- AC-11 A line with a raised `ORDER` row whose brand is later set to blocked has that row
  retired (not `raised`) on the next confirm, and no fresh row raised.
- AC-12 A blocked-brand Buy does not count toward SCM reorder demand (it never became an OI
  row), same as a local Buy under #814.
- AC-13 Board contributions, sheet lines and confirm payloads carry `buy_origin: "local"`
  for a blocked-brand product; the `Local` pill renders in the List view Suggested /
  Decided cells, the OPTIONS Buy row and the cell breakdown dialog (R5, existing pill).

## Brands screen

- AC-14 Brand form (create and edit) shows one `Switch` with the accessible name
  `Flows to purchasing`, on by default for a new brand, reflecting the stored value on
  edit. No description text under it.
- AC-15 Saving with the switch off sends `flows_to_purchasing: false`.
- AC-16 Brand table shows a `Purchasing` column reading `Yes` / `No`.
- AC-17 The form and the table stay usable and non-clipped at 375px and 1280px.

## Browser (agent-browser, via sidebar)

- AC-E1 Master Data > Brands, edit TP Enterprise, switch off, save: table reads `No`.
- AC-E2 Fulfilment planning board for an order with a TP Enterprise Buy and a Mocha Buy:
  the TP line shows `Local`, the Mocha line does not. Confirm. Order Inquiries for the
  order lists the Mocha row raised and no TP row.
- AC-E3 General Settings `Local supplier Buys skip Order Inquiries` is still off and
  unaffected.
