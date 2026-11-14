# PLAN: Invoiced target achievement, period join the planner can hash (lane TARGET-ACHIEVED-PERF)

Status: Plan (scope add) - part 1 (join fix + timeout text) built, reviewed PASS, PR #2420; part 2 (#2419 slice 1) waits on the behaviour-card answers. Track: full (M after the scope add: agent loop + prompt). UAC:
`target-achieved-perf-14nov-acceptance-criteria.md`.

## Why

Owner, 14 Nov (testing #2243): the AI agent's "how is the sales for my dealers this year, compared
with their targets?" times out, and the Targets screen dealer tab takes about 8.7 s. Root cause
(crew report `AGENT-COMMISSION-WA-timeout/rootcause.md`, measured on sorento_prod_1112):

- `achievement_service._achieved_invoiced` joins credited documents to the credit rows (`icr`
  VALUES) and then to the period list (`ipv` VALUES, 260 rows) on `credit_group` and a date range.
  VALUES carry no statistics, so the first join is estimated at 1 row and the planner nests the
  period list under it: 42,456 x 260 comparisons, 10,998,391 rows removed by the join filter,
  5-6 s warm, 18-28 s cold. The agent's per-statement limit is 5 s (`query.py:26`).
- The timeout hint (`query.py:585`) tells the model to narrow with a filter, but a computed
  entity's filters (agent, owner kind, ...) run in Python after the compute
  (`computed.py:359-361`), so a retry can never be faster.

## Architecture

- Layer: backend service only (`app/services/sales/achievement_service.py`), plus the assistant
  registry's timeout message (`app/services/assistant_registry/query.py`, `computed.py`).
- Mechanism: fold the credit rows and the periods into ONE VALUES in Python, one row per
  (credit row, period of its credit group) with the intersected date window
  `[max(valid_from, pstart), min(valid_to, pend)]`, empty windows dropped. The documents meet it
  on a hash of `(ckind, credit_key)`; only the date test stays as a join filter, on the few rows
  of that key. Same tuples as today's two joins (each (document, credit row, period) triple with
  the date inside both windows), so the figures are identical by construction.
- Rejected: the order side's `period_days` (every day of every period, `achievement_service.py:316-341`):
  works, but generates about 100,000 day rows for 2026's 444 dealer periods; the fold removes a
  join instead of adding a CTE (PRINCIPLES "Simplest thing that works").
- Timeout message: `timed(db, work, timeout_message=...)`; the two computed-entity calls pass a
  message that does not suggest narrowing. Pushing the agent filter into SQL is not trivial (the
  compute signature takes no filters), so text only (brief step 3).

## Reuse

- `_credit_groups` (`achievement_service.py:201`) as is: merged windows per (group, key), so a
  document still meets at most one credit row per period.
- `invoiced_sales.posted / signed_amount / agent_id / signed_line_*` as is (the one shared sales
  function, standing rule "Every sales figure ...").
- `timed` (`query.py:572`) extended with one keyword, not copied.

## Tests (red first)

- `tests/test_sales_target_invoiced.py`: a plan test on a prod-shaped, analyzed volume (60 dealers
  x 2 accounts x 4 quarters x 30 documents): figures equal the shared sales total, the plan joins
  ONE VALUES list read once, and `Rows Removed by Join Filter` stays within (credited documents x
  periods of one target). Red on today's code (two VALUES lists). The prod tie-break itself does
  not reproduce at fixture size (the fixture's first join is estimated at 5 rows, prod's at 1).
  The file's figure tests stay green.
- `tests/chatbot/agent/...` timeout message: a computed-entity timeout reads without "Narrow".

## Timing (brief step 4)

sorento_prod_1112, read-only sessions, before vs after, warm and cold: agent_target_summary
this_year, target_list this_year, `GET /api/v1/sales/targets?all=true&subject=dealer`. Figures:
2026 totals per dealer target and account, before vs after, must be identical.

## Measured (sorento_prod_1112, read-only sessions, 14 Nov, Mac load 9-15)

ms per call through the real code path; "first" = first call on a new connection, "warm" = repeat.

| Call | Before first | Before warm | After first | After warm |
|---|---|---|---|---|
| agent_target_summary this_year | 5,535 timeout | 5,549 timeout | 748 | 404 |
| target_list this_year | 315 | 301 | 406 | 301 |
| Targets dealer tab (`list_all_targets(subject="dealer")`) | 583 | 320 | 939 | 361 |

The timed-out statement itself, timeout lifted: 9,035 ms before (nested loop, 10,998,391 rows
removed). Before, target_list and the dealer tab got the hashed plan on these runs: the nested and
the hashed plan cost within the planner's 1% fuzz (395.86 vs 394.58), so a lower start-up cost
picks the nested one on some inputs (the root-cause runs: dealer tab 8.7 s, target_list 7.3-15.4 s).
After, the statement has one VALUES join and no such tie.

Figures, old vs new statement in one read-only session (timeout lifted): IDENTICAL for every 2026
dealer period per account (444 periods, 387 non-zero cells), per document (39,110 cells), per
period, the dealer tab body, and the agent_target_summary / target_list answers.

## Part 2: #2419 slice 1 "sales vs target, fast and right" (crew scope add, 14 Nov 19:27)

Owner approved `documentation/plans/agent/PLAN-agent-context-budget-14nov.md` (PR #2419), section 7
row 1. Target: the panel answers "how are my dealers' sales this year against their targets?", "and
last year?" and a typo version in 2 model calls, under 35,000 tokens, under 15 s, no timeout, with
the Targets screen's figures. Owner D4: no hard cut-off that ends an answer with a limit message.

Measured today (discovery, file:line in `sorento_crm_backend/`):
- `assistant_registry/computed.py:360-381`: `entity.compute(db, user_id, own_only, date_from,
  date_to, limit)` computes every target in the window; agent / owner kind / dealer filters run in
  Python after it (`_exact_agents` :378, row tests :381). `types.py:72-76` compute takes no filters.
- `assistant_registry/sales.py:44-71`: the period-count cap and the targets query take no agent;
  `_summary_rows` :156 learns a dealer row's agent only after `_accounts_by_target` :172-176.
  `target_list` (`_target_list_rows` :303) calls `list_all_targets` for all three subjects.
- No gap field (`agent_target_summary` :425 and `target_list` :500 carry `achieved_pct` only); the
  figure check (`chatbot/agent/loop.py:709-724`) rejects a gap the model computes itself.
- `loop.py:89` MAX_QUERY_CALLS = 3, check :2292 counts every crm_query AND crm_describe entry,
  denied ones included; the refusal is a tool reply, not the end of the turn.
- Prompt conflicts (`ai_prompt_registry.py` fallback; live text is the DB row `chatbot_agent`,
  `loop.py:59`): :1103 "resolve every name with crm_resolve before any other tool" vs
  `query_tools.py:278` "pass the agent ... no crm_resolve"; :1116 "show invoiced, delivered and
  ordered" vs the loop refusing a second basis (`loop.py:2301-2304`).

Design (pending crew answers Q1-Q5):
- Narrowing: `run_computed` resolves the agent filter to candidate agent ids and passes them (and
  owner kind) to `compute`; `sales.py` keeps a target when its agent, a team member, or ANY of its
  dealer accounts' agents is a candidate (95 of 164 dealer targets have accounts of two agents).
  The Python row filter still runs after: the answer can only lose work, never rows.
- Server-side gap: one field beside `achieved_pct` on both entities (Q1 decides its sign).
- Query cap: counts only crm_query calls that ran (Q3: timed-out ones count).
- Prompt: draft a new `chatbot_agent` version through the repo's prompt-version path (Q2).

Lead pattern: tester writes the red tests from the UAC (part 2 lines), coder implements, reviewer
once over the whole lane; hand test filed with the three phrasings; live x1 per Q4.

## Standing rules that apply

- "Every sales figure ... comes from the one shared sales function": unchanged, same service.
- "Nothing hangs": the Targets dealer tab and the agent answer return well under 5 s.
- "The bot states only what the data holds": the timeout message no longer suggests a retry that
  cannot help.
