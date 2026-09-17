# UAC: local-supplier Buy routing behind a system setting

Plan: `PLAN-local-buy-routing-toggle.md`
Owner ruling: 18 Sep 2026

## Setting

- AC-1 `system_settings.local_buy_routing_enabled` exists, boolean, not null, server default
  false. Migration `lbrt_0001_local_buy_toggle` adds it; downgrade drops it.
- AC-2 GET `/api/v1/user-management/settings` returns `local_buy_routing_enabled` in the
  settings block, from BOTH manual builders (row present, row absent). Default false.
- AC-3 POST `/api/v1/user-management/settings/general` with `local_buy_routing_enabled`
  saves it and the next GET reads it back.
- AC-4 The general settings page shows one Switch with the accessible name
  `Local supplier Buys skip Order Inquiries`, reflecting the stored value, and Save sends the
  field. No description text under it.

## Off (the default)

- AC-5 `buy_origin_by_product` answers `None` for every id asked and runs no query against
  `product_suppliers` or `purchase_order_lines`.
- AC-6 Board contributions, sheet lines and confirm payloads carry `buy_origin: null` for a
  product whose primary supplier's country is MY.
- AC-7 No `Local` badge renders anywhere on the board: List view Suggested / Decided cells,
  OPTIONS Buy row, cell breakdown dialog.
- AC-8 Confirming a Buy on a MY-supplier product mints the Order Inquiry header (when it is
  the only Buy) and raises one `ORDER` row in `raised`, counted in `created`.
- AC-9 A line confirmed as a local Buy while the setting was on (no OI row) is raised on the
  next confirm after the setting is turned off, including when it is carried unchanged.
- AC-10 SCM reorder demand counts that Buy.
- AC-11 The board statement-count bound (40) still holds with the one added settings read.

## On

- AC-12 With the setting on, every assertion in `tests/scm/test_confirm_local_buy_no_oi.py`
  and `tests/scm/test_supply_origin.py` still holds: local Buys skip, pill renders, prior
  raised rows on a now-local line are left alone.

## Untouched

- AC-13 Countries master, supplier country FK, Borrow modal Location table: no diff.
- AC-14 No OI-service or board-component code deleted. The toggle is the only gate.

## Docs

- AC-15 User guide `local-buy-and-borrow-source.md` describes the rule as a setting, off by
  default, with no pill and every Buy reaching Order Inquiries while it is off.
- AC-16 `PLAN-local-supplier-oi-routing.md` Status line reads implemented and it is archived
  with its UAC and evidence folder under `documentation/plans/_archive/scm/`.

## Browser pass (agent-browser, via sidebar from `/`)

- AC-B1 Settings, General: the Switch is present, off, and survives a Save + reload.
- AC-B2 Fulfilment Planning, List view, a MY-supplier Buy line: no `Local` badge in
  Suggested or in the expanded OPTIONS table.
- AC-B3 Confirm that line: Order Inquiries shows the row under the SO's header.
- AC-B4 Flip the Switch on, reload the board: the `Local` badge is back on that line.
