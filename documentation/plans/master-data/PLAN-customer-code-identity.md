# PLAN - customer-code-identity (CUSTOMER-CODE-IDENTITY)

Status: in progress (lane branch `crew/customer-code-identity`); full track (migration,
external ingest surface). UAC: `customer-code-identity-acceptance-criteria.md`.

## Problem (owner, 30 Sep 2026)

AutoCount identifies a debtor by code. The CRM back-creates a customer when the (code, name)
pair is not found, and a user can edit the debtor name on a sales order or DO, so one debtor
code now exists several times in `customers` (300-1001 three times, 300-4002 and 300-H030
twice). The ingest resolver picks one of them arbitrarily (`ORDER BY id DESC ... first()`),
so orders for the same debtor scatter across rows and the integration cannot be trusted.

Evidence (origin/main 950785de2, `sorento_crm_backend/`):

- `customers` uniqueness is (company, lower/trim code, lower/trim name):
  `app/models/order.py:199-205`, `alembic/versions/305_company_composite_unique.py:82`.
- Resolver: ref first, else code match ordered by id desc, else create by code and name:
  `app/services/master_ref_resolver.py:315-333, 359-367`; `app/services/scm/customer_back_create.py:52-58`.
- Masters push adopts by code AND name: `app/services/master_ingest_service.py:640-653`.
- Order import debtor upsert (pair match): `app/services/order_service.py:2203-2248`.
- Manual create (pair conflict check): `app/services/order_service.py:3647-3662`.
- Customer master import keys on the pair: `app/services/customer_import_service.py:277-316`.
- Migration 220 already merged duplicate pairs once, repointing FKs discovered from
  `pg_constraint` - the pattern this plan reuses.

## Decisions

- **D1 Code is identity.** Within a company, `lower(btrim(customer_code))` identifies the
  customer. Every matcher (resolver, back-create, masters adoption, order import upsert, manual
  create conflict, customer import) matches by code alone. Names are labels.
- **D2 Names are kept, never used to fork.** A document naming an existing code with a
  different name links to the existing row and the name is appended to the customer's
  `name_aliases` (new JSONB list column, case-insensitive dedupe). The master name is not
  overwritten by a document. The masters push (AutoCount's own Debtor master) does own the
  name: it updates `customer_name` as it always did and the previous name is kept as an alias.
  One column, not an alias table: one list per customer, read in one place (the detail page).
- **D3 Ambiguity is refused, not guessed.** While legacy duplicates exist (the merge is a held,
  owner-approved migration), a code matching more than one row resolves to the row holding the
  integration reference, else the row with the most orders (`orders` + `sales_orders`), else the
  oldest, and the verdict carries the new warning `customer_ambiguous` (added to the contract
  vocabulary). After the merge and the unique index this branch is unreachable.
- **D4 Unique index replaces the pair index.** `uq_customers_company_code_lower` on
  `(company_id, lower(btrim(customer_code)))` replaces `uq_customers_company_code_name_lower`.
  Two indexes carrying two identity rules would drift; the pair index is implied by the new one.
- **D5 Merge migration.** One alembic revision: (1) add `name_aliases`; (2) merge duplicate-code
  groups per company, survivor per D3, repointing every FK discovered from `pg_constraint`
  (migration 220's mechanism), with unique-collision handling (a child row that would collide
  with one the survivor already has is deleted; a loser's `main` contact is demoted to
  `stakeholder` when the survivor has a `main`); survivor fill-only on empty contact and
  classification columns; losers' names into `name_aliases`; delete losers; (3) swap the
  unique indexes. Destructive: held by crew for the owner. A read-only report script shows the
  blast radius first (`scripts/report_customer_code_duplicates.py`).
- **D6 Odd names merge too.** 300-1001 "MODERNMED SDN BHD" next to "1 LIVING DEPOT" is still the
  same debtor code, and AutoCount is the truth for debtors. Recommended to the owner via
  `crew-ask`; the report flags names that share no word with the survivor's.

## Slices

1. Tests red: resolver, back-create, masters adoption, order import upsert, manual create,
   contract vocabulary, migration merge (scratch schema).
2. Backend: `customer_rules.customer_code_key`, resolver code-only match with D3 ambiguity and
   alias recording, back-create by code, masters adoption by code, order import upsert, manual
   create conflict, customer import keyed by code, model + schema + migration, report script.
3. Frontend: `name_aliases` on the customer type and "Also known as" under the detail header.
4. Hand-test script `laneboard/scripts/<PR>.md`, `crew-migration` SQL for the test copy.

## Out of scope

- Merging customers across companies (never: the code is per company, D1).
- Renaming a customer from a document push (the master name stays; D2).
- Deduplicating `orders.debtor_name` text: it stays as the document printed it.
