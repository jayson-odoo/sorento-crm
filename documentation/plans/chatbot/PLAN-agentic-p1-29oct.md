# PLAN: Agentic phase 1 - the agent foundation (read-only, explicit entry)

Status: Plan. Card v3 (the foundation) posted for owner answers (crew-note on PR #1982); no code until they
arrive. Hand-off-rule track stopped by the owner (30 Oct). Track: full lane (a migration for the per-contact
switch, a new entry endpoint, a permission layer). Lane AGENTIC-P1, branch `claude/agentic-crm-chatbot-p1-fhvvb0`,
base origin/main ec29a81c.

Parent: `PLAN-agentic-crm-29oct.md` (components 1, 3, 4, 8). P0 (#1979, c9ff4958c9, on main) keeps Gemini thought
signatures / Claude thinking across tool rounds (`ChatResult.continuation`, `app/services/llm_provider.py:26-54`)
and passes reasoning effort.

## Owner rulings this lane carries

29 Oct ~22:45:
- R1: today's parser -> lane path stays as is. The agent is a separate branch.
- R2: follow the Claude Code mechanism: plan, call typed tools, read results, iterate, answer. No model-written
  SQL; analytics through the typed query builder and the one report service.
- R3: every read is limited by BOTH the linked user's permissions AND the contact's chatbot scope; never wider
  than today.
- R4: Gemini Flash (not lite). R5: one confirmation per write later; P1 is read-only.

30 Oct ~00:30:
- Multi-domain asks stay on today's bot; they are NOT a hand-off trigger. No automatic routing from today's bot.
- The agent writes its own reply (card v2 Q2 a). Staff = a linked active user; the tier field is not used
  (Q3 a). On a budget limit it behaves like Claude Code: keeps going within budget, then reports what it did and
  what it could not check (Q4 a). Eval budget approved, capped at USD 5 by crew (Q5).
- "Be firm on the foundation of our agentic architecture first": this card.

Measured facts kept from v2 (crew, dev DB, 29 Oct): `chatbot_profile.tier` is null on every contact; `sub_asks`
is never filled; so the existing multi-ask runner (`engine.py:7287-7300`) cannot fire on that data. Not this
lane's to fix; reported to the owner.

## Card v3: the agent foundation

One small package, `app/services/agent/`, four modules. It reuses what exists (provider adapters, MCP read seam,
prompt registry, turn trace, usage log) and adds only the loop, the tool registry with its permission layer, and
the entry point. No planner agent, no multi-agent topology, no new workflow platform.

### 1. The loop (`agent/loop.py`), Claude Code shape

```
context = system prompt + conversation memory + the user's message
loop:
    result = provider.chat(context, tools=permitted tool schemas, reasoning_effort)
    if result has tool calls:
        for each call: dispatch through the registry (permission layer) -> typed result
        append the assistant turn (with result.continuation) and the tool results to context
        check budgets; on a limit: one last call with NO tools ("answer with what you have")
        continue
    else:
        final text -> figure check -> reply
```

- Planning is inside the loop, as in Claude Code: the system prompt tells the model to work out what it needs,
  call tools, look at what came back and adapt. No separate planner call (the assistant's optional planner,
  `ai_assistant_service.py:584`, produces prose nobody executes; not reused).
- Provider: `llm_provider.get_provider` (`:1968`) and `chat(... tools, reasoning_effort)` (`:211-226`). The
  assistant turn is appended with `continuation` so Gemini thought signatures survive every round (P0).
- Model/prompt: its own prompt label `chatbot-agent` in the prompt registry (provider/model `ai_prompt_registry.py:1576`,
  effort `:1601`), seeded to Gemini Flash. No fallback to the parser's model: no approved key or model = a clear
  "agent unavailable" reply.
- Figure check (v2 Q2 a): every number in the final reply must appear in a tool result of this turn or in the
  user's own message. On a miss: one repair round naming the unsupported figures; still missing = the reply
  says those figures could not be verified rather than printing them.
- Not reused wholesale: `AIAssistantService._run_agent_loop` (`ai_assistant_service.py:2314`). It force-empties
  `contact_id`/`space_id` before calling MCP (`:2715`), which drops the contact's scope, and its dispatch checks
  names against the whole MCP catalogue, not the bound set (EVIDENCE-agentic-runtime). Its schema conversion
  (`_mcp_schema_to_openai_tool`, `:1504`) is reused.

### 2. Tool registry + typed read-only tools (`agent/tools.py`)

An explicit Python table. Each entry: `name` (an MCP tool), `user_permission` (the slug its route requires),
`contact_grant` (a reveal grant, or none), and a result summariser. The model-facing schema comes from the MCP
catalogue's `inputSchema` with `contact_id`/`space_id` stripped (they are server-injected, never model-chosen).

P1 set (all already on the chatbot's read-only allow-list, `lanes/business/fetch.py:1475`):

| Tool | Reads |
| --- | --- |
| `crm_report_ask` | The one report service: sales / outstanding ranked or totalled by one dimension and period |
| `crm_inventory_stock_balance_list` | Stock on hand |
| `crm_incoming_stock_by_product`, `crm_incoming_stock_shipments` | Incoming quantities, ETAs, allocation signal |
| `crm_procurement_grn_summary`, `crm_procurement_po_last_cost_list`, `crm_procurement_spo_allocations_last_receipt_list`, `crm_procurement_po_placed_list` | Received, last cost / supplier, last receipt, POs placed |
| `crm_order_management_orders_by_product_list`, `crm_order_management_orders_list` | SO / DO lines and status |
| `crm_lookup_resolve`, `crm_master_products_list` | Names, codes, brands, categories to ids |

Typed results: every dispatch returns `{status: ok | denied | invalid | error | timeout, data, more}`. `denied`
and `invalid` go back to the model as facts ("you may not read X"), so it can say so or try another route.
Large results are summarised to a fixed size with a `more` count, never cut mid-row.

Later, not P1: the analytics typed query builder (`app/services/analytics_connector/datasets.py`, today a chat
data catalogue only) as a tool once its datasets cover sales/stock; discovery of further tools.

### 3. The permission layer (`agent/access.py`): user rights AND contact scope

An immutable `AgentContext` built server-side per turn: contact (internal id, Respond id, workspace), the linked
active user (`users.respond_contact_id`, `app/models/user.py:74`), the contact's grants and brand scope. Nothing
in it comes from the model.

- Entry: no linked active user, or the contact's switch off, or AI replies off (`chatbot_allowed`) = refused.
- Model sees only tools the context permits: the user holds the tool's `user_permission`
  (`UserPermissionService.check_user_has_permission`, `services/user_service.py:1543`, the same check
  `require_permission` uses, `dependencies.py:414`) AND the contact holds its `contact_grant`.
- Dispatch re-checks all of it (schema exposure is not a guard), validates arguments against the schema, injects
  the contact's `contact_id`/`space_id`, and calls through `services._mcp_call(db)`
  (`lanes/business/services.py:228`): read-only allow-list, brand-scope guard on the call and on the result.
- The routes then apply today's contact scope from `contact_id` (customer scope, reveal grants, audience, stock
  location policy; `api/v1/order_management/report_ask.py:1-9`). So a read is never wider than the same contact
  gets from today's bot, and never wider than the user's permission slugs.
- Known limit, stated: the MCP call itself still authenticates as the integration's act-as user. Company scope and
  own-agent rules of the linked user are therefore enforced only as far as the contact scope covers them (Q2).

### 4. Context and memory per conversation

- One conversation = one contact, in the agent world, until "new conversation". Each agent turn is one
  `chatbot.turns` row (`app/models/chatbot_turn.py`, `ingress = "agent"`), carrying the message, the reply and the
  trace. No new table.
- Context per call: system prompt (behaviour, today's date, the user's display name and role, permitted tools) +
  the last 10 agent exchanges of this conversation read back from those rows (user text, final reply, and a
  one-line digest of each tool call: name, key arguments, status) + the new message + this turn's tool protocol.
- Fresh facts every time: history is evidence of what the user wants, never of current stock or orders; the model
  is told to re-read.
- Later, not P1: summarising/compacting older exchanges, retrieving exact earlier tool results, durable tasks
  across turns (needed with writes).

### 5. Budgets

Per turn, constants in `app/config.py` (env-overridable, like `ai_assistant_agent_max_iterations`, `:366`):

| Budget | P1 default (Q3) |
| --- | --- |
| Tool rounds | 8 |
| Tool calls per round | 4 |
| Wall clock | 45 s |
| Input tokens summed over the turn | 150,000 |
| Per MCP call timeout | min(remaining time, 10 s) |

On any limit: one final call with no tools, told to answer with what it has and name what it could not check
(owner Q4 a). The trace records which limit hit.

### 6. Tracing and usage

- Reuse the turn trace (`app/services/chatbot/trace.py`): one record per round (model, tokens in/out/cached,
  reasoning tokens, latency) and one event per tool call (name, arguments, status, ms, result size). Persisted on
  the `chatbot.turns` row, so the existing trace screen shows it.
- Usage rows into `ai_assistant_usage_logs` with `feature = "chatbot_agent"` (as `chatbot/usage.py` does for the
  parser), for console and eval turns too, so the eval cost is measured from the log.
- No private reasoning is stored or shown; only the opaque continuation needed within the turn.

### 7. Failure fallback

Explicit entry, so no silent fallback to today's bot (Q5). Provider error, timeout or missing key before any
tool result = "the agent could not answer: <reason>", with the trace. A failure after some tool results = the
budget-limit path (answer with what it has). A tool failure is a typed `error` result the model can work around.

### 8. How it is invoked

- Per-contact switch: `respond_contacts.chatbot_agent_enabled`, boolean, default off (migration), on the existing
  partial update `PUT /api/v1/user-management/contacts/{id}/chatbot` (pattern of `chatbot_files_as_links`,
  `api/v1/user_management/contacts.py:473,530`), one toggle in Contact Details > Chatbot.
- Entry point P1: an "Agent" mode in the chatbot console. New `POST /api/v1/system/chatbot/agent/turn`
  `{contact_respond_id, text, new_conversation?}`, same console permission as `/console/turn`
  (`api/v1/system/chatbot.py:649`), refused unless that contact's switch is on and it has a linked active user.
  Answers `{reply_text, turn_id, trace_summary, usage}`. Reads only; nothing is sent to WhatsApp.
- Today's bot is untouched: no automatic routing, no change to `engine.run_turn`.
- Later: WhatsApp entry for switched contacts (Q1), then routing rules if the eval ever justifies them.

### 9. How the eval proves it

- New eval engine `AgentTurnEngine` beside `HttpTurnEngine` (`scripts/chatbot_eval/engine.py:42`), posting to the
  agent endpoint. Same case format and runner.
- Cases (seeded fakes, never the real rows): the five real failure shapes crew pulled (paraphrased), each with 3
  paraphrases (one Malay, one Chinese); plus permission cases (user lacks a slug, contact lacks a grant,
  brand-scoped contact, no linked user, switch off), a budget case (more work than 8 rounds) and a follow-up case
  (memory).
- Grading on the end state: each expected figure computed independently by SQL on the test copy must appear
  correctly; denied data must not appear; gaps must be stated. Recorded: correct rate, rounds, latency p50/p95,
  tokens, cost per turn, denied/invalid calls, figure-check misses.
- Baseline: today's bot on the same cases through `/console/turn`, to show what the agent adds.
- CI: cassette tests only (`app/services/llm_cassette.py`), no paid calls. Paid run by crew on the test copy,
  capped at USD 5.
- Pass bar proposed: zero permission violations (hard), at least 80% of case-runs correct, every budget hit
  reported honestly, p95 <= 45 s in console.

## P1 builds vs later

P1: the four-module package (loop, registry + permission layer, memory read-back, budgets), tracing + usage,
the switch (migration + contact screen toggle), the console Agent mode + endpoint, the eval engine + cases,
cassette tests. Read-only.

Later: WhatsApp entry; writes with one confirmation each, an action ledger and durable tasks; running reads as
the linked user's own principal; memory compaction; the analytics query builder tool and sandboxed computation;
any automatic routing from today's bot.

## Delivery after owner answers

Red first (tester): context refusals; tool list filtered by user slug and contact grant; dispatch refusals
(name outside the registry, a slug or grant lost between exposure and dispatch, invalid arguments, a
model-supplied contact_id ignored); budget limits and the final no-tool answer; figure check; memory read-back;
continuation replay (Gemini cassette); endpoint auth and switch rules. Coder makes them green. FE: console Agent
mode + switch, built against mocks first. Reviewer + security reviewer (permission gating). Crew runs the eval.
