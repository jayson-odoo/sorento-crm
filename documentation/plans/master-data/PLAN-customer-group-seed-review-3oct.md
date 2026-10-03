# PLAN: Customer groups seeded from an owner-reviewed list (CUST-GROUP-SEED-REVIEW)

Status: PR 1 in review (PR #1451, DDL-only migration); PR 2 waiting on the behaviour card
answer. Track: small fix (PR 1); PR 2 track set by the chosen apply flow.
UAC: `customer-group-seed-review-acceptance-criteria.md`.

## Why

Owner ruling 3 Oct 2026 (option b): no automatic name-matching joins, explicit links only.
`cust_group_0001` (#1441) ran `seed()` on upgrade and joined customers into `customer_groups`
by `ledger_family_key` name similarity. It is not on prod yet (prod head `grn_pull_0001_perm`).

## PR 1: DDL-only migration (urgent, blocks the next release)

- `sorento_crm_backend/alembic/versions/cust_group_0001.py`: `seed()` and its call in
  `upgrade()` removed; DDL unchanged; revision id and `down_revision` unchanged so dev, which
  already ran the old body, stays at the same head (its seeded rows are left as they are).
- `plan_groups` stays a pure helper because `scripts/customer_groups_seed_sql.py` imports it.
- Test: `tests/test_customer_groups_seed.py` runs `upgrade()` under an alembic `Operations`
  context on the blank Postgres schema with the table and column dropped first; both are
  created and no customer is grouped. Red against the old body.

## PR 2: reviewed seeding (after PR 1 merges)

1. A read-only proposal SQL the owner runs on prod (`BEGIN READ ONLY ... ROLLBACK`): one row
   per proposed member with proposed group name, company, customer id, code, name, account
   level, current group. Exportable to Excel. The name rule only PROPOSES here.
2. An apply path that takes ONLY the owner-approved list (explicit customer ids per group),
   creates groups and links, idempotent, dry run first, never name matching at apply time.
   Flow (script vs admin import) per the behaviour card ask on PR #1451.
