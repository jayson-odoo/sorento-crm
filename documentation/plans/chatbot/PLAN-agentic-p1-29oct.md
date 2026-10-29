# PLAN: Agentic phase 1 - read-only agent branch for complex staff turns

Status: Plan. Behaviour card posted for owner answers (crew-ask on PR #1982); build waits on them. Track: full
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

A turn goes to the agent when ALL of these hold:

1. The contact's agent switch is on (section 3), the contact is staff (`is_staff_profile`,
   `turn/state.py:259`) and has a linked active user (`users.respond_contact_id`, `app/models/user.py:74`).
2. The turn is one the business lane would answer: `branch_kind == "business_query"`, it completes here, no
   customer-scope refusal, not a stock-availability-only contact. These are the exact guards the multi-ask runner
   uses today (`engine.py:7287-7300`), so a refusal, an escalation, a casual or a `not_supported` turn never
   reaches the agent (R3: the agent cannot reopen a domain the owner turned off).
3. And one of:
   - **H1, asks no lane can serve.** The parser named two or more asks (`sub_asks`, parser schema
     `head/parser.py:497-516`) and at least one of them is one the runner answers with "not available yet":
     `measure == "other"`, or `sold_by` with a `group_by` outside the runner's axes. That is the runner's own
     NOT_AVAILABLE arm (`turn/sub_asks.py:709-715`), computed with the same predicate, so the agent takes exactly
     the turns today's path already admits it cannot answer. The predicate reads the verdict only; it does not
     depend on the runner having placed a product.
   - **H3, a multi-ask with no product for the runner to anchor on.** The parser named two or more asks and the
     verdict carries no product entity. Today the runner returns None for exactly this case
     (`_scoped_products` empty, `turn/sub_asks.py:291-293`) and the turn drops to the one-domain path, so
     only part of it is answered. This is where chained asks live ("top 3 customers for brand X last month and
     their outstanding DO": the subject is customers and a brand, not a product).
   - **H2, a follow-up of an agent answer.** The previous turn was answered by the agent and this turn's
     decision (`turn/decide.py:41-44`, on `plan.trace.decision`) is REFINE, ANSWER or CARRY (it keeps the standing
     subject), with no `topic_reset`.

**Chained asks, plainly.** No parser field says that one ask depends on another's result. A `sub_asks` item is
`{measure, group_by, date_from, date_to, basis, label}` (`head/parser.py:497-516`), and entities belong to the
turn, not to an ask. So P1 does not detect a chain as such. A chain reaches the agent only through H3 (no
product subject) or H1 (a part the measure list does not cover: "outstanding DO" is not a measure, so the
addendum tells the parser to label it `other`, `chatbot_parser_prompt.py:884-895`; the eval measures how
reliably it does). A chain whose parts are all runner measures over one product ("stock of X and who bought most
of it") is answered part by part by today's runner, and that is out of P1. The smallest honest signal for those
chains is one per-ask field (`uses_result_of: <index> | null`) on the agent-only parser label of Q1 (b); it is
not proposed for P1.

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
- Effective only when the contact is staff AND has a linked active user. The existing AI replies gate
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
| order / delivery status list tool of the order domain (exact name pinned in Phase 2 from `default_policy()`) | SO / DO status |
| product / customer lookup through the existing resolver | Turn a name or code into ids |

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

The sandbox has no access to the dev DB (crew contract), so the 3 to 5 real turns are pulled by crew with the
query below (read-only; crew masks names, phones and prices before posting back). The verdict is the
`understood` stage's `raw.derived` (`engine.py:5468`); `contact_respond_id` is the Respond id.

```sql
WITH v AS (
  SELECT t.id, t.created_at, t.branch_kind, t.envelope, t.response,
         jsonb_path_query_first(t.trace, '$[*] ? (@.stage == "understood").raw.derived') AS verdict
  FROM chatbot.turns t
  JOIN respond_contacts c ON c.respond_io_id = t.contact_respond_id
  WHERE c.chatbot_profile->>'tier' = 'office'
    AND t.is_test = false
    AND t.created_at > now() - interval '45 days'
)
SELECT id, created_at, branch_kind,
       envelope AS envelope_with_text,
       verdict->'sub_asks' AS sub_asks,
       verdict->'entities' AS entities,
       left(response::text, 800) AS reply
FROM v
WHERE jsonb_typeof(verdict->'sub_asks') = 'array'
  AND jsonb_array_length(verdict->'sub_asks') >= 2
  AND (jsonb_path_exists(verdict, '$.sub_asks[*] ? (@.measure == "other")')         -- H1
       OR NOT jsonb_path_exists(verdict, '$.entities[*] ? (@.hint == "product")'))  -- H3
ORDER BY created_at DESC
LIMIT 30;
```

If the join returns nothing, join on `c.id` instead. The shapes they target, each tied to the code arm that fails today:

1. Several asks where one is outside the runner's measures, for example "stock, incoming, and which customers
   bought the most of it this quarter and whether they still owe us": the last part becomes
   "not available yet" (`turn/sub_asks.py:709`).
2. A sold breakdown by an axis the runner does not have: same arm (`turn/sub_asks.py:714`).
3. A chained ask (the answer to one part feeds the next, for example "top 3 customers for brand X last month and
   their outstanding DO"): no product subject, so the runner returns None (`turn/sub_asks.py:291-293`) and
   only one domain is answered. Reaches the agent through H3.
4. A follow-up on (3) ("and the month before?"): through H2, because (3) was answered by the agent.

## Delivery after owner answers

Red-first. Tester writes failing tests first: hand-off predicate (H1/H2 and every exclusion), switch PATCH and
effective rules, dispatcher allow-list / grant / permission refusals, budget caps, fall-through on failure,
cassette loop tests for Gemini with thought signatures. Coder makes them green. Reviewer + security reviewer
(the diff touches permission gating). Crew runs the paid eval.
