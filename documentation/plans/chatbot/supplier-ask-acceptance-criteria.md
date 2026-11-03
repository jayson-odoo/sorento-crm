# UAC: SUPPLIER-ASK

- AC-1: A staff "outstanding for <supplier, native-script short name>" resolves the supplier and lists
  that supplier's open POs (not fully received) only.
- AC-2: The same with the supplier's English name, its code, and a one-letter typo of the name.
- AC-3: `GET /procurement/purchase-orders/placed?supplier_ids=<id>` returns only that supplier's rows; under a
  `contact_id` without the `purchase_orders.supplier` reveal it is a 403.
- AC-4: A dealer/customer asker, or staff without the `purchase_orders.supplier` reveal, never gets a
  supplier resolved or `supplier_ids` sent (PO data gates unchanged).
- AC-5: Prompt changes are new UNLABELLED versions; no production label moves in code.
