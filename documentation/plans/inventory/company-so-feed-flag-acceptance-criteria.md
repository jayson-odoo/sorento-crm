# UAC: per-company "AutoCount sales orders connected" flag

Plan: `PLAN-company-so-feed-flag.md`.

- **AC-1 [BE]** `companies.so_feed_live` exists, boolean, NOT NULL, default true. Migration
  495 sets it false for `code = 'MOCHA'` only; downgrade drops the column.
- **AC-2 [BE]** `GET /api/v1/inventory/stock/balance?include_sellable=true`: a detailed row
  whose company has `so_feed_live = false` carries NO `open_so_qty` and NO `sellable` key. A
  row whose company has it true carries both, with the same numbers as before this change.
- **AC-3 [BE]** Compact mode under `include_sellable=true`: a `stock_summary` entry for a
  product of a no-feed company carries no `open_so_qty` / `sellable`, and its location
  lines carry no `open_so_qty`. A feed-on company's entry and locations are unchanged.
- **AC-4 [BE]** Detailed mode's synthesised per-product `stock_summary` (rows without a
  backend summary) omits `open_so_qty` / `sellable` on no-feed products; feed-on products
  keep them.
- **AC-5 [BE]** Without `include_sellable` the response is byte-identical to before (no new
  keys anywhere), regardless of the flag.
- **AC-6 [BE]** Companies API: `POST /system/companies` accepts `so_feed_live` (default true
  when omitted), `PUT` updates it, `GET` list and detail serialise it.
- **AC-7 [MCP]** Presenter: a stock row with no `sellable` key renders no `Outstanding`
  field; a row with `sellable` renders it (existing behaviour, pinned).
- **AC-8 [FE]** Companies page > Add / Edit dialog shows a switch labelled "AutoCount sales
  orders connected" above "Active"; create defaults on; edit reflects the row; saving sends
  `so_feed_live`. No explanatory copy in the UI.
- **AC-9 [FE]** Companies list shows an "SO feed" column (Yes / No) with an explicit column
  size; usable at 375px and 1280px.
- **AC-10 [browser]** Via sidebar from `/`: System Management > Companies > edit Mocha >
  switch off > Save > row shows No; reopen, switch is off. Edit Sorento: switch is on.
- **AC-11 [live]** With Mocha off and Sorento on, the MCP tool `crm_inventory_stock_balance_list`
  with `include_sellable=true` for `MWC7625-SH-S10` returns Sorento rows with Outstanding and
  Mocha rows without.
