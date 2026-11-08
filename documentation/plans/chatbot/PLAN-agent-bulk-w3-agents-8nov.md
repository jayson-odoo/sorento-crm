# PLAN: agent bulk wave 3, sales agent -> customers from a pasted table (AGENT-BULK-W3-AGENTS)

Status: Merge-ready pending crew live run (laneboard/scripts/2253.md) + router gate; PR #2253, reviewer READY after fix round 1 (pick check by row number, hidden-company guards); fix round 2 (crew live x3: a partial answer kept other rows waiting) applied. Track: full (agent write path; no migration, no new permission, no new ingest surface).

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

## Behaviour card (one write, `crm_customer_agent`, batchable; as built after crew answers + dev data)

A row = company (optional) + customer code and / or name + the agent it should be under. Slug
`master_data.sales_agents.edit` (same as the route). Reads under every company the user is granted.

- **Company**: a code the user may see; any other is Not changed `No company "X"`.
- **Customer**: exact customer code (case and spaces aside), read in the row's company (2470 codes exist in both
  companies on dev); a code two companies hold and no company given -> "give the company". Inactive -> Not changed
  `Customer "X" is inactive.` A name only needs the company and always WAITS with that company's ACTIVE accounts whose
  name contains it (max 10), even one; picked by chat reply.
- **Agent**: an exact code first; a code is never matched by containment (tier codes contain each other, `X I` sits
  inside `X III`). Then an exact person name (`person_label`, else `description`): one agent is that agent, several
  (one person holds a code per tier, 3-5 on dev) WAIT. Otherwise the active agents whose NAME contains the text wait
  (max 10); none -> `No sales agent named "X"`. Inactive -> `Sales agent "X" is inactive.` An agent of another company
  than the customer's (the route's own `_resolve_sales_agent` rule; every dev agent is shared, so it never fires
  there) -> `"X" is a <co> agent`, naming only companies the user sees.
- **Already on that agent** -> Not changed `Already under X; nothing to change.`
- **Ready row**: `agent <old or none> -> <new>`; for a company whose `sales_agent_source` is `customer` (read from
  the company; both dev companies are `document`) it adds `Past invoiced sales of this customer move to <new> (RM n in
  the last 12 months)`, the sales reports' figure (`invoiced_sales.posted` / `signed_amount`, Malaysia date).
- **Pick check**: a picked code must be one the last table listed for that row (found by the row key, else by the
  table row number, since a pick may change the customer fields the key is built from) or typed by the user. The
  text a row is still waiting on, re-sent unchanged when the user answers only other rows, is not a pick: that row
  waits again (crew live fix round 2).
- **Confirm**: per row, recheck the customer's agent is still `before`, then `assign_sales_agent_many([c], agent)`
  (the route's checks), audit = the listener's customer row + one `customer.sales_agent_agent` row. CRM only; no
  AutoCount write. Assign only: a row asking to clear an agent is not understood as clearing (it reads as an agent
  name, so `No sales agent named "none"` or "Name the sales agent"); clearing stays on the customer form.

Dev examples (crew-data-request answered 8 Nov, agent names masked by crew):

| # | Pasted row | Result |
|---|---|---|
| E1 | `MCH / 300-Y031 / <its current agent AGENT A - I>` | Not changed: Already under AGENT A - I |
| E2 | `SRT / 300-T009 / AGENT C I` (now AGENT D I) | Ready: agent AGENT D I -> AGENT C I |
| E3 | `SRT / YEE TAT HARDWARE / AGENT C I` | Needs your choice: SRT 300-Y045, 300-Y046 only (never the 3 MCH Yee Tat accounts) |
| E4 | `MCH / 300-H100 / <AGENT B's person name>` | Needs your choice: the 5 AGENT B codes |
| E5 | `SRT / 300-H100 / AGENT C I` | Not changed: Customer "300-H100" is inactive |
| E6 | MCH set to `customer`: `MCH / 300-Y031 / AGENT C I` | Ready + "Past invoiced sales ... (RM 27,121.69 in the last 12 months)" |

## Scope note (crew live, 8 Nov)

The agent reads and writes under every company the user is granted (`grants_scope`, the #2241 rule), so one table
can hold MCH and SRT rows. The screen route `POST /master-data/sales-agents/{id}/customers` reads under the ACTIVE
company only: putting MCH 300-H100 back through that route while SRT is active answers 404. That is the route's
existing behaviour and is intended here; switch the active company (or use the customer form) to undo by hand.

## Crew answers (8 Nov)

Q1 (a) CRM only, no AutoCount write. Q2 (a) allow, with the Ready-row warning and the 12-month RM, conditional on the
company's actual `sales_agent_source`. Q3 (a) assign only.

## UAC

See `agent-bulk-w3-agents-8nov-acceptance-criteria.md`.
