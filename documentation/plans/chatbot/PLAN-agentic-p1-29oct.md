# PLAN: Agentic phase 1 - the agent foundation (read-only, explicit entry)

Status: PR #1982 open. Crew eval 1 (ed4d19b6d2) FAILED 0/15 strict; fix rounds 5-5d built red-first (real resolver,
id provenance, typed empty/invalid, answer-tool verifier, honest limits); security reviewer SECURE on round 5, reviewer
confirmed round 5c and round 5d fixes the last date blocker; round 5e adds crm_products_find (security SECURE). Crew eval re-run pending. Full lane (migration: contact
switch, budget settings, `chatbot.agent_conversations`; new endpoints; permission layer). Lane AGENTIC-P1, branch
`claude/agentic-crm-chatbot-p1-fhvvb0`.

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

One small package, `app/services/chatbot/agent/`, four modules. It reuses what exists (provider adapters, MCP read seam,
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

| Tool | Reads | User permission (screen view slug) | Contact grant (today's bot) |
| --- | --- | --- | --- |
| `crm_report_ask` | The one report service: sales / outstanding ranked or totalled by one dimension and period | `order_management.orders.view` (the route's own) | none on the tool: the route decides the sales / outstanding reveal from the contact id. Arguments: `basis=unpaid` also needs the user's `finance.billing_documents.view`; `dataset=chat` needs the user's `chatbot.analytics.view` and the contact's `chatbot.analytics` |
| `crm_inventory_stock_balance_list` | Stock on hand | `inventory.stock.view` | none; the contact's stock switch (`chatbot_stock_allowed`) must be on; `include_sellable` only with `inventory.sellable` |
| `crm_incoming_stock_by_product`, `crm_incoming_stock_shipments` | Incoming quantities, ETAs, allocation signal | `procurement.packing_lists.view` | none |
| `crm_procurement_grn_summary` | Received quantities | `procurement.grn.view` | `purchase_orders.placed` |
| `crm_procurement_po_last_cost_list` | Last cost / supplier | `scm.purchase_orders.view` | `purchase_orders.cost` |
| `crm_procurement_po_placed_list` | POs placed | `scm.purchase_orders.view` | `purchase_orders.placed` |
| `crm_procurement_spo_allocations_last_receipt_list` | Last receipt | `procurement.spo_allocations.view` | `purchase_orders.placed` |
| `crm_order_management_orders_by_product_list` | SO / DO lines and outstanding by product | `order_management.orders.view` (the route's own) | none (outstanding fields are field-restricted) |
| `crm_resolve` (local, round 5) | Names and codes of products, suppliers, brands, categories, customers, sales agents to ids | one slug per kind (`KIND_SLUGS`) | `purchase_orders.supplier` for suppliers |
| `crm_products_find` (local, round 5e) | The products of a brand and/or category (one level of child categories) and/or a code or name query, at most 50 rows | `master_data.products.view` | none; company and brand scope apply |

Every call carries `view=render` (set by the server, never the model), because only the render view carries `restricted_fields`; a result that is not a render envelope is refused and never reaches the model.

Most of these routes only require a signed-in caller (for example `inventory/stock.py:239`). So the slug is the
view permission of the screen showing the same data (`config/menu.config.tsx`; `external/ingest.py:153`
READ_PERMISSIONS), which is stricter than the route, never wider.

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
- Field-level contact scope: every result passes through `lanes/business/fetch.py::output_structurer`, the one
  place today's chatbot drops restricted fields (supplier, sellable, ...) unless the contact holds the reveal
  (`fetch.py:3200-3270`), with the contact's reveal grants as `access.attributes`. The model never sees a field
  the contact could not see today.
- The routes then apply today's contact scope from `contact_id` (customer scope, reveal grants, audience, stock
  location policy; `api/v1/order_management/report_ask.py:1-9`). So a read is never wider than the same contact
  gets from today's bot, and never wider than the user's permission slugs.
- Known limit, stated: the MCP call itself still authenticates as the integration's act-as user. Company scope and
  own-agent rules of the linked user are therefore enforced only as far as the contact scope covers them (Q2).

### 4. Context and memory per conversation (owner Q4: continuous, like Claude Code)

- The conversation runs continuously until the user clears it ("New conversation"), like Claude Code. There is
  no fixed window of N exchanges.
- Storage: each agent turn is one `chatbot.turns` row (`app/models/chatbot_turn.py`; `ingress = "agent"`,
  `is_test = true` because nothing is sent to WhatsApp). The row carries the user text and
  `agent_conversation_id` in `envelope`; the final reply and a one-line digest per tool call (name, key
  arguments, status) in `response`; and the full trace.
- One small new table, `chatbot.agent_conversations`, is needed for what a turn row cannot hold: `id`,
  `contact_respond_id`, `created_at`, `summary` (text, null), `summary_through` (the `created_at` of the last turn
  folded into the summary, null), `summary_tokens`. The contact's current conversation is its newest row.
  "New conversation" inserts a new row. Nothing is deleted.
- Rebuilding context for a call: system prompt + `summary` (when set) + every turn of the conversation after
  `summary_through`, verbatim (user text, reply, tool digests) + the new message + this turn's tool protocol.
- Compaction: when the verbatim part is estimated (characters / 4) above `chatbot_agent_compact_tokens`
  (default 40,000), one model call with no tools folds the older turns, keeping the last 6 verbatim, into the
  running summary (old summary + those turns). The summary keeps corrections, open questions, entities and
  figures already answered, with the date each was read. `summary_through` then moves forward. A failed
  compaction leaves the conversation as it was; the turn still runs, on the verbatim history truncated from the
  oldest turn.
- Fresh facts every time: history and summary are evidence of what the user wants, never of current stock or
  orders. The model is told to re-read.
- Later, not P1: retrieving the exact earlier tool results, durable tasks across turns (needed with writes).

### 5. Budgets (owner Q3: configurable)

System Settings columns (one migration, edited on the existing Chatbot settings screen, read per turn):

| Setting (`system_settings`) | Default | Meaning |
| --- | --- | --- |
| `chatbot_agent_max_rounds` | 8 | Tool rounds per turn |
| `chatbot_agent_max_seconds` | 45 | Wall clock per turn |
| `chatbot_agent_max_input_tokens` | 150000 | Input tokens summed over the turn's model calls |
| `chatbot_agent_compact_tokens` | 40000 | Verbatim-history size that triggers compaction |

Fixed in code: 4 tool calls per round; each MCP call's timeout is min(remaining time, 10 s).

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

## Delivery

Red first (tester): budget settings read per turn and editable through the settings PUT; compaction (trigger,
summary stored, `summary_through` moved, last 6 verbatim, a failed compaction keeps the turn running); "new
conversation" starts empty; context refusals; tool list filtered by user slug and contact grant; dispatch refusals
(name outside the registry, a slug or grant lost between exposure and dispatch, invalid arguments, a
model-supplied contact_id ignored); budget limits and the final no-tool answer; figure check; memory read-back;
continuation replay (Gemini cassette); endpoint auth and switch rules. Coder makes them green. FE: console Agent
mode + switch, built against mocks first. Reviewer + security reviewer (permission gating). Crew runs the eval.

## Build contract (Phase 2; tester and coder both read this)

Backend package `sorento_crm_backend/app/services/chatbot/agent/`. Names below are the contract; tests import them.

### `agent/tools.py`

```python
@dataclass(frozen=True)
class ToolDef:
    name: str                 # MCP tool name
    user_permission: str      # slug the linked user must hold

REGISTRY: dict[str, ToolDef]  # exactly the 10 tools of card section 2, with the slugs in that table

@dataclass
class ToolResult:
    status: str               # "ok" | "denied" | "invalid" | "error" | "timeout"
    data: Any = None          # the (filtered, size-capped) tool output
    more: int = 0             # rows not shown because of the size cap
    message: str = ""         # plain reason for denied / invalid / error / timeout

def tool_schemas(tools: list[ToolDef], catalog: dict[str, dict]) -> list[dict]
    # OpenAI-style function tools; `catalog` is MCP tools/list ({name: {description, inputSchema}});
    # contact_id / space_id removed from properties and required.

def dispatch(db, ctx: "AgentContext", name: str, args: Any, *, call, catalog: dict[str, dict],
             timeout: float) -> ToolResult
```

`dispatch` rules, in order: name not in `REGISTRY` -> denied; the linked user lacks `user_permission`
(checked NOW, not at exposure) -> denied; `args` not a dict, or a key not in the tool's `inputSchema.properties`
-> invalid; model-supplied `contact_id` / `space_id` are discarded and the context's values injected; then
`call(name, args)` (production: `lanes/business/services._mcp_call(db)`; injected in tests). A raised
`ToolNotAllowed` -> denied; a timeout -> timeout; any other exception -> error (never raises). An ok result is
passed through the restricted-field drop with the contact's grants (below), then capped at 12,000 characters of
JSON: list values are cut by whole items and `more` counts the cut items.

Restricted-field drop: extract the block at `lanes/business/fetch.py:3200-3270` from `output_structurer` into
`fetch.drop_restricted_fields(envelope: dict, granted: set[str], axis: str | None = None) -> None` (in place), call
it from `output_structurer` (behaviour unchanged; the existing tests prove it) and from `dispatch`.

### `agent/access.py`

```python
class AgentRefused(Exception):
    reason: str   # "contact_not_found" | "switch_off" | "ai_replies_off" | "no_linked_user"

@dataclass(frozen=True)
class AgentContext:
    contact_pk: str           # respond_contacts.id
    contact_respond_id: str   # respond_contacts.respond_io_id (what chatbot.turns.contact_respond_id holds)
    space_id: str | None      # the contact's workspace id as the MCP tools take it
    user_id: str
    user_name: str
    grants: frozenset[str]    # the contact's field reveals, as today's turn reads them

def build_context(db, contact_respond_id: str) -> AgentContext   # raises AgentRefused
def permitted_tools(db, ctx: AgentContext) -> list[ToolDef]      # REGISTRY entries the user holds the slug for
```

Refusal order: no contact row -> contact_not_found; `chatbot_allowed` false -> ai_replies_off;
`chatbot_agent_enabled` false -> switch_off; no `users` row with `respond_contact_id = contact_pk`, active ->
no_linked_user. Permission checks use `UserPermissionService(db).check_user_has_permission` (superadmin/admin
pass, as everywhere). The contact's brand scope is applied to the session for the turn the same way today's turn
does, so `_mcp_call`'s brand guard sees it.

### `agent/memory.py`

```python
def current_conversation(db, contact_respond_id: str) -> AgentConversation  # newest row; created if none
def new_conversation(db, contact_respond_id: str) -> AgentConversation
def conversation_turns(db, conv) -> list[ChatbotTurn]                      # ingress="agent", oldest first
def history_messages(db, conv) -> list[dict]
    # [{"role":"user","content":"Summary of the earlier conversation: ..."}] when conv.summary, then for each
    # turn after conv.summary_through: {"role":"user","content":text}, {"role":"assistant","content":reply
    # + "\n[tools: name(args) status; ...]"}
def maybe_compact(db, conv, *, summarize, threshold_tokens: int, keep_last: int = 6) -> bool
    # estimate = chars/4 of the verbatim part; above threshold: summarize(old_summary, turns_to_fold) -> str,
    # store summary, summary_through = created_at of the last folded turn, summary_tokens; True.
    # summarize raising -> nothing changes, returns False.
```

Model `AgentConversation` (`app/models/chatbot_agent.py`), table `chatbot.agent_conversations`: `id` uuid pk,
`contact_respond_id` String(64) not null indexed, `created_at` timestamptz default now, `summary` Text null,
`summary_through` timestamptz null, `summary_tokens` Integer null. `__audit_skip__` like `ChatbotTurn`.

### `agent/loop.py`

```python
@dataclass
class Budgets:
    max_rounds: int = 8
    max_seconds: float = 45
    max_input_tokens: int = 150_000
    compact_tokens: int = 40_000
    calls_per_round: int = 4

def budgets_from_settings(db) -> Budgets          # system_settings columns; missing row -> defaults

def unsupported_figures(reply: str, sources: list[str]) -> list[str]
    # numbers in reply (ints, decimals, thousands separators; ignoring ones inside dates YYYY-MM-DD and the
    # digits of product codes) that do not appear in any source after normalising separators.

@dataclass
class AgentTurnResult:
    turn_id: str
    conversation_id: str
    reply_text: str
    status: str            # "answered" | "limited" | "failed"
    limit_hit: str | None  # "rounds" | "seconds" | "input_tokens" | "error" (provider failed after tool results) | None
    rounds: int
    usage: dict            # {"prompt_tokens", "completion_tokens", "cached_tokens", "calls"}
    tool_calls: list[dict] # [{"name", "status", "ms"}]

def run_agent_turn(db, *, contact_respond_id: str, text: str, provider=None, mcp_call=None,
                   catalog=None, clock=time.monotonic) -> AgentTurnResult
```

`run_agent_turn`: `build_context` (AgentRefused propagates); budgets; conversation + `maybe_compact`; messages =
system prompt (prompt key `chatbot_agent`, fallback text in `ai_prompt_registry`) + history + text; loop: each round
`provider.chat(messages, tools=schemas, reasoning_effort=...)`; with tool calls, at most `calls_per_round` run
(extra calls get a `denied` "too many calls this round" result), the assistant message is appended with
`continuation` when the result has one, then one `tool` message per call; budgets checked after every round; on a
limit, one final `chat` with `tools=None` and an instruction to answer with what it has and name what it could not
check, `status="limited"`. No tool calls -> figure check against the user text + every ok tool result's JSON: if
unsupported, one repair round naming them; still unsupported -> those figures are replaced by "(not verified)".
Provider/model: `ai_prompt_registry.agent_model(db, "chatbot_agent")`, default ("gemini", "gemini-3.5-flash"); key
from the assistant config as other callers resolve it; no key or provider error before any tool result ->
`status="failed"`, reply "The agent could not answer: <reason>." Every turn writes one `chatbot.turns` row
(`ingress="agent"`, `is_test=True`, `status="done"` or `"failed"`, `envelope={"text", "agent_conversation_id"}`,
`response={"reply_text", "tool_digest": [...], "status", "limit_hit"}`, trace events `agent_round` /
`agent_tool`), and usage rows (`feature="chatbot_agent"`).

### Routes (`api/v1/system/chatbot.py`, permission `VIEW` like `/console/turn`)

- `POST /api/v1/system/chatbot/agent/turn` body `{contact_respond_id: str, text: str 1..4000}` -> 200
  `AgentTurnResult` fields. `AgentRefused` -> 409 `{"detail": {"code": "agent_refused", "reason": ...}}`.
- `GET /api/v1/system/chatbot/agent/conversation?contact_respond_id=` -> `{conversation_id, turns: [{turn_id,
  text, reply_text, status, created_at}]}`.
- `POST /api/v1/system/chatbot/agent/conversation/new` body `{contact_respond_id}` -> `{conversation_id}`.

### Settings and switch

- `respond_contacts.chatbot_agent_enabled` Boolean not null default false: `ContactChatbotUpdate` field +
  partial update (`api/v1/user_management/contacts.py:473,530` pattern) + every contact chatbot GET dict.
- `system_settings.chatbot_agent_max_rounds` (8, 1..30), `chatbot_agent_max_seconds` (45, 5..300),
  `chatbot_agent_max_input_tokens` (150000, 10000..2000000), `chatbot_agent_compact_tokens` (40000,
  5000..500000): settings request model + the GET dict builder + PUT (`api/v1/user_management/settings.py:173,469`
  pattern of `report_ask_rate_limit`).
- One migration (revision id <= 32 chars) on the current head: the contact column, the four settings columns,
  the table.

### Frontend

- Contact Details > Chatbot: one "Agent mode" switch through `contactChatbotService.ts` (existing pattern).
- Chatbot settings page (`settings/chatbot-media`): the four budget fields.
- Chatbot console (`system-management/chatbot-console`): an "Agent" mode toggle; in agent mode, messages go to
  `agent/turn`, the history loads from `agent/conversation`, a "New conversation" button, each reply shows its
  rounds and tool calls (name + status) and the limit hit. Service + hooks layering, `extractApiError`.

## Round 5 contract (crew eval 30 Oct: FAIL, 0/15 strict; tester and coder both read this)

Eval root causes (crew, at ed4d19b6d2): no tool turned a product code / supplier / brand into an id
(`crm_lookup_resolve` covers dropdown lists only); a lookup "not found" came back as ok; a code passed as an id
failed as "The tool failed."; the model read empty or unrelated results as "no records" and made up totals; budget
hits were reported honestly only 3 of 6 times. Permission violations: 0 of 26 (keep it that way).

1. **`crm_resolve`, a local tool** (in process, not MCP; replaces `crm_lookup_resolve` in `REGISTRY`, so still 10
   tools). Args `{terms: [str] (1..10), kinds: [product|supplier|brand|customer|category|sales_agent] (optional,
   default all the user may search)}`. Runs the bot's own resolver seam
   `lanes/business/services._resolve_entity(db)` (`POST /system/references/resolve` in process) with
   `{"tokens": terms, "raw_tokens": terms, "allowed_entity_types": <mapped kinds>, "dry_run": true}`.
   - Kind gates: product `master_data.products.view`; supplier `procurement.suppliers.view` + contact reveal
     `purchase_orders.supplier`; brand `master_data.brands.view`; customer `order_management.customers.view`;
     category `master_data.product_categories.view`; sales_agent `master_data.sales_agents.view`. A kind the user
     or contact may not search is left out and named in the result (`skipped_kinds`).
   - Scope: `build_context` stamps the contact's COMPANY scope on the session
     (`company_scope_resolver.resolve_contact_company_scope`, fail closed to an empty set, as `engine.py:1057`
     does) beside the brand scope. Customer matches pass through the same readable-customer rule today's turn uses
     (`engine._readable_customers`; move it to a shared helper rather than copy it).
   - Result per term: `{term, status: "found" | "ambiguous" | "not_found", matches: [{id, kind, code, name}] (at
     most 5)}`. `found` = one match, or a top match the resolver itself marks unambiguous; `ambiguous` = several;
     `not_found` = none. The model must ask or say it could not find the term, never "no records".
2. **Ids come from results.** Dispatch keeps the set of ids seen in this turn's ok results. Any argument named
   `*_id` / `*_ids` (other than the injected contact_id / space_id) whose values are not in that set is `invalid`:
   a non-UUID value -> "`<arg>` takes ids from crm_resolve, not codes or names (`<value>`)."; an unknown UUID ->
   "Unknown id in `<arg>`; get ids from crm_resolve first."
3. **Typed empty.** An ok render envelope with no rows (`has_result` false, or no items / answers) is
   `status="empty"` with message "No rows matched these filters." and the applied filters.
4. **Clear errors.** A route validation error that comes back through MCP (HTTP 4xx detail) is `invalid` with the
   route's own detail text, URLs and host names stripped, at most 200 characters. Other failures stay "The tool
   failed."
5. **The `answer` tool ends every turn.** Schema `{text: str, figures: [{value: str, call_id: str}], not_found:
   [{what: str, call_id: str}], not_checked: [str]}`. The verifier (code, not a model):
   - every number in `text` (same extraction as `unsupported_figures`: dates and product codes ignored) must be in
     `figures`, and each figure's `call_id` must be an ok call of this turn whose result holds that value as a JSON
     number or numeric string value (keys, UUIDs and dates never count; a sum the model did itself does not count);
   - each `not_found` must cite a `crm_resolve` term with status `not_found`, or an `empty` call whose id arguments
     all came from `crm_resolve` `found` matches;
   - a violation goes back to the model once as the `answer` call's result (`status="invalid"`, the exact list);
     still violating: unbacked numbers become "(not verified)" and unbacked `not_found` items get the prefix
     "I could not confirm that nothing exists for: <what>.";
   - a plain-text reply with no `answer` call counts as an `answer` with nothing declared (so the repair round
     asks for the tool).
6. **Budget hits always say what was not checked.** On a limit, the final call offers ONLY the `answer` tool. If
   `not_checked` comes back empty, the reply gets "I stopped at the <rounds|time|token> limit before finishing, so
   I did not check: <plain labels of the tools that were refused, failed, timed out or never ran, or 'the rest of
   your question'>."
7. **System prompt** (fallback text): resolve every name or code with crm_resolve before any other tool; never pass
   a code as an id; `not_found` / `ambiguous` mean ask or say so; `empty` is not proof of "no records" unless the
   ids came from crm_resolve; totals come from a tool that totals (crm_report_ask), never from adding rows
   yourself; always finish with the answer tool, citing call ids.
8. Migration: no `CREATE SCHEMA` (472 creates `chatbot`; the statement needs the database CREATE privilege even
   with IF NOT EXISTS).

Round 5c notes: the brand-scope filter on closed-list brands in `crm_resolve` is stricter than `set_brand_scope` (only in-scope brand rows are returned, because brand rows themselves are not filtered by the session criterion). Numbers inside formatted strings back figures (a report's text, "51 (O/S: 36)", "RM 12.50"); UUIDs, dates, identifiers with a letter joined by "-" or "/", and keys never do. Every UUID value in an ok result of this turn is a known id for later calls; the reply text never carries a UUID.

Round 5e: `crm_products_find` is the 11th tool. Its brand and category ids must come from `crm_resolve` (the id rule), the rows are read on the agent session under the chat visibility rule, and its product ids join the ids seen this turn so the stock and incoming tools accept them. A lowercase `may` is a month only when a year follows.
