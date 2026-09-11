# UAC: SPO Allocations list shows and searches the container number

Plan: `PLAN-spo-list-container-number.md`. Page: Procurement > SPO Allocations.

- AC-1 Each header row carries `containers`: one `{container_number, shipment_id}` per
  distinct container over the document's visible lines, sorted by container number, where
  the container is `coalesce(spo_allocations.container_number,
  inbound_shipments.shipping_container_number)` and `shipment_id` is the line's
  `inbound_shipment_id` (null for a raw, unlinked container).
- AC-2 A document with no container on any line returns `containers: []` and the list
  cell renders `-`.
- AC-3 Two lines on the same container yield one entry (the one carrying a shipment id
  wins); a retired line's container is not counted.
- AC-4 The list search matches the raw `spo_allocations.container_number` (unlinked
  container) as well as the linked shipment's `shipping_container_number` and
  `shipment_number` (already true). Partial, case-insensitive.
- AC-5 The Container No column header sorts server-side (`sort=containers`); documents
  with no container sort last in either direction.
- AC-6 The list shows a "Container No" column after Supplier. The cell shows the FIRST
  container only, as a link to its packing list (`/procurement-management/packing-lists/{id}`)
  when linked, plain text when not. More than one container adds a `+N` pill after it
  (never a comma list): with one extra the pill links straight to that packing list; with
  two or more the pill opens a popover listing each extra container as a packing list
  link. The cell truncates (`title` carries every container) so a narrow column clips the
  pill and widening the column reveals it. Pill and link clicks do not trigger the row
  navigation. The client export carries every container comma-joined.
- AC-7 The search box placeholder reads "Search SPO, product or container...".
- AC-8 Browser: on the dev stack, searching a real container number (e.g. `CMAU7650091`)
  returns its SPO(s) and the column shows that number; clearing the search restores the
  full list. Verified via sidebar navigation, 1280px and 375px.
