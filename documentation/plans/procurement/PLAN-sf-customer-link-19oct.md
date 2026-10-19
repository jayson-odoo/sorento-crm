# PLAN: SF-CUSTOMER-LINK, one-off reviewed script linking old Sponsorship Forms to their customer

Status: in progress (small fix track: one script + its tests, no migration, no API/RBAC change; owner runs it on prod)

UAC: `sf-customer-link-acceptance-criteria.md` (beside this file).

## Why

`scripts/backfill_sf_sales_type.py` (SF-SALES-TYPE, #1728) inner-joins `purchase_requests.customer_id`
onto `customers` (`backfill_sf_sales_type.py:41`), so it can only fill an SF that is linked to a
customer. Every old SF predates the link (`customer_id`, added by `frc_0001_debtor_type_no_cs.py:61`,
set only through `link_customer`, `app/services/debtor_type.py:58`) and stores the customer as free
text in `customer_name`. Measured on the dev DB (15 Oct prod copy, read-only): 107 SFs, 0 linked,
107 with a blank sales type.

Owner ruling (19 Oct): "yeah i need a one off script to fill the customer link". This is a ONE-OFF,
REVIEWED exception to "explicit links only": the owner reviews the full proposed list (a CSV) before
anything is written, and only rows the owner leaves in the CSV are linked.

## Build

`sorento_crm_backend/scripts/link_sf_customers.py`, same shape as `backfill_sf_sales_type.py`
(core functions take a session; `main()` is CLI plumbing).

- `propose(db)` returns one row per Sponsorship Form: status, form number, typed customer text,
  matched customer code + name + debtor type, the sales type that customer maps to
  (`SALES_TYPE_FOR_DEBTOR_TYPE`, `debtor_type.py:15`), plus the SF id and customer id (machine keys
  the apply step reads back).
  - `ALREADY LINKED`: `customer_id` is set. Never touched; shows the linked customer.
  - `LINK`: exactly one ACTIVE customer of the chosen company whose name equals the typed text after
    trim + whitespace collapse + lower-casing on both sides.
  - `AMBIGUOUS`: more than one such customer (their codes are listed; nothing is picked).
  - `NO MATCH`: none (blank text included). No fuzzy match, no prefix/suffix stripping.
- Dry run (default) writes nothing, prints the rows and counts and writes the CSV to the path given.
- `--apply --from-csv FILE` reads the reviewed CSV and, for each `LINK` row, re-runs the same match
  for that SF NOW and links only when the result is still `LINK` to the same customer the CSV names
  (a row whose SF got linked meanwhile, whose text changed, or whose match changed is skipped and
  counted). The link goes through `link_customer` (active check, company visibility) and stores the
  customer's own name as `customer_name`, exactly like the staff form
  (`procurement_service._apply_customer_link`), so the printed name and the routed customer cannot
  differ; the difference is case/spacing only by construction. Never overwrites a set `customer_id`.
  One transaction, one commit; any error rolls back everything. A rerun links 0.
- After apply it prints the next command: `python scripts/backfill_sf_sales_type.py` (dry run, then
  `--apply`), which fills Sales Type from the linked customer's debtor type. It does not call it:
  the owner reviews that dry run on its own.

### Company

`purchase_requests` has no `company_id` (measured: `information_schema.columns`; the model
`PurchaseRequestHeader(Base)` at `app/models/procurement.py:1092` carries no `CompanyScopedMixin`),
so an SF has no company of its own to match against. The script matches customers of ONE company,
`--company-id`, default `DEFAULT_COMPANY_ID` (Sorento), by setting the session's company scope to that
company (`set_company_scope`), the same mechanism that scopes the staff customer picker. Another
company's customer is never matched and `link_customer` refuses it. Measured on dev: all 70 name
matches are Sorento customers, 0 are Mocha customers.

## Tests (red first)

`sorento_crm_backend/tests/test_link_sf_customers.py`, blank Postgres schema, every row seeded:
statuses LINK / NO MATCH / AMBIGUOUS / ALREADY LINKED; trim + whitespace + case matching and nothing
looser; inactive customers never matched; other company never matched; PRs never listed; dry run
writes nothing and writes the CSV; apply links only CSV `LINK` rows (deleted rows skipped), stores the
customer's name, never overwrites, skips a row whose match changed; idempotent rerun = 0.

## Runbook

In the PR body (owner runs it on prod; crew never does).
