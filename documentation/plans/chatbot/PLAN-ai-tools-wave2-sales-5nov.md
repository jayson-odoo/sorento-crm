# PLAN: AI-TOOLS-WAVE2 (sales modules in the assistant registry)

Status: Review (round 6: crew pass on 0463b805; sales basis and active customers passed there). Track: full (RBAC, one
additive migration).
Lane AI-TOOLS-WAVE2, PR #2210.

Parent: `PLAN-ai-tools-standard-5nov.md` (PR #2185), `PLAN-ai-query-core-5nov.md` (#2188, merged).

Owner ask: the agent cannot answer "commission payout" or "sales target" questions. Owner standard (5 Nov): every
module reaches the agent through the registry, one `crm_query` tool, no per-screen tools, switch off by default.

## Measured facts (base 5e97671e)

- Targets: `sales.targets` (`app/models/sales.py:342`), periods (:470), tiers incl. `is_additional` (:539),
  per-account rates (:580), dealer accounts (:603). Achievement and commission are not stored (`sales.py:330`,
  :546): `target_service.target_detail.period_out` computes them per period from `_achieved_by_account`,
  `period_payout` (over `commission_service.payout_for`) and `_replacing_reached`.
- Targets screen: `sales.targets.view` for every read (`api/v1/sales/targets.py:43,84`), module `sales`. No own-only
  slug on base. Owner ruling 5 Nov 23:2x: add `sales.targets.view_own` (below).
- Sales: `app/services/sales/invoiced_sales.py` is the one sales calculation: `posted()` :79, `signed_amount()` :91
  (IV + CS + DN - CN on `local_net_total`), `agent_label()` :134, `sales_type_label()` :318. Billing documents
  screen `finance.billing_documents.view` (`api/v1/finance/billing_documents.py:29`), module `finance`, no own rule;
  its rows show net total, total and outstanding (`billing_document_query_service._row`).
- Sales orders: `scm.dashboard.view` (`api/v1/scm/sales_orders.py:33`), module `scm`; the list is one `doc_type`
  at a time, sales orders by default (`sales_order_service.py:1467`). The header carries no money; the order total
  is summed in code (`sales_order_service._order_amount` :133), so no SO amount here.
- Customers: menu slug `order_management.customers.view` (`config/menu.config.tsx:296`), company scope only.
- Quotations (`models/projects.py:1764`) are a projects screen with `projects.projects.view_own`: wave 3.

## What changed

- Core (`app/services/assistant_registry/`):
  - `FieldDef.expr`: a field read through the module's own SQL expression (adapted onto a relation alias when
    reached through one). `FieldDef.kind` types a computed field.
  - `EntityDef.compute` + `window_field`: a computed entity. `computed.run_computed` checks every name in the spec
    first (a refusal costs no computation), turns filters on the window field into the date window (periods
    overlapping it; no window = the periods containing today, said in `scope_note`), calls the module's service,
    then filters, groups (buckets too), aggregates, sorts and caps in code. Same result shape as the SQL path, so
    the code-rendered table, labels and dd/mm/yyyy dates apply unchanged.
- `target_service.period_figures`: the target page's per-period figures batched over many targets, from the same
  calls `target_detail` makes. Test T2 holds every figure equal to `target_detail` for agent and dealer targets.
- Entities: `sales_target` (computed, one row per period: target, achieved, %, below target, short by, tier,
  commission, bonus, payout), `billing_document` (`sales_amount`, `agent`, `sales_type` from `invoiced_sales`;
  cancelled left out by default and said), `sales_order` (consignments out), `customer` promoted from a lookup
  (no phone, email, address or AR), `sales_agent` lookup.
- `crm_query` description: one line routing targets and commission to `sales_target`.

## Own-only targets (owner ruling 5 Nov 23:2x)

- `sales.targets.view_own`: migration `sales_0007_targets_view_own` (additive, granted to no role; an admin grants
  it to the salesperson role), in `PERMISSION_REGISTRY`.
- Rule `own_scope.sales_target_clause`: agent targets of the user's own sales agents (`own_scope.me().agent_ids`,
  through the user's linked contact); never a team or dealer target. Held with `sales.targets.view`, ignored.
- Screen (`api/v1/sales/targets.py`): list, detail, options, point ratios and the commission statement accept
  either slug; for an own-only holder the list is cut to their agents' agent targets (team and dealer tabs empty,
  company-wide summary figures zeroed) and a detail or statement of any other target answers 404.
- FE: "My targets" in the salesperson's MY WORK (`config/menu.config.tsx`); the targets page shows only the Agents
  tab to an own-only holder. Column layout already accepts `<slug>_own` (`api/v1/list_query.py:207`).
- `crm_query`: `sales_target.own_permission`/`own_clause` apply the same rule before anything is computed.
- Tests `tests/test_sales_targets_view_own.py` (written red first): own vs another agent on the list, detail and
  statement; team and dealer hidden; no slug still 403; view holder unchanged; `crm_query` own rows equal the
  screen's list; no linked agent reads nothing; the slug is registered and seeded to no role.

## Review rounds

- Security review: brand-scoped linked-user turns refused on billing_document / sales_target / sales_order
  (`EntityDef.brand_blind`); a related entity with its own list screen is a lookup (name fields only, no further
  hop) without its slug; computed path counts periods first (cap 2000), windows over two years refused, the
  service runs under the statement timeout; expression fields only on the entity itself; two-company test.
- Code review: T8 holds points (ratio missing and converted), replaced dealer and team targets equal to the page;
  engine tests E1 to E3 (truncation, sort with empty values, between, ne and booleans as SQL, window days); `null`
  in between / in refused; a date filter without a `period` window refused; `below_target` on the raw figures;
  `ratio_missing` exposed (target and % empty then); dealer subject without the ledger marker. The mutations that
  survived round 1 (replaced zeroing, points ratio, truncation, between bound, ne) now fail the suite.

## Crew pass on d430fe3c (5 Nov) and round 3

Targets and commission passed against the screens. Fixed:

1. Sales report gate. `crm_report_ask` refuses a staff member without the reveal `sales_orders.sales_report`
   (`api/v1/order_management/report_ask.py:45` GRANT, :432 staff keys, :439 granted, :448 staff decision, :460 the
   refusal), which a staff member holds through `sales.reports.view` (`contact_field_reveal_service.py:105`,
   `staff_reveal_keys` :114). The registry now reads the same keys: `query._slugs` adds `reveal:<key>` for every
   `staff_reveal_keys` entry (`assistant_registry/query.py:70`), `billing_document`'s money fields need
   `reveal:sales_orders.sales_report` and `outstanding` needs `reveal:sales_orders.outstanding`
   (`finance.py:41,49,50,53`), and every total or grouping of `billing_document` and `sales_order` needs the sales
   report reveal (`EntityDef.aggregate_permission`, `query.require_aggregate` :80, applied at :500 and
   `computed.py:304`). `crm_query` runs in process as the staff member alone, so its keys are the report's
   `staff_reveal_keys_for` over that one user. Test G1 asserts both answer the same for the same user.
2. Active customers: `customer` applies the Customers list's Active filter (`order_service.py:3740`, `is_active`)
   unless the query names `is_active`, and says "Inactive customers excluded."
3. Tokens: the entity index (hint, fields, relation name fields) is in `crm_query`'s description
   (`query_tools.entity_index`), so a question is one query call with no describe round; `loop.MAX_QUERY_CALLS = 4`
   crm_query/crm_describe calls per turn, the fifth is denied with "answer with what you have".
4. The panel table has a blank line before and after it (`query_tools.render_card`), or markdown shows raw "|".
5. Payout per agent: the `sales_target` hint says no period filter = the current periods and per agent = group by
   agent, sum payout; the default window was already today's periods (T4).

Tokens on three sample questions (OpenAI input_tokens; this round's parts measured, the rest of each call, system
prompt and MCP catalogue, taken as 18.5k so that "before" reproduces crew's measured ~77k list turn):

| Question | Before (d430fe3c) | After |
|---|---|---|
| commission payout for agent A last month | 4 calls, 79.3k | 2 calls, 39.5k |
| who is below target this quarter | 4 calls, 79.3k | 2 calls, 39.4k |
| sales last month per agent | 4 calls, 79.0k | 2 calls, 39.5k |

Per call the in-process schemas grow 662 -> 1,100 tokens (the index); one describe round saved is ~19k.

## Crew pass on 69b3b479 (5 Nov) and round 4: root causes

1. Identity gate on the agent path. An identity read (shared key + `X-Staff-User`) asks every slug of the staff
   member AND the key's act-as user (`user_service.gate_user_ids`, used by `report_ask.py:432`), so the dev act-as
   user without the sales report reveal refused a staff member who holds it. The act-as half stays for anyone else
   holding the key; the backend's own panel agent now proves who it answers: `app/services/staff_proof.py` (HMAC over
   staff id + expiry, key derived from JWT_SECRET under its own label, 60 seconds), sent by the panel MCP client as
   `X-MCP-Staff-Proof` (`ai_assistant_service.MCPRuntimeClient._headers`), stripped by the MCP server from a caller
   without the bearer token (`auth.AUTHENTICATED_ONLY_HEADERS`), relayed as `X-Staff-Proof` only beside a forwarded
   `X-Staff-User` (`scope.forwarded_staff_proof`, `http_client`), verified in `dependencies._apply_staff_identity`
   (`staff_proven`), after which `gate_user_ids` is the staff member alone. A proof never grants what the staff
   member lacks; a wrong, expired, tampered or other-staff proof changes nothing (`tests/test_staff_read_identity.py`).
   A panel 403 now says to try `crm_query` (`tools.PANEL_ROUTE_REFUSED`) instead of "do not get this another way":
   `crm_query` runs in process as the user under the same reveal rule, so it is no side door. Contact turns unchanged.
2. Customers of an agent: the Customers list links an agent by `Customer.sales_agent_id`
   (`order_service._build_customer_list_query`, the agent's Customers tab `api/v1/master_data/sales_agents.py:156`)
   and Active is `is_active` (`order_service.py:3740`). Both were already the registry's; the model filtered
   `agent.code` with a NAME ("Agent A") and found none. `customer.agent` is now one field "CODE - Name" (the screens'
   `agent_label`), matched with contains on either.
3. Tokens. Measured on the real loop with a scripted model and the real MCP catalogue (in process, 55 tools, the
   admin-like user gets 24): every call carries system 1.6k (the fallback prompt here) + MCP tool schemas 17.2k +
   in-process tools 4.5k; tool results in history are 0.2k to 1.9k. So the bulk is the tool block resent on every
   call, not old results. `loop.narrow_after_query`: after a round of only crm_query / crm_describe in which one
   answered, the next rounds carry only those two, `answer` and `plan`. Rows without `fields` show the entity's
   `list_fields`, not all 22 columns.
4. Tables: agent replies render through `components/chatbot/WhatsAppBlocks.tsx` (`AIAssistantBubble.tsx:778`, any
   reply with `metadata_json.route`), which had no table support, so the blank line could not help. It now renders a
   GFM table (header, separator, rows) as a real table.
5. Payout per agent: no period filter reads the periods containing today (test P1: October only, 180 each).

Tokens per turn (gpt-4.1 tokenizer; same scripted calls on 69b3b479 and on this head):

| Question | path | before | after |
|---|---|---|---|
| commission payout per agent this month | query, answer | 46,958 | 26,968 |
| commission payout per agent this month | describe x2, query, answer | 96,680 | 36,694 |
| who is below target this quarter | query, answer | 47,288 | 27,067 |
| who is below target this quarter | describe x2, query, answer | 97,010 | 36,793 |
| sales last month per agent | query, answer | 47,004 | 27,014 |
| sales last month per agent | describe x2, query, answer | 96,392 | 36,478 |
| active customers of agent A | query, answer | 46,905 | 26,915 |
| active customers of agent A | describe x2, query, answer | 95,373 | 35,343 |

## Crew pass on 74b6b751 (5 Nov) and round 5

- (a) One sales basis per answer. The description says sales with no basis named are invoiced (billing_document, one
  query for the table and its total; owner rule: invoiced first, ask when unclear) and delivery orders only when DOs
  are asked. Every billing total says its basis ("Invoiced sales (invoices + cash sales + debit notes - credit
  notes, by document date)."). The loop refuses a second money total on the other basis in the same turn
  (`query_tools.money_basis`, `mixed_basis_refusal`; test SB3 through the real loop).
- (b) (e) `agent_target`: one row per agent (agent targets only) over the window, the sum of `sales_target`'s own
  period figures (target, achieved, commission, bonus, payout; % by `achievement_service.achieved_pct` over the
  sums). "Payout per agent" and "Agent A last month" are one query; dealers and team targets stay out.
- (c) `agent` on `sales_target` and `agent_target` is "CODE - Name", so a name matches; `agent_code` stays. A text
  filter that matches nothing returns `values_in_window` and the instruction not to show or total other records.
- (d) At most 8 columns per row result (`query.MAX_COLUMNS`), the rest named in `columns_dropped`.
- Calls: `loop.MAX_QUERY_CALLS` 3.

Tokens per turn on this head (real loop, scripted model, real MCP catalogue; one query then the answer):

| Question | Calls | Turn | Call 1 | Call 2 |
|---|---|---|---|---|
| sales last month per agent | 2 | 27,382 | 23,545 | 3,837 |
| payout per agent | 2 | 27,340 | 23,544 | 3,796 |
| commission payout for Agent A last month | 2 | 27,386 | 23,547 | 3,839 |
| who is below target this quarter | 2 | 27,382 | 23,546 | 3,836 |
| active customers of Agent A | 2 | 27,285 | 23,545 | 3,740 |

Call 1 = system 1.6k + MCP tools 17.2k + other tools 4.6k; call 2 carries only the registry tools (1.8k). Worst case
with the cap: one full call and three narrowed ones, about 38k.

## Crew pass on 0463b805 (5 Nov) and round 6: one deterministic target entity

- `agent_target_summary` (`assistant_registry/sales.py` `_summary_rows`) replaces `agent_target`: one row per owner
  per period, from `_target_rows` (the target page's own period figures), nothing recomputed but sums and counts.
  Owner = the target service's own rule for a salesperson's view (`target_chat_scope`): an agent target is its
  agent's, a dealer target is the agent's who owns every counted account (`Customer.sales_agent_id`, else
  "(no single agent)"), a team target the team's. Columns: targets, below_target (count), target, achieved, %,
  payout; a totals row over every matching row (`EntityDef.row_totals`). It is the only target entity in the
  index (`EntityDef.in_index`); `sales_target` stays for one named target through crm_describe.
- Below target is the Targets screen's own reading (`sorento_crm_frontend/app/(protected)/sales/targets/components/
  SalesTargetsView.tsx:389`: reached = `pct !== null && pct >= 100`, the % from `achievement_service.achieved_pct`
  :898, one decimal). Round 2 had used achieved < target, which counts a target of 0 (no %) as reached: the dev
  copy's 3 agent targets of 0 and similar rows are the 62 vs 66 gap. `sales_target.below_target` and the summary
  use `_below` now; test S3 holds the summary's below total = `sales_target`'s count = the count read from
  `target_detail` the screen's way.
- Tokens, one query then the answer: payout per agent 27,255; commission for Agent B last month 27,323; below
  target this quarter 27,320 (2 calls each).

## Token measurement (task item 5)

OpenAI `responses/input_tokens` (gpt-4.1 tokenizer), counting only:

- Tool schemas (`crm_query` + `crm_describe` as one JSON payload), paid on every model call: 649 before, 662
  after: **+13 tokens per call** (the routing line). The entity list is not in any schema or prompt.
- `crm_describe()` index, paid only when the model calls it: 90 before, 181 after (+91, eight queryable entities
  for a holder of every slug).
- `crm_describe(entity)`, on demand: sales_target 699, billing_document 471, sales_order 268, customer 126.
- Offer rule: `query_tools.ANY_ENTITY` now also includes `sales.targets.view`, `finance.billing_documents.view`,
  `order_management.customers.view` and `scm.dashboard.view` (scm was already there), so a user holding only one
  of those is newly offered the two tools (~660 tokens per call for that user).

## Tests

`tests/chatbot/agent/test_ai_tools_wave2.py` (no LLM): T1 commission payout for one agent last month, T2 every
figure equals the target page, T3 below target, T4 default window and its note, T5 payout per agent grouped,
T6 slug only (no own-only path), T7 refusals before compute; B1 sales = IV + CS + DN - CN by DocDate cancelled out
and equal to `invoiced_sales`, B2 per agent, B3 cancelled on request + slug; S1 sales orders; C1 customers.
`test_ai_query_core.py::test_Q12` extended for expression and computed fields.

## Eval prompts (for crew's live run on the dev copy)

1. "Commission payout for agent <CODE> last month" -> `sales_target`, agent eq, period between, `payout`.
2. "Who is below target this quarter?" -> `sales_target`, period between the quarter, `below_target` true.
3. "Total commission per agent this year" -> group_by agent, sum payout.
4. "What tier did <dealer> reach in Q3?" -> `sales_target` rows with `tier_reached`.
5. "Sales last month per agent" -> `billing_document`, doc_date between, group agent, sum sales_amount, note
   "Cancelled documents excluded."
6. "Sales orders of <customer> this month" -> `sales_order` rows.
7. "How many active customers does agent <CODE> have?" -> `customer`, agent.code eq, is_active true, count.

## Next wave (3)

Listed in a crew-note when wave 2 is handed off: stock / inventory balances, AR outstanding, quotations and
projects (own rule `project_clause`), opportunities (own rule `opportunity_clause`).
