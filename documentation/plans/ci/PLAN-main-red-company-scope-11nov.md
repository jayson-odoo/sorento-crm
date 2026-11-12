# PLAN: MAIN-RED-COMPANY-SCOPE (11 Nov 2026)

Status: PR #2352 open, review clean, Merge-ready. Small fix track (one test file, no migration, no auth/RBAC change, no behaviour change).

## Problem

`sorento_crm_backend/tests/test_company_scope.py::test_every_company_id_table_is_registered` fails on
origin/main bcab68352c: `assert 188 == 183` (line 653). PRODUCT-COSTING (#2321, 9e9731b17a) added five
company-scoped tables (`costing_settings`, `costing_category_rules`, `costing_product_overrides`,
`customer_costing_profiles`, `customer_costing_products`) without updating the owned-table census.

## Check before the number

The census counts `CompanyScopedMixin` subclasses. A table counts as properly owned when its model is a
mixin subclass and every read goes through the ORM (the mixin's `do_orm_execute` filter), with no raw SQL
that skips the company predicate. Evidence goes in the PR body with file:line.

## Architecture

Layer: test only. Mechanism: the census tripwire comment + `expected_owned` constant. No model, service,
route or schema change unless the check above finds a table that is not properly scoped.

## Change

1. `tests/test_company_scope.py`: add a PRODUCT-COSTING line to the census comment, `expected_owned = 188`.

## Tests

- Red: the unchanged test on bcab68352c (`assert 188 == 183`).
- Green: whole `tests/test_company_scope.py` + census/guard neighbours (`test_raw_sql_company_scope.py`,
  `test_list_api_perms.py`, `test_schema_uuid_id_principle.py`, costing access tests).
- Kill: drop `CompanyScopedMixin` from one costing model, the census fails on its count assert (the mixin declares `company_id`, so no offender appears); restore.

## Also report (no fix unless one line)

`tests/chatbot/test_no_live_llm_guard.py:21` imports `httpx2`: is it in the requirements CI installs?

## Standing rules

None of the owner's UI/data checklist lines apply (no user-visible change). guide: n/a.
