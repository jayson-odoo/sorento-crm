# UAC OI-PO-LINK B (14 Nov)

- B-1 Opening the Link PO popup (Order Inquiry `POST .../order-inquiries/po-link/options` and Stock Debt
  `GET .../stock-debt/snapshots/{id}/rows/{row_id}/po-link/options`) makes NO call to the Shared Service
  (no `write-capabilities`, nothing else); it reads only CRM tables.
- B-2 The options answer keeps `capabilities` with each action `{enabled: true, reason: null}`; nothing in
  the popup is greyed by a capability feed.
- B-3 A Save that the Shared Service refuses with VENDOR_UNSUPPORTED / WRITE_DISABLED / WRITE_NOT_ALLOWED
  shows its plain reason and Try again (existing wording, `poLinkWording.ts`); nothing changed in AutoCount.
- B-4 Order Inquiry options for ticked rows where some are not in AutoCount: 200; each such row comes back
  in `skipped` with the CRM copy's `so_number`, `line_no`, `location_code`, `delivery_date`, `open_qty`
  where the row has a CRM sales order line (null otherwise), plus `inquiry_no`, `item_code`, `reason`.
  All ticked rows not in AutoCount (none in AutoCount) still answer 422 as before.
- B-5 In the popup every ticked line is a row: an AutoCount line as today; a "Not in AutoCount yet" line as
  its own row with that text in the PO column, no tick box, no PO picker, no qty box, not counted in
  "Save (n)". No separate note under the grid for it.
- B-6 Stock Debt Decide behaves as before apart from B-1/B-2.
