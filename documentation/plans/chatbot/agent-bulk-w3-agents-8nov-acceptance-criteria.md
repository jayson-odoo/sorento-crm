# UAC: agent bulk wave 3, sales agent -> customers from a pasted table (AGENT-BULK-W3-AGENTS)

Plan: `PLAN-agent-bulk-w3-agents-8nov.md`. Test numbers in brackets are the pytest names in
`sorento_crm_backend/tests/chatbot/agent/test_agent_bulk_w3_agents.py`.

- T1 (01) `crm_customer_agent` is a batchable WriteDef, slug `master_data.sales_agents.edit` (the Customers tab's
  route); `crm_batch_propose` offers it only with the slug; without it a call is denied. Tool label "assign sales
  agents to customers".
- T2 (02) A row = company (optional), customer code and / or name, agent. Exact customer code (case and spaces
  aside) + exact agent code or person name -> Ready `agent <old or none> -> <new>`; the cells read
  `# | Customer | Name | Will change`, Name = the CRM name ("(table says X)" when it differs). Confirm moves the
  customer through `CustomerService.assign_sales_agent_many`, the customer listener writes its audit row, plus one
  `customer.sales_agent_agent` row.
- T3 (03) No fuzzy matching. Agent: an exact code first, and a code is never matched by containment ('X I' never
  picks 'X III'). Next, an exact person name: one agent = that agent; several (the per-tier codes) = the row waits
  with them. Otherwise the active agents whose NAME contains the text wait as a pick (max 10). Customer: a name-only
  row waits with the row's company's active accounts whose name contains it, even one. A pick is a chat reply; a
  picked value that was not listed, not exact in the row and not typed by the user this turn is Not changed.
- T4 (04) Not changed, every reason listed: `No company "X"` (unknown or not visible), `No customer with the code "X" in your companies`, a customer of
  another company than the row names, a code two companies hold and no company given ("give the company"), a
  name-only row without a company, an inactive customer, `No sales agent named "X"`, `Sales agent "X" is inactive`,
  an agent of another company, no code and no agent ("Give the customer code; Name the sales agent"),
  `Already under X; nothing to change.`, the same customer twice ("Same as row N.").
- T5 (05) A company whose `sales_agent_source` is `customer` adds to the Ready row "Past invoiced sales of this
  customer move to X (RM n in the last 12 months)" (posted invoices / cash sales / debit notes less credit notes,
  the sales reports' figure); a `document` company shows no such line.
- T6 (06) Confirm rechecks each row: a customer moved on screen since the preview, or an agent retired since,
  fails that row alone; the other rows still apply.
- T7 (07) The reply carries the code-built tables; the waiting table's pick column says "Agent" for agent picks
  ("Account" for customer picks) and the closing line asks for the agent code (customer code); grant and tag
  wording unchanged.
- T8 (08) A Not changed `No sales agent named "X"` backs the reply's "no sales agent named X" wording.
- T9 (09) No AutoCount write: the write imports no AutoCount module (crew Q1 (a)). Clearing an agent is not offered
  (crew Q3 (a)).

## Fix round 1 (reviewer, 8 Nov)

- R1 A pick that changes the row's key fields (drops the customer name, adds a company) is still checked against the
  list that row number showed; an unlisted, untyped pick is Not changed (`batch._not_listed` falls back to the row
  number).
- R2 Inactive accounts are never offered as a customer pick.
- R3 A company the user may not see is `No company "X"`; the other-company agent message never names a hidden company.
- R4 The 12-month window uses Malaysia's date.
