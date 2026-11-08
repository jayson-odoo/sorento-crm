# PLAN: agent bulk wave 3, sales agent -> customers from a pasted table (AGENT-BULK-W3-AGENTS)

Status: Step 1 done (mapping + behaviour card); waiting on crew answers Q1-Q3 and the dev examples (crew-data-request on #2253). Track: full (agent write path; no migration, no new permission, no new ingest surface).

Wave 3 after AGENT-BULK-W2-TAGS (#2247). Owner wave order (8 Nov): 2 contact tags (#2247), 3 sales agent ->
customers (this lane), 4 contact edits keyed by phone, 5 product fields, 6 supplier fields.

## Step 1: the assignment path today (main @ eeca809d, file:line)

Paths are under `sorento_crm_backend/app/`.

1. **Route.** `POST /master-data/sales-agents/{id}/customers` (`api/v1/master_data/sales_agents.py:181`), slug
   `master_data.sales_agents.edit` (`sales_agents.py:185`). Each customer read with
   `contact_customer_service.get_customer_in_scope` (hidden = 404), then
   `CustomerService.assign_sales_agent_many` (`services/order_service.py:3926`): all or nothing; a customer already
   on that agent is skipped; each pair checked by `_resolve_sales_agent` (`order_service.py:3801`): unknown agent,
   an agent of ANOTHER company than the customer's own (shared agents, `company_id IS NULL`, always fit) and an
   inactive agent are 422. The customer form (`order_service.py:3905`) uses the same check.
2. **Audit.** `Customer` lists `sales_agent_id` among its audited fields (`models/order.py:121`); the audit
   listener writes the before / after row on flush, for the form and the bulk route alike.
3. **Who reads a customer's agent (the side effects of a move).**
   - **Sales credit, commission, leaderboard.** `sales/invoiced_sales.py:128` `agent_id()`: for a company whose
     `companies.sales_agent_source = 'customer'` (`models/company.py:41`, "Mocha's"), every invoice belongs to the
     customer's CURRENT agent, so a move re-credits that customer's whole history to the new agent
     (`sales/achievement_service.py:706`, `leaderboard_service`, commission via achievement). For `document`
     companies (Sorento, the default) the invoice keeps its own agent; a move changes no past figure.
   - **A salesperson's book / access.** `contact_asker.own_book` (`contact_asker.py:139`), the portal debtor
     dropdown (`models/order.py:173`), the chatbot's sales-target scope (`sales/target_chat_scope.py:162`: which
     dealer targets a salesperson sees = customers on their agents), opportunities own-agent gate
     (`chatbot/agent/writes.py:654`), stock asks (`stock_ask_service.py:385`), access grants of own customers
     (`chatbot/agent/writes.py:964`). All read live, so a move hands the customer to the new agent at once.
   - **Dealer targets** are keyed by customer, not agent: the target stays; who SEES it follows the agent (above).
   - **AutoCount.** No CRM -> AutoCount customer write exists (grep `app/` for a debtor push: none), and no AutoCount
     ingest sets `customers.sales_agent_id` (`customer_import_service.py` has no agent column; the DO pull compare
     skips Agent by ruling, `autocount_pull_compare.py:531`). The customer's agent is CRM-owned today; a move here
     is not overwritten by a sync and is not sent anywhere.

## Reused from #2241 / #2247 / #2250

`chatbot/agent/batch.py` (`crm_batch_propose`, Ready / Needs your choice / Not changed, `_not_listed`, decided
cards), `chatbot/agent/writes.py` `WriteDef(batchable=True)`, `chatbot/agent/actions.py` (Confirm card, per-row
transaction + recheck), `chatbot/agent/contact_grant._customers` (customer by exact code, else contained-name
candidates of the row's companies).

## Behaviour card (one write, `crm_customer_agent`, batchable)

A row = one customer + the agent it should be under. Slug `master_data.sales_agents.edit` (same as the route).

- **Customer**: by exact customer code (case and spaces aside) in the row's company; a name only -> the row WAITS
  with that company's active customers whose name contains it (max 10), picked by chat reply; nothing auto-picked.
  Not found / another company's / hidden -> Not changed with the reason.
- **Agent**: exact agent code (`sales_agents.sales_agent`) or exact name (`person_label`, else `description`),
  case and spaces aside, among agents that fit the customer's company (own company or shared). Not exact -> WAITS
  with the agents whose code or name contains it (max 10). None -> Not changed "No sales agent named X".
  Inactive -> Not changed "Agent X is inactive". Another company's agent -> Not changed "X is a <co> agent".
- **Already on that agent** -> Not changed "Already under X; nothing to change."
- **Ready row** shows `Agent: <old or none> -> <new>`; for a `customer`-source company it adds
  "Past invoiced sales of this customer move to <new> (this company credits the customer's current agent)."
- **Confirm**: per row, recheck the customer's agent is still `before`, then `assign_sales_agent_many([c], agent)`
  (the route's own checks), audit = the listener's customer row + one `customer.sales_agent_agent` row naming
  the agent table. CRM only; no AutoCount write.

Examples: real masked dev rows requested from crew (crew-data-request on #2253); shapes until then.

| # | Pasted row | Result |
|---|---|---|
| E1 | `SRT / 300-A001 / agent SEAN` (now under JOHN) | Ready: Agent JOHN -> SEAN |
| E2 | `MOC / 300-M010 / agent LISA` (Mocha, customer source) | Ready: Agent none -> LISA; past sales move with it |
| E3 | `SRT / Ace Hardware / agent SEAN` (no code) | Needs your choice: the Ace accounts of SRT; reply "row 3: 300-A044" |
| E4 | `SRT / 300-A001 / agent SEAN` (already) | Not changed: Already under SEAN; nothing to change |
| E5 | `SRT / 300-A002 / agent OLDBOY` (inactive) | Not changed: Agent OLDBOY is inactive |

## Questions (crew-ask on #2253)

- Q1 AutoCount: (a) CRM only, no write (nothing ships, so no switch needed), recommended because the field is
  CRM-owned today (above); (b) build an AutoCount debtor-agent write behind the admin switch, OFF (new lane).
- Q2 `customer`-source companies (Mocha): (a) allow, Ready row warns that past sales move, recommended (same as the
  screen today); (b) refuse those rows here.
- Q3 Clearing an agent ("no agent"): (a) not in this wave, Not changed "Clearing an agent is done on the customer
  form", recommended (one write = assign); (b) allow clearing.

## UAC

To follow once Q1-Q3 are answered: `agent-bulk-w3-agents-8nov-acceptance-criteria.md`.
