# PLAN: agent answers commission payout for dealer and team (AGENT-COMMISSION-ALL)

Status: Build done (owner answered Q1-Q5 8 Nov ~02:35 MYT, all recommendation (a)); Phase 3 review in progress.
Track: small fix (registry only, no migration, no new permission). Size M.

Follow-up to #2210 (AI-TOOLS-WAVE2). Owner, 8 Nov: asking the AI agent about commission
payout finds only AGENT (salesperson) commission, not DEALER or TEAM commission.

## Step 1: commission map (main @ 90d2de22)

### One engine, three subjects

There is ONE commission computation for every kind. Nothing is stored; it is computed per period.

| Piece | Where |
|---|---|
| Engine: marginal / retroactive / none, pct / amount / points thresholds, per-account rates, rounding | `sorento_crm_backend/app/services/sales/commission_service.py:92` `payout_for` |
| Tier "+ Additional" (#2186): only the REACHED main tier's Additional pays, never a lower tier's, never carries up | `commission_service.py:169-171`; RM Additional (Bonus) of the reached tier only `:179` |
| Legacy `is_additional` rows: pay on their own threshold and stack, until folded | `commission_service.py:172-176`, fold `:210` |
| Per period, per target: agent and team collapse achievement to one bucket; a dealer keeps per-account | `app/services/sales/target_service.py:1392` `period_payout` (`:1406`) |
| Dealer "replaced by" another dealer target that reached a tier: this one pays 0 | `target_service.py:231` `_replacing_reached`, `:1689` |
| Dealer paid account (`payout_customer_id`) | `target_service.py:277`, `models/sales.py:377` |
| Batched per-period figures (the assistant's source, equal to the target page) | `target_service.py:2345` `period_figures` |
| Target page (periods, commission, bonus, tier ladder) | `target_service.py:1772` `target_detail`; earned to date / current `:1961` `_earned` |
| Commission statement xlsx (documents behind Achieved + tier table) | `target_service.py:1976`; route `api/v1/sales/targets.py:264` |
| Targets list tabs (Teams, Agents, Dealers): whole-range target/achieved/%; Commission column (current period) ONLY on the Dealers tab | `target_service.py:1607` `list_all_targets`, `:1684`; FE `SalesTargetsView.tsx:402` |

Subjects (`models/sales.py:331` SalesTarget, `subject_kind` `:351`, CHECK `:415-420`):

- **agent**: `sales_agent_id`; may be a child of a team target (`parent_target_id` `:400`).
- **team**: `sales_team_id`; the team's period figure is the sum of its agent children (`resum_team`,
  `target_service.py:518`); its commission is the team target's own tiers on the team's achievement.
  No payee is stored for a team payout; `SalesTeam.leader_sales_agent_id` (`models/sales.py:64`) exists
  but nothing in commission reads it. There is no separate "team leader override" commission.
- **dealer**: counted accounts (`target_accounts`, `:609`), per-account tier rates (`:585`), paid to
  `payout_customer_id`; label = customer group name when all accounts share one, else the first
  account's name (`target_service.py:164`).

Permissions (screens): `sales.targets.view` sees all three tabs and every target page.
`sales.targets.view_own` sees only the agent targets of the user's own agents; team and dealer tabs are
empty, a team/dealer target page is a 404 (`api/v1/sales/targets.py:76`, `:96`;
`app/services/own_scope.py:169`).

### What the assistant covers today (`app/services/assistant_registry/sales.py`)

| Entity | In crm_query index? | Rows | Commission? |
|---|---|---|---|
| `sales_target` `:260` | NO (`in_index=False` `:324`; hint redirects to agent_target_summary `:322`) | one per target period, any subject, `subject` = agent / team / dealer label | yes: commission, bonus, payout, tier_reached, replaced |
| `agent_target_summary` `:333` | yes, the ONLY payout entity (hint `:362` "PAYOUT / COMMISSION ... per agent") | one per OWNER over the window | yes |
| `target_list` `:371` | yes | one per target (Targets tabs) | no commission fields |

All three read `period_figures` (one computation, equal to the page; tests in `tests/chatbot/agent/test_ai_tools_wave2*.py`).

### Why dealer and team questions fail

1. **Dealer has no row of its own in the only payout entity.** `_summary_rows.owner()` (`sales.py:156-164`)
   folds a dealer target into the agent who owns every counted account, else into one "Unassigned" row.
   No field carries the dealer's name. "Commission payout for dealer X" -> the model calls
   `agent_target_summary` with `agent="X"` -> `shorthands` makes `owner eq X` (`query.py:708`) ->
   `_exact_agents` finds no agent named X (`computed.py:350`) -> zero rows -> `_no_match` answers with
   agent names (`computed.py:382`) -> "nothing matched".
2. **The entity that does have the dealer is hidden.** `sales_target` has `subject` = the dealer label and
   `tier_reached`/`payout`, but is out of the index and its hint tells the model to use the summary.
3. **Team: the owner is printed "Team <name>".** `agent="North"` -> `owner eq "North"`; `agent_exact`
   (`query.py:175`) splits on " - " only, so "Team North" never matches "North" -> zero rows. Only the
   exact string "Team North" works. "Commission of the agents in team North" has no path at all: the
   summary has no team field.
4. **Side defect found while mapping:** because of (1), "Agent A's commission payout" ADDS the payout of
   dealer targets whose accounts Agent A wholly owns. That money is paid to the dealer's account, and the
   Agents tab and the agent's target page show no such figure, so the agent answer does not tally with
   the screens whenever such a dealer target has commission.

## Step 2: behaviour card

Posted on PR as `crew-ask` (owner answers drive the build). Summary of the proposal:

- Keep ONE `crm_query`, ONE computation (`period_figures` via `_target_rows`); no new tool.
- `agent_target_summary` becomes a payout summary per SUBJECT: one row per agent, per team, per dealer
  (`owner_kind` agent / team / dealer), each row the sum of that subject's own target periods. The dealer
  row is named as the Dealers tab names it; `team` and `agent` (the owning agent of a dealer) are fields
  to filter on. An agent's row is its own agent targets only (fixes side defect 4).
- Name matching: team by its name with or without "Team"; dealer by the label, any counted account's code
  or name (exact first, then contains).
- Permissions: exactly the screens. `view`: all three. `view_own`: own agent targets only; a dealer or team
  question answers "not visible to you", as the empty tabs do.

## Built (as answered)

- `agent_target_summary` (`assistant_registry/sales.py` `_summary_rows`): one row per subject, `owner_kind`
  agent / team / dealer; `agent` (agent itself, or the owner of every account of a dealer) and `team` (an agent's
  team today) as filter fields; `replaced_by`. Dealer targets with one label are one dealer row.
- Matching (`computed.names_exact`): "CODE - Name" as before, plus names a row carries in `_names`: the agent's
  `person_label` (owner evidence C3: one person, three codes, the 3-call cap), a team with or without "Team", a
  dealer's account codes and names.
- Notes (`EntityDef.row_note`, `own_note`): targets of 0 left out of target/achieved/% (owner C3: 1,396.8%),
  "No commission is set ... payout is empty, not RM 0", "X is replaced by Y ...", and for view_own "team and dealer
  payouts are not visible to you".
- Owner evidence: `sales_target` hidden by ddd978ef; the per-dealer question now runs on the summary (one entity
  per question kind kept).

## Crew live x3 round (8 Nov, head fe1c8af4)

- Payout rows ranked by payout desc (`EntityDef.rank_by`); totals over every row and group, also when cut; a cut
  list says "Top N of M by commission payout"; up to 50 rows by default.
- Empty figures in words in the tool output (`_empty`): "no commission set", "left out (target of 0)"; no total
  for a column with no figures.
- No period named: this year (`EntityDef.default_window`), said; past the 2000-period cap, the periods containing
  today, said.
- An empty crm_query backs a not-found claim only for the name it searched with no other narrowing filter
  (`loop._searched_names`); the unbacked line reads "I did not search for X, so I cannot say it does not exist."
- Known and left: "this year" includes periods not started yet, so the year's target % reads low early in the
  year; payout is unaffected (reviewer should-fix 3, an owner call).

## Next waves (one PR each, same single crm_query; crew starts the next without waiting)

- W-A distance to the next tier and what it would pay (`tier_ladder`, `agent_progress`).
- W-B invoices behind an achievement / commission (`commission_statements`).
- W-C earned to date vs current period (`_earned`); teams and members as entities.
- W-D opportunities and quotations (own rules `opportunity_clause`, `project_clause`).
- W-E AR outstanding per dealer / agent; point ratios.

## Tests

`tests/chatbot/agent/test_agent_commission_all.py`: C1-C3 dealer by name, account code, per dealer; C4 agent own
only + dealers of an agent; C5 order and totals; C6 team with or without "Team"; C7 team members; C8 replaced;
C9-C10 view_own note; C11 index hint; C12 every row = target page payouts; E1 person label; E2 target of 0;
E3 no commission set. `test_ai_tools_wave2_round6.py` S1/S5 updated to the Q1 ruling.
