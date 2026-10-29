# PLAN: Agentic phase 1 - read-only agent branch for complex staff turns

Status: Plan. Behaviour card revised on the crew dev-DB measurement (rule now on `asks` + linked user); posted for owner answers (crew-ask on PR #1982); build waits on them. Track: full
lane (a migration for the per-contact switch, a new contact-settings field). Lane AGENTIC-P1, branch
`claude/agentic-crm-chatbot-p1-fhvvb0`, base origin/main ec29a81c.

Parent: `PLAN-agentic-crm-29oct.md` (components 1, 4, 8). P0 (#1979, c9ff4958c9, on main) keeps Gemini thought
signatures / Claude thinking across tool rounds and passes reasoning effort.

## Owner rulings this lane carries (29 Oct ~22:45)

- R1: today's parser -> lane path stays the default and is NOT changed. The agent is a separate branch that steps
  in only when a turn is complex.
- R2: Claude-Code-style loop: plan, call typed tools, read results, iterate, answer. No model-written SQL;
  analytics go through the typed query builder and the one report service.
- R3: every read is limited by BOTH the linked user's permissions AND the contact's chatbot scope; never wider
  than today.
- R4: Gemini Flash (not lite). Crew prices the P1 eval and asks the owner for that budget.
- R5: one confirmation per write action later; P1 is read-only, so no writes at all.

## Behaviour card

### 1. The hand-off rule: when a turn goes to the agent

Decided from the parser's own verdict fields (semantic, already emitted today). No word lists, no regex on the
message, no prompt change.

**Measured on the dev DB by crew (29 Oct, read-only):** `chatbot_profile.tier` is null on every contact, so
`is_staff_profile` (`turn/state.py:259`) is false for all of them; and `sub_asks` is never filled (null on every
turn since 13 Oct, an empty list on 31). The verdict's older `asks` list (`head/parser.py:472-482`, one
`{domain, intent}` per domain asked) IS filled: 102 turns with two or more in a month. The rule is therefore
built on `asks` and the linked user, not on `sub_asks` or the tier. (Side finding for the owner: the multi-ask
runner, `engine.py:7287-7300`, is gated on both of those, so it cannot fire on this data.)

A turn goes to the agent when ALL of these hold:

1. The contact's agent switch is on (section 3) and the contact has a linked active user
   (`users.respond_contact_id`, `app/models/user.py:74`). The linked user is the staff test (Q3).
2. The turn is one the business lane would answer: `branch_kind == "business_query"`, it completes here, no
   customer-scope refusal, not a stock-availability-only contact (the runner's own guards minus the tier check,
   `engine.py:7287-7300`). A refusal, an escalation, a casual or a `not_supported` turn never reaches the agent
   (R3: the agent cannot reopen a domain the owner turned off).
3. And one of:
   - **H3, several asks with no product subject.** `asks` has two or more domains and the verdict carries no
     product entity (the subject is a supplier, a brand plus a category, a customer, or the previous reply).
     Today these drop to a one-domain answer or a not-found line. 11 of the 68 linked-user multi-ask turns
     in the dev month; three of the five real failures in section 7.
   - **H1, several asks about a product, beyond the stock + incoming pair.** `asks` has two or more domains, a
     product entity is present, and the domain set is not just {`inventory`, `incoming`}. That one pair is
     exempt because crew measured it is the common routine turn and today's path answers it well (Q1). Two of
     the five real failures in section 7.
   - **H2, a follow-up of an agent answer.** The previous turn was answered by the agent and this turn's
     decision (`turn/decide.py:41-44`, on `plan.trace.decision`) is REFINE, ANSWER or CARRY (it keeps the standing
     subject), with no `topic_reset`.
   - When a later prompt does fill `sub_asks`, a `measure == "other"` ask (the runner's "not available yet" arm,
     `turn/sub_asks.py:709-715`) also counts as H1. Not relied on in P1.

**Chained asks, plainly.** No parser field says that one ask depends on another's result: `asks` items are
`{domain, intent}`, `sub_asks` items carry no subject, and entities belong to the turn. P1 does not detect a
chain as such. Chains reach the agent through H3 (no product subject) or H1 (a product plus a domain beyond
stock/incoming). A chain inside the exempt stock + incoming pair stays on today's path. The smallest honest
signal for chains is one per-ask field (`uses_result_of: <index> | null`) on an agent-only parser label; not
proposed for P1.

Seam: one new `if` right BEFORE the multi-ask runner block (`engine.py:7287`). Every other turn falls through to
today's code with zero changes.

### 2. How the agent returns to the normal path

- Not sticky beyond H2. Each turn re-runs the rule. A NEW_ASK the normal path serves, a `topic_reset`, or any
  non-business branch goes back to today's path at once.
- Fail-safe: if the agent cannot answer (provider error, no approved agent model/key, budget spent before any
  tool result, the number check in Q2 fails), the turn falls through to today's path unchanged, and the trace says
  why. No silent fallback to the parser's lightweight model for the agent role.
- Agent memory between turns: a small `agent_frame` on the existing session state (objective, the reply it gave,
  the tool calls and arguments it made). No new table in P1: nothing is written, so no action ledger is needed.

### 3. The per-contact switch (staff only first)

- New column `respond_contacts.chatbot_agent_enabled` boolean, default false (migration). Edited through the
  existing partial update `PUT /api/v1/user-management/contacts/{id}/chatbot` (same pattern as
  `chatbot_files_as_links`, `api/v1/user_management/contacts.py:473,530`), one switch in Contact Details >
  Chatbot via `contactChatbotService.ts`.
- Effective only when the contact has a linked active user (the staff test, Q3). The existing AI replies gate
  (`chatbot_allowed`) stays authoritative. Turning it on grants no data access of its own.
- Agent model: its own prompt label `chatbot-agent` in the prompt registry (provider/model per key
  `ai_prompt_registry.py:1576`, effort `:1601`), seeded to Gemini Flash. Independent of the per-contact parser
  model ladder.

### 4. The typed tools in P1 (read-only)

A short explicit table, not the whole catalogue. Every tool is already on the chatbot's read-only allow-list
(`lanes/business/fetch.py:1475`) and is called through the existing seam `services._mcp_call(db)`
(`lanes/business/services.py:228`), which refuses non-read tools and applies the contact's brand scope.

| Tool | What it reads |
| --- | --- |
| `crm_report_ask` | The one report service: rank or total sales / outstanding by any one dimension and period (`api/v1/order_management/report_ask.py`) |
| `crm_inventory_stock_balance_list` | Stock on hand by product/location |
| `crm_incoming_stock_by_product` | Incoming quantities and ETAs |
| `crm_procurement_grn_summary`, `crm_procurement_po_last_cost_list`, `crm_procurement_spo_allocations_last_receipt_list` | Received qty, supplier / last cost, last receipt |
| `crm_procurement_po_placed_list` | POs placed, by supplier / product (supplier field gated on `purchase_orders.supplier`) |
| `crm_incoming_stock_shipments` | Shipment headers and allocation signal |
| `crm_order_management_orders_by_product_list` | SO / DO lines and outstanding by product |
| `crm_master_products_list`, `crm_lookup_resolve` | Turn a name, code, brand or category into ids |

Scope, both sides (R3):

- Contact scope: every call carries the contact's `contact_id` + `space_id`; the routes apply customer scope,
  reveal grants, audience and stock-location policy from it (as `report_ask.py:1-9` documents), exactly as for
  today's turns. The table also carries each tool's reveal grant (the runner's `GRANT` map,
  `turn/sub_asks.py:76`) and the dispatcher refuses when the contact lacks it.
- User permissions: each table row names the permission slug its route requires; the dispatcher checks the
  linked user holds it before the call. A refused call returns a typed `denied` result to the model, which says
  so in the answer.
- Dispatch accepts only names in this table (not every catalogue entry) and validates arguments against the
  tool's schema; ids the model passes must come from an earlier tool/lookup result in the same task.

### 5. Latency and cost guard

- Target p95 <= 8 s for an agent turn, measured in the eval.
- Hard caps: 4 tool rounds, 3 calls per round, one wall-clock deadline of 8 s; each MCP call's timeout is
  min(remaining budget, `chatbot_mcp_timeout_seconds`=10, `app/config.py:203`). Tool results fed back to the model
  are summarised to a fixed size, never silently cut mid-row (paged with a "more" count).
- Per-turn token and cost usage recorded on the trace (provider usage, as the parser does).

### 6. The eval: agent vs today on the same complex cases

- Same cases, two arms on the crew test copy: arm A switch off (today's path), arm B switch on. Each case has
  3 paraphrases (one Malay or Chinese), 3 repeats per arm.
- Graded on the end state of the answer: each expected figure is computed independently by SQL on the test copy
  and must appear correctly; plus "said what it could not answer" honesty. Also recorded: latency p50/p95, tool
  rounds, invalid or denied tool calls, tokens and cost per turn.
- Uses the existing eval engine (`scripts/chatbot_eval/engine.py`, dry-run console turns). CI uses cassette
  tests only (recorded provider responses, no paid calls).
- Pass bar proposed: arm B correct on at least 80% of case-runs where arm A is wrong or partial, no regression on
  the H2 follow-ups, p95 <= 8 s, zero scope violations.

### 7. Complex turns today's path answers badly

Crew pulled these from the shared dev DB read-only and masked them (29 Oct). The rows themselves are NOT
committed (public repo); below are paraphrases only. Fixtures and eval cases use seeded fakes.

| # | Paraphrase | Parser saw | Today's reply | Hand-off | Tools the agent needs |
| --- | --- | --- | --- | --- | --- |
| 1 | One product code, six asks in one message: received this year, supplier, purchase price, last receipt date, total sold this year, sold per salesperson this year | 3 domains (incoming, purchase cost, order), product | Tens of thousands of characters of raw lists; four of the six asks unanswered, the other two buried | H1 | GRN summary, last receipt, last cost, report-ask (sold total; group_by sales_agent) |
| 2 | Total purchased and delivered this year from one supplier, named by a short name | 2 domains (PO, order), the supplier read as a customer, no product | A no-match line, a date-range limit notice and a not-found line; nothing asked was answered | H3 | supplier lookup, PO placed list, delivered report |
| 3 | A brand plus a product category: stock and ETA | 2 domains (stock, incoming), brand + category, no product | A not-found line for the category, then an escalation offer | H3 | category lookup to products, stock balance, incoming by product |
| 4 | Reply to the bot's own incoming list: is this pending allocation for a project or a dealer? | 2 domains (incoming, order), no entity | The incoming list repeated plus 20 unrelated delivery orders; the question unanswered | H3 (and H2 once the list itself comes from the agent) | incoming shipments (allocation signal), orders by product; an honest "not allocated to any order yet" when that is the fact |
| 5 | One product: dealer outstanding and stock | 2 domains (stock, order), product | Stock shows 1 outstanding, the order part reports none outstanding because it read deliveries only | H1 | stock balance, orders by product (SO outstanding) or report-ask basis outstanding by customer |

Note on case 3: the reply ended in an escalation offer, so its `branch_kind` may not be `business_query`; if so,
guard 2 keeps it on today's path. Phase 2 checks the recorded branch before counting it.

## Delivery after owner answers

Red-first. Tester writes failing tests first: hand-off predicate (H1/H2/H3 on `asks`, the stock + incoming exemption, every exclusion), switch PATCH and
effective rules, dispatcher allow-list / grant / permission refusals, budget caps, fall-through on failure,
cassette loop tests for Gemini with thought signatures. Coder makes them green. Reviewer + security reviewer
(the diff touches permission gating). Crew runs the paid eval.
