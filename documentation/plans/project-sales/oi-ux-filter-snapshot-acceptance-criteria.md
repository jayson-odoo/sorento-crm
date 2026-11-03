# UAC: OI-UX-FILTER-SNAPSHOT

- AC-1: On an OI detail page, the lines grid's search, filters and sort are held in the URL.
- AC-2: Pressing next/previous OI keeps those query params, so the next OI's lines open with the
  same search, filters and sort.
- AC-3: Reloading an OI detail page with those params restores the same lines view.
- AC-4: The Stock Debt snapshot drill names each OI group with its number plus the customer and
  project (`CUSTOMER (PROJECT) / project code`).
- AC-5: Each sales order line in the snapshot drill shows the same customer / project label.
- AC-6: A missing customer or project prints a dash in its place, never an id.
