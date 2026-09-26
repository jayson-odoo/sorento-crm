# UAC: PO placed fields and cross-domain rung wording

Plan: `PLAN-po-placed-fields-and-rung-wording.md`.

- AC-1 Presenter field order. For a row carrying every field, `_purchase_orders_placed`
  renders EXACTLY, in this order: `Company` (when present), `PO Number`, `Product Code`,
  `Ordered Qty`, `Outstanding Qty`, `PO Date`, `Location`, `Supplier`. No `Source` and no
  `Expected Date` field, even when the raw row still carries `kind` and `expected_date`.
- AC-2 Top-level kind. When a row carries `kind`, the rendered item carries `kind` as a
  TOP-LEVEL key (sibling of `title`/`fields`/`flags`), not a rendered field; a row with no
  `kind` produces an item with no top-level `kind` key at all (never `None`).
- AC-3 Field omission. `Ordered Qty` and `Location` are omitted from the rendered fields
  when the row has no `ordered_qty` / `location` value (same rule every other empty field
  already follows).
- AC-4 Rung structured block. The cross-domain PO rung renders one field per line per row -
  `Product Code:`, `Ordered:`, `Outstanding:`, `PO date:`, `Location:` - with no
  per-document heading and no "pcs".
- AC-5 Rung null omission. A null or empty `ordered_qty`, `po_date` or `location` omits
  that line entirely (never a placeholder); `Product Code:` and `Outstanding:` always
  print regardless of what else is missing.
- AC-6 Rung row separation. Two or more rows for the same code are separated by exactly ONE
  blank line between their blocks - not zero, not two.
- AC-7 Rung header selection. A rung answer made up entirely of `kind = "spo"` rows still
  reads "but stock is on order from the supplier"; any `kind = "po"` row in the set reads
  "but PO is placed". `kind` is read ONLY from the item's own top-level key; a row with no
  top-level `kind` is treated as a PO row.
- AC-8 Backend row keys. `purchase_orders_placed_rows` adds `ordered_qty` and `location` to
  every row. PO side: `ordered_qty` is the line's `qty_ordered`; `location` is the line's
  warehouse code, None when the line has no warehouse. SPO side: `ordered_qty` is the
  allocation's `allocated_quantity`; `location` is the allocation's warehouse code, else
  the book's raw `location_code`, else None. Every other existing row key is unchanged.
- AC-9 Outstanding on the cross-domain stock block. `crossdomain_probe_args` stamps
  `"access": {"attributes": [...]}` on the first probe's args when `granted` is a
  non-empty list/tuple/set, omitted entirely otherwise; `run_crossdomain` passes its own
  `granted` through unchanged. `entity_ids_transformer` already reads it, so a granted
  contact's cross-domain stock block carries `open_so_qty`/Outstanding like a direct ask.
- AC-10 Zero-everywhere climbs both directions. Stock-origin: a requested code whose
  primary stock reply's own rows are all `Quantity On Hand: 0` is flagged `zero: True` in
  `crossdomain_zeroset`'s `missing` and probes the next domain like a genuine miss.
  Incoming-origin: a code whose cross-probed STOCK rows are all 0 renders those rows as
  today AND climbs to the next rung with the same `zero: True` flag. Either direction, a
  further ladder rung (e.g. `purchase_order`) still runs and its own answer or non-answer
  is worded per AC-11.
- AC-11 The zero wording set. `_xdBlock.zero_codes` names the zero-flagged subset of
  `nothing_codes`. The rendered sentence set, exact:
  - stock-origin, rung answers: `Stock is 0 at every location and no incoming for X,
    {header}:` + the rung's block.
  - stock-origin, rung answers nothing: `Stock is 0 at every location, no incoming and
    nothing on order for X.`
  - incoming-origin, rung answers: `No incoming and stock is 0 at every location for X,
    {header}:` + the rung's block.
  - incoming-origin, rung answers nothing: `No incoming, stock is 0 at every location and
    nothing on order for X.`
  A plain group and a zero group present together each render their own paragraph(s),
  plain first, joined the same way the existing plain-only case already joins multiple
  paragraphs.
- AC-12 No false climb. A requested code with at least one row reading a non-zero quantity
  is genuinely "found" - unchanged from today: no `zero` flag, no cross-domain probe, no
  wording change, `only_other`/`nothing` behave exactly as before this ruling.
- AC-13 First-probe zero note, and stock-visibility parity. Before any further rung runs
  (no ladder configured, or the rung's grant is missing), the FIRST probe's own
  `nothing_note` already carries the zero wording for a zero-flagged code: stock-origin
  `Stock is 0 at every location and no incoming for X.`; incoming-origin `No incoming and
  stock is 0 at every location for X.` A plain code keeps today's `No {primary} and no
  {other} for X.` This same code never earns the AC-820 "no {primary} for X" only-other
  line either, at this stage or after a rung runs - the zero sentence already says it.
  Availability-mode (no quantity field ever emitted) and `hide_zero_locations=true`
  (locations suppressed once nothing is left) contacts never reach a zero classification
  at all - a code with no rows at all still reaches the PO rung through the EXISTING
  no-rows path, with the SAME plain PO block wording, so the customer-visible outcome is
  consistent across all three stock-visibility configurations (full detail, compact,
  availability/hidden-zero).
