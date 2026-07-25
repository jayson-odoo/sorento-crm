# A won Project PO lives in its own table, never in `purchase_orders`

Both the SCM domain and the Project Sales domain call their document a "PO", but they point
in opposite directions: `purchase_orders` is the **outgoing** supply PO we issue to a
supplier, while a Project PO is the **incoming** order a main contractor or trading house
places with us. They are stored separately in `project_purchase_orders`. The UI says "PO" for
both, because that is the client's word — the tables must never merge.

This is not a naming preference. `purchase_orders` is wired into SCM's supply maths:

- `purchase_order_service._is_on_order()` treats any PO with `qty_ordered > qty_received` as
  **incoming supply**. A won project PO for 733 units would tell the reorder engine 733 units
  are inbound — when we just sold them — and suppress a purchase we actually need.
- `decision_service._draft_po_for_supplier()` selects the unassigned draft via
  `supplier_id IS NULL`, which is exactly the shape of a customer PO. The SCM engine could
  append supplier recommendation lines onto a customer's order.

A `po_direction` discriminator column was rejected: every existing SCM query lacks that
filter, so the default behaviour would be fail-**open** — silently wrong until each call site
is found and fixed.

If project wins should ever feed SCM demand planning, that is an explicit read-model built
deliberately — not a side effect of sharing a table.
