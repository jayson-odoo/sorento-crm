# UAC: SPO Allocations list shows and searches the container number

Plan: `PLAN-spo-list-container-number.md`. Page: Procurement > SPO Allocations.

- AC-1 Each header row carries `container_numbers`: the sorted, distinct, non-null set of
  `coalesce(spo_allocations.container_number, inbound_shipments.shipping_container_number)`
  over the document's visible lines.
- AC-2 A document with no container on any line returns `container_numbers: []` and the
  list cell renders `-`.
- AC-3 Two lines on the same container yield one entry; a retired line's container is
  not counted.
- AC-4 The list search matches the raw `spo_allocations.container_number` (unlinked
  container) as well as the linked shipment's `shipping_container_number` and
  `shipment_number` (already true). Partial, case-insensitive.
- AC-5 The Container No column header sorts server-side (`sort=container_numbers`);
  documents with no container sort last in either direction.
- AC-6 The list shows a "Container No" column after Supplier; several containers render
  comma-separated, truncated with a `title` tooltip carrying the full text; the client
  export carries the same joined text.
- AC-7 The search box placeholder reads "Search SPO, product or container...".
- AC-8 Browser: on the dev stack, searching a real container number (e.g. `CMAU7650091`)
  returns its SPO(s) and the column shows that number; clearing the search restores the
  full list. Verified via sidebar navigation, 1280px and 375px.
