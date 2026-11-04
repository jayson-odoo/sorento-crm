# PLAN: RELEASE-FIX-4NOV, unblock the 4 Nov release

Status: in progress (PR open; the deploy.yml hunk waits on a token with the `workflow` scope). Track: small fix (test fixtures, one docstring, one CI timeout; no
migration, no behaviour change).

## Problem

Release run 41694380916 (deploy.yml, main a6ac58d67b = prod bfd2b54800 + #2151 #2105 #2094) failed.

1. `tests/chatbot/test_rearch_s2_apply_is_pure.py::test_turn_package_never_calls_re_dot_or_reads_dot_text`
   fails with `AssertionError: ['apply.py:3784: before. Parser fields only."""']`. The guard
   substring-matches `re.`; the word "before." in a #2105 docstring
   (`app/services/chatbot/turn/apply.py:3784`, `_which_one_keeps_its_ask`) trips it.
2. `tests/chatbot/test_one_ranking_r3c.py::test_r3c_5_a_customer_ranking_row_pick_opens_that_customers_products`
   answers "I could not fetch sales just now". Root: `DataError invalid input syntax for type uuid:
   "cust-1"`. #2105's `report_ask.with_customer_groups` queries `Customer.id IN (ids)` and the fixture
   customer row keys (test lines 31-32) are not UUIDs.
3. Flaky `tests/chatbot/agent/test_agent_writes_round2.py::test_contact_confirm_rechecks_the_operators_reach[True-rejected]`:
   `UniqueViolation uq_sales_agents_company_sales_agent`. `tests/_ask_todo_seed.py:39` names agents
   `ZZT{code}{uid()[:4]}` (16 bits of randomness per name).
4. Vitest shards are slow, not hung: 4 shards cancelled at the 20 min cap at 330-410 of ~448 files,
   every finished file green.

## Fix

1. Docstring reword only: "as before." becomes "as earlier.".
2. Fixture customer keys become valid UUID strings (`CU1`, `CU2`). Product behaviour unchanged.
   Follow-up for crew (not this lane): a code-side guard in `with_customer_groups` that skips
   non-UUID ids, so a malformed key cannot turn a ranking into a fetch failure.
3. Seed agent names use `uid()[:8]`.
4. `.github/workflows/deploy.yml` `validate-frontend` (vitest shards) `timeout-minutes` 20 -> 30,
   that job only.

## Verification

Throwaway Postgres DB (`release_fix_4nov_throwaway`, `-n 2`): red on main a6ac58d67b for 1 and 2;
green after on the purity guard file, the whole r3c file and every test file importing
`tests/_ask_todo_seed.py`. Kill proof: revert the docstring and the fixture keys, the same two
tests fail again.
