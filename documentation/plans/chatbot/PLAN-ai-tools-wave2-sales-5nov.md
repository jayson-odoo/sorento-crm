# PLAN: AI-TOOLS-WAVE2 (sales modules in the assistant registry)

Status: Build done, tests green locally; waiting on review. Track: full (multi-entity RBAC, no migration).
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
  slug. Crew ruling 5 Nov: the entity mirrors the screen exactly (option b); own-only for salespeople is an owner
  question for later, not this wave.
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
