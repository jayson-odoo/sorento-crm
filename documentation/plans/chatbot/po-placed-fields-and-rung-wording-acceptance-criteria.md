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
