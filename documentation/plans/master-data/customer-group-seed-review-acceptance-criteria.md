# UAC: CUST-GROUP-SEED-REVIEW

Plan: `PLAN-customer-group-seed-review-3oct.md`.

## PR 1

- AC-1 [BE] `alembic upgrade` through `cust_group_0001` creates `customer_groups` and
  `customers.customer_group_id` and assigns NO customer to any group, even when a numbered
  family (`X SDN BHD [A/C I]`, `X SDN BHD [A/C II]`) exists. `customer_groups` holds 0 rows.
- AC-2 [BE] The revision id stays `cust_group_0001` with `down_revision` `picker_no_cap_0001`;
  one alembic head.

## PR 2 (filled in once the behaviour card is answered)

- AC-3 [SQL] The proposal SQL is read only (`BEGIN READ ONLY ... ROLLBACK`) and writes nothing.
- AC-4 [BE] Apply links only the customers the approved list names by id; a row whose id,
  company, code or name does not match is rejected and reported, never matched by name.
- AC-5 [BE] Apply is idempotent and has a dry run that changes nothing.
