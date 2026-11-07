# CARD: SALES-LEADERBOARD (who sold most, this month)

Status: Asked (crew-ask on PR #2227, 7 Nov); round 2 on dev evidence (comment 6704175660). Build waits for the owner's answers. Track: full (size L, new screen).
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

## Real October case (dev copy `sorento_prod_1104`, prod copy of 4 Nov; crew run, PR #2227 comment 6704175660)

162 agent-code x month rows (Sep + Oct 2026, SRT + MCH). Grouped by `person_label`: 41 persons, 40 with October sales.
October total RM 16,514,407.26 (line sum), +2.9% vs September RM 16,041,861.96; no agent RM 1,210.32.
Top 3: LCL RM 1,856,856.61 (SRT 1,798,043.09 + MCH 58,813.52, so #1 only because of the person grouping),
SEAN RM 1,276,644.96 (SEAN I + III + IV), JUSTIN RM 1,156,644.97. Mockup redrawn with these.

What the evidence changes:
- **Target % dropped from v1.** Only 3 agent targets cover October: TGT-000002..4 (FANNY I / III / IV), yearly 2026,
  `basis = ordered`. None is invoiced, so a target % beside an invoiced month would compare different things.
  Trigger: the first invoiced agent target. (Q4 recommendation updated.)
- **House codes rank.** ACC (no `person_label`, falls back to its code), C/S and SAMPLE are agent codes in AutoCount;
  they rank at #37, #39, #40. Simplest is to rank them as sent; an exclude list waits for the owner to ask.
- **Change % is blank when last period was zero or negative** (SAMPLE Sep RM -1,206.10 would read -136%).

## Line sum vs header total (2 of 162 rows differ)

| Person, month | Line sum (engine) | Header total (Targets) | Gap | Effect |
|---|---|---|---|---|
| ERIC NG, Oct | 949,652.34 | 805,048.34 | +144,604.00 | rank #7 either way (FANNY 949,878.00 is above, WT 684,012.74 below); vs Sep -1.7% on lines, -16.7% on headers |
| JENNIFER, Sep | 375,705.75 | 228,388.15 | +147,317.60 | her October change flips: -22.4% on lines, +27.6% on headers |

Where the two numbers come from:
- Line sum: `signed_line_amount()` = `net_amount * currency_rate` (`services/sales/invoiced_sales.py:96-99`), what
  `run_ask` invoiced sums (`services/reports/datasets/billing_document_lines.py:66`), so Sales & outstanding and the
  chatbot.
- Header: `signed_amount()` = `local_net_total` (`invoiced_sales.py:91-93`), what Targets sums for an all-products
  amount target (`achievement_service.py:657-658`). The model calls it "what the invoiced basis sums"
  (`models/finance.py`, `local_net_total` comment, ruling Q12).
- Nothing ties them: ingest checks only `total = net_total + tax_total` (`schemas/canonical_documents.py:642`); lines
  are stored as sent (`services/finance/billing_document_ingest_service.py:473-494`).

Ruled out from code: duplicated lines (unique `(document_id, source_ref)`, `models/finance.py` line table, and a
duplicate `source_ref` in one push is refused, `canonical_documents.py:636-641`); stale lines after a re-push (a push
replaces the whole line set, `billing_document_ingest_service.py:390-418`); a missing header total (`local_net_total`
is required, `canonical_documents.py:519`). Lines exceed the header, so the money is on the lines only.

Candidates, all named in `documentation/plans/finance/REF-autocount-billing-schema.md`:
1. **Footer discount**: header-only money (REF section 5 item 5) lowers `NetTotal` but no line. Q2 shows no
   discount line and Q1 shows `sum_line_net` > `net_total` on an MYR document.
2. **Package parent + children both carrying money** (REF section 3, "must not double count"; the backfill runbook
   says children carry no money on AED_SORENTO, but these may be a later shape). Q2 shows a parent line whose amount
   equals the sum of following lines.
3. **Currency**: a non-MYR document whose lines are already local (Q1 `currency_code` <> MYR, `gap = sum_line_net *
   (rate - 1)`).
4. **Stale line set in AutoCount terms**: a line-only edit in AutoCount does not bump `LastModified` (REF item 9), so
   the CRM may hold lines from before an edit while the header was re-sent. Q1 `last_synced_at` vs the line
   `updated_at` in Q2.

Read-only query for crew: `evidence/sales-leaderboard-line-vs-doc-dev.sql` (Q1 the documents off, Q2 their lines,
Q3 how widespread across 2026).

Recommendation (pending Q1-Q3): the board stays on `run_ask` (one engine, same as Sales & outstanding and the
chatbot), and the fix goes where the cause is. If it is candidate 1 (header-only money), the engine's invoiced
total must use the header when no line-level filter or grouping is asked, which changes the shared engine for every
consumer: an owner ruling, not a leaderboard decision. If it is 2, 3 or 4 the lines are wrong and the fix is at
ingest / the shared service; the board needs no change.

## Questions (max 5)

1. Ranked unit: (a) person, codes grouped by `person_label` / (b) agent code as AutoCount sends it. Rec (a).
2. Team board: (a) person board only in v1, team later / (b) person + team tab now. Rec (a).
3. Salesperson visibility: (a) full board, own row pinned / (b) top 5 + own rank only / (c) own row only. Rec (a).
4. Columns: (a) RM rank + vs last period + customers, no target % in v1 (no invoiced agent target exists) / (b) also new customers (new measure). Rec (a).
5. Assistant: (a) reuse `crm_report_ask` with the person grouping / (b) a separate leaderboard tool. Rec (a).
