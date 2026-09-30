# UAC - customer-code-identity (CUSTOMER-CODE-IDENTITY)

One CRM customer per debtor code within a company. Names are labels. Plan:
`PLAN-customer-code-identity.md`.

## Resolution (ingest)

- **AC-01 [BE]** Given a customer `300-1001 / "1 LIVING DEPOT SDN BHD"` exists in the anchor
  company, when a sales order is pushed with `customer_code=300-1001` and
  `customer_name="MODERNMED SDN BHD"`, then the order links to the existing customer, no new
  customer row is created, no `customer_created` warning is emitted, the master's
  `customer_name` is unchanged, and `"MODERNMED SDN BHD"` appears in the customer's
  `name_aliases`.
- **AC-02 [BE]** Given no customer holds code `X` in the anchor company, when a sales order is
  pushed with code `X` and a name, then exactly one customer is back-created (`customer_created`)
  and a second push with the same code and a different name lands on that same row (AC-01).
- **AC-03 [BE]** Given two legacy rows share code `X` in the anchor company and one of them holds
  an `integration_references` row, when a document names code `X` with no ref, then it resolves
  to the row holding the ref and the verdict carries `customer_ambiguous`.
- **AC-04 [BE]** Given two legacy rows share code `X`, neither holds a ref, and one has orders,
  when a document names code `X`, then it resolves to the row with orders and carries
  `customer_ambiguous`.
- **AC-05 [BE]** `customer_ambiguous` is in the published warning vocabulary
  (`GET /api/v1/external/contract` `warnings`).
- **AC-06 [BE]** `customer_back_create.get_or_create` matches by code alone (case and whitespace
  insensitive, within the company) and returns the existing row when the name differs.
- **AC-07 [BE]** A code held by another company is never matched (AC-V1-2 unchanged).

## Masters push and imports

- **AC-08 [BE]** Given a customer with code `X` and name `ALPHA`, when the masters push sends
  code `X` name `BETA` with a new `source_ref`, then the existing row is adopted and linked,
  no third row is created, `customer_name` is updated to `BETA` (the masters push is AutoCount's
  own master and owns the name), and `ALPHA` is kept in `name_aliases`.
- **AC-09 [BE]** The order (Excel) import's debtor upsert matches by code alone: a row with
  the same code and a different debtor name reuses the customer and does not insert.
- **AC-10 [BE]** The customer master import (`customer_import_service`) treats a file row whose
  code is already held as an update of that row, never an insert of a second row.
- **AC-11 [BE]** `POST /api/v1/order-management/customers` with a code already held in the
  company returns 409 whatever the name.

## Schema and data

- **AC-12 [BE]** After the migration, `customers` carries a unique index on
  `(company_id, lower(btrim(customer_code)))` and the old `(company_id, code, name)` unique index
  is gone; inserting a second row with the same code in the same company fails.
- **AC-13 [BE]** The merge migration, run on a schema holding duplicate-code rows, keeps exactly
  one row per code per company: the row holding the integration reference, else the one with the
  most orders (`orders` + `sales_orders`), else the oldest. Losers are deleted.
- **AC-14 [BE]** After the merge, every row that referenced a loser (orders, order lines via
  their order, sales orders, delivery orders, customer contacts, respond contact links, stock
  asks, project leads, integration references) references the survivor, and the losers' names
  are in the survivor's `name_aliases`.
- **AC-15 [BE]** The merge does not lose a unique-constrained child row where the survivor
  already holds the equivalent: a respond contact linked to both rows ends with one link; a
  loser's `main` contact becomes a `stakeholder` when the survivor already has a `main`.
- **AC-16 [BE]** A read-only report (`python -m scripts.report_customer_code_duplicates`)
  lists, per duplicated code, every row with its name, whether it holds a ref, and its order
  counts, without writing anything.

## Frontend

- **AC-17 [FE]** The Customers list shows one row for `300-1001` after the merge (data, no code
  change), and the customer detail page shows the aliases under the header as "Also known as"
  when there are any, nothing when there are none.

## Hand test

- **AC-18 [E2E]** On the crew test copy: Customers page shows one `300-1001`; an SO push with a
  changed debtor name lands on that same customer and the name appears as an alias.
