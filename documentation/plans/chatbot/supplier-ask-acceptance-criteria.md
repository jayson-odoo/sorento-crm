# UAC: SUPPLIER-ASK

- AC-1: A staff "outstanding for <supplier, native-script short name>" resolves the supplier and lists
  that supplier's open POs (not fully received) only.
- AC-2: The same with the supplier's English name, its code, and a one-letter typo of the name.
- AC-3: `GET /procurement/purchase-orders/placed?supplier_id=<id>` returns only that supplier's rows.
- AC-4: A dealer/customer asker never gets the supplier kind resolved or PO data (gates unchanged).
