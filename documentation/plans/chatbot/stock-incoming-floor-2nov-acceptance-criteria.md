# UAC: STOCK-INCOMING-FLOOR

Plan: `PLAN-stock-incoming-floor-2nov.md`. Fake codes and dates only. "Dealer" = a contact on the
"Availability only" stock policy. Today is 02/11/2026 (MYT) in every example.

## Fix B: one shared incoming answer (owner 2 Nov 2026; card Q1 a, Q2 a, Q3 a, Q4, Q5 a)

- **AC-SIF1** The production case. A dealer with ETA buffer ON asks a product with no stock, with a
  quantity. It has shipments promised 20/10/2026 and 23/10/2026, and its category buffer is 14 days.
  The stock check answers `incoming` with eta `03/11/2026, 06/11/2026`. The reply reads
  "No stock, ETA 03/11/2026, 06/11/2026." and never "No stock and no incoming".
- **AC-SIF2** The same dealer asks the product's ETA (`/incoming-stock/by-product`). The dealer view
  lists exactly `["03/11/2026", "06/11/2026"]`, the stock check's dates in the same order.
- **AC-SIF3** A told date equal to today is plain `02/11/2026`, with no marker.
- **AC-SIF4** A told date before today carries the one marker: promised 01/10 + 14 days reads
  `15/10/2026 (delayed)`. It is still `incoming` on the stock check and still listed by the ETA ask, in
  date order with the others (`15/10/2026 (delayed), 03/11/2026`).
- **AC-SIF5** A dealer with the buffer OFF is told the promised dates: `20/10/2026 (delayed), 10/11/2026`,
  never the padded 03/11.
- **AC-SIF6** A code carried by two companies is padded by the larger of their offsets, and its dates
  are the union of both companies' shipments, on both paths.
- **AC-SIF7** Q1 (a): a still-incoming shipment WITHOUT a packing list is told on both paths. The
  packing list file still goes only with a stock check answer, only when the contact's toggle is on,
  and is the file of the earliest still-incoming shipment that has one.
- **AC-SIF8** Q2 (a): a shipment with ETA 13/09/2026 revised to 05/11/2026 is told as `05/11/2026` on
  both paths, never `13/09/2026`. This holds even when the contact is not granted the "ETA delay" field.
- **AC-SIF9** Two shipments that are told the same date print that date once.
- **AC-SIF10** Q5 (a): a code whose only still-incoming shipment has no ETA reads
  "No stock and no incoming" on the stock check and "No ETA" on the ETA ask (unchanged).
- **AC-SIF11** Q4: the marker is one constant. Its ms text is `(lewat)` and its zh text is `（延迟）`. A
  dealer replying in ms or zh reads the dates with the marker translated.
- **AC-SIF12** Unchanged: a windowed ETA ask, `/shipments`, staff and non-dealer contacts, the
  `in_stock` and `too_big` answers, and every sentence other than the date list.
