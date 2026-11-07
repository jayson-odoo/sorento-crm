# CARD: SALES-LEADERBOARD (who sold most, this month)

Status: Asked (crew-ask on PR #2227, 7 Nov). Build waits for the owner's answers. Track: full (size L, new screen).
Mockup: `mockups/sales-leaderboard-07nov.html`. Plan: `PLAN-sales-leaderboard-07nov.md`.

## The ask in one line

Owner 7 Nov ~15:40: "I also need a sales leaderboard feature." A screen that ranks the sellers for a period, on the
one sales number the CRM already has, so the board, the Targets screen and the assistant never disagree.

## What already exists (measured, paths under `sorento_crm_backend/app/` unless marked)

- **The sales number.** `services/sales/invoiced_sales.py:4-5,79-104`: IV + CS + DN - CN, `local_net_total` net of
  tax, by DocDate, `status = posted` only (cancelled never counts). Agent attribution `agent_id()` :119-131 (the
  document's agent, or the customer's agent when the company is set to `customer`).
- **The one engine.** `services/reports/ask.run_ask` (`ask.py:231`) on the `invoiced` basis already ranks by
  `sales_agent` with `top_n` (:383-401) and already compares (`compare_to=previous_period|last_year`, each row gets
  `prev` + `change_pct`, :531-578). Distinct customers is a measure (:260). So the leaderboard needs **no new
  calculation**: it is `run_ask(basis=invoiced, group_by=sales_agent, compare_to=previous_period)`.
- **What is missing in the engine:** no `person` dimension (rows are agent CODES; one person can hold several codes,
  `models/sales_agent.py:62` `person_label`), no `team` dimension, no `company` dimension (company is only a filter,
  `report_ask.py:280-282`). The only route that runs `run_ask` is chatbot-only (`report_ask.py:309-310` refuses a
  Bearer token); the staff `POST /reports/sales_invoiced_ask/run` (`api/v1/reports/reports.py:234`) returns pivot
  rows without ranking or compare.
- **Targets.** `services/sales/achievement_service.py:641-720` computes "achieved" on the same invoiced rules, but
  credits a PERSON (all codes sharing `person_label`, :123-148) and uses the document total, not the line sum
  (:657-658). `achieved_pct` :898-902.
- **Commission** (`services/sales/commission_service.py`, Additional tiers :13-14): never shown on the board. Today
  `sales.targets.view` shows every target's commission (`api/v1/sales/targets.py:77-104`); the board does not widen that.
- **Assistant.** `crm_report_ask` (MCP `sorento_crm_mcp/sorento_crm_mcp/catalog.py:921-1000`) already answers "top 3
  sales agents last month" with `group_by=sales_agent`.
- **No podium / leaderboard component exists in the FE.**

## Behaviour, with a recommendation each

| # | Topic | Recommendation |
|---|---|---|
| 1 | Who is ranked | One row per **person** (agent codes grouped by `person_label`, code shown under the name), so a person selling in SRT and another company is one row. Needs a `sales_person` dimension on the invoiced ask definition: a grouping, not a second calculator. "(no agent)" sales shown as a footer line, never ranked. |
| 2 | Ranking metric | Rank by **invoiced net sales (RM)**. Columns beside it: vs last period (`change_pct`, from `compare_to`), target achieved % (only for a person with an agent target in the period, from `achievement_service`, the Targets screen's own figure; blank otherwise), customers invoiced (distinct count). No "new customers" column in v1 (no measure for it today; trigger: owner asks). |
| 3 | Period | Chips **This month (default) / Last month / This quarter / YTD**, plus a custom range; compare is always "previous period of the same length". |
| 4 | Grouping | Board by **person**; **Company** filter (default: all granted). Brand and category as optional filters (the engine has them). **Team** board deferred: the engine has no team dimension and team credit uses dated stays (`achievement_service.py:159-171`); trigger: owner asks for a team board. |
| 5 | Who sees what | New slug `sales.leaderboard.view`. Everyone with it sees the **full board** (rank, name, RM, change, target %). Commission is never on the board. A user linked to an agent gets their own row highlighted and pinned under the top rows ("You: #7"). |
| 6 | Display | Page header + filter row + **podium of top 3** (cards) + DataGrid of all ranks with a sparkline-free trend arrow. Totals KPI row: total invoiced, sellers ranked, vs last period. |
| 7 | Refresh | **Live on load** (one query over posted billing documents for one month is small); figures are as fresh as the last AutoCount push, and the header shows "Data as of <last push time>". No daily snapshot. |
| 8 | Mobile (375px) | Podium collapses to one row of three compact cards; the grid keeps Rank, Name, RM; change and target % move under the name. |
| 9 | Assistant | Same service: the board's endpoint calls `run_ask`; the assistant keeps `crm_report_ask` and gains the `sales_person` grouping, so "who's top this month" answers with the board's numbers. One eval line added. No new MCP tool. |

## Known mismatch to rule on

The board ranks on the **line** sum (`run_ask`); Targets "achieved" uses the **document** total
(`achievement_service.py:657-658`). They can differ by rounding / header-level discounts. Recommendation: show
target % from the Targets service as is (so it matches the Targets screen) and add a reconciliation test on dev data.

## Real October case (dev copy)

This cloud sandbox has no copy of the dev database (crew rule: no shared DB). The mockup marks its figures
"placeholder". Crew: run `evidence/sales-leaderboard-oct-dev.sql` (read only, `BEGIN READ ONLY ... ROLLBACK`) on the
dev copy and paste the output on the PR; the mockup is redrawn with those agent codes and October figures.

## Questions (max 5)

1. Ranked unit: (a) person, codes grouped by `person_label` / (b) agent code as AutoCount sends it. Rec (a).
2. Team board: (a) person board only in v1, team later / (b) person + team tab now. Rec (a).
3. Salesperson visibility: (a) full board, own row pinned / (b) top 5 + own rank only / (c) own row only. Rec (a).
4. Columns: (a) RM rank + vs last period + target % + customers / (b) also new customers (new measure). Rec (a).
5. Assistant: (a) reuse `crm_report_ask` with the person grouping / (b) a separate leaderboard tool. Rec (a).
