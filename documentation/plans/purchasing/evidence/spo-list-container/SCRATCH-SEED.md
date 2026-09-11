# Scratch seed - AC-8 step 4 (multi-container pill), reversible

DB: `sorento_ai_automation_0907` (same `DATABASE_URL` as the lane backend `.env`), local Postgres.
Purpose: the two named multi-container SPOs measured in the plan
(`SPO-2026/07-0026`, `SPO-2026/08-0002`, `SPO-2026/08-0015`) turn out to carry their second
container under a DIFFERENT company (`Mocha`, `38db4f20-ab6b-4bd0-a6fc-3a6728f0dee2`) than the
one the browser session is logged into (`Sorento`, `00000000-0000-0000-0000-000000000001`), so
none of them shows a "+1" pill under the scoped view. This scratch seed adds one extra,
same-company line to the real `SPO-2026/09-0030` (already used in step 2, container
`CMAU7650091`) so the pill/popover behaviour can be demonstrated live, then removes it.

## Seed (run, committed in its own transaction)

```sql
BEGIN;
WITH new_shipment AS (
  INSERT INTO inbound_shipments (id, shipment_number, shipping_container_number, shipment_date, shipment_status, company_id)
  VALUES (gen_random_uuid(), 'ZZT-SLC-1', 'ZZTU9990001', CURRENT_DATE, 'in_transit', '00000000-0000-0000-0000-000000000001')
  RETURNING id
),
new_line AS (
  INSERT INTO spo_allocations (
    id, spo_number, spo_line_number, product_id, warehouse_id, supplier_id, uom_id,
    company_id, allocated_quantity, quantity_received, receipt_status, line_status,
    issue_date, inbound_shipment_id, container_number, source_ref
  )
  SELECT gen_random_uuid(), 'SPO-2026/09-0030', 5,
         '31f1cb07-cdbe-4eea-b408-2314b0aaa1c6', '21608757-0065-4ef2-bd05-1397452411eb',
         NULL, NULL,
         '00000000-0000-0000-0000-000000000001', 1, 0, 'pending', 'open',
         NULL, new_shipment.id, 'ZZTU9990001', 'ZZT-SLC-1'
  FROM new_shipment
  RETURNING id, inbound_shipment_id
)
SELECT new_shipment.id AS shipment_id, new_line.id AS line_id
FROM new_shipment, new_line;
COMMIT;
```

`product_id` (`31f1cb07-cdbe-4eea-b408-2314b0aaa1c6`), `warehouse_id`
(`21608757-0065-4ef2-bd05-1397452411eb`), `supplier_id` (NULL), `uom_id` (NULL), `issue_date`
(NULL) are all copied from the sibling line `f16761b6-49e4-4103-9ee1-58a271f722e8`
(`SPO-2026/09-0030` line 1, company Sorento) - the values the plan asked to copy.

### Ids created (for cleanup)

- `inbound_shipments.id` = `bca0219d-e052-4820-8315-0370b241c109` (`shipment_number='ZZT-SLC-1'`,
  `shipping_container_number='ZZTU9990001'`)
- `spo_allocations.id` = `f37401ef-504f-46d7-b6dc-4c93259e0df3` (`spo_number='SPO-2026/09-0030'`,
  `spo_line_number=5`, `container_number='ZZTU9990001'`, `source_ref='ZZT-SLC-1'`)

## Cleanup (run after verification, mandatory even on failure)

```sql
DELETE FROM spo_allocations WHERE id = 'f37401ef-504f-46d7-b6dc-4c93259e0df3';
DELETE FROM inbound_shipments WHERE id = 'bca0219d-e052-4820-8315-0370b241c109';
```

### Post-cleanup verification

- `select count(*) from spo_allocations where spo_number='SPO-2026/09-0030';` -> **4** (the
  original 4 lines, scratch line gone)
- `select count(*) from inbound_shipments where shipping_container_number like 'ZZTU999%';` ->
  **0**

## Cleanup executed

Both `DELETE` statements above ran in one transaction and each reported `DELETE 1`, then
committed. The two verification queries were re-run immediately after and returned exactly the
expected values:

```
select count(*) from spo_allocations where spo_number='SPO-2026/09-0030';
 count
-------
     4

select count(*) from inbound_shipments where shipping_container_number like 'ZZTU999%';
 count
-------
     0
```

No other row was touched - both `DELETE`s targeted the scratch rows by primary key `id` only.
