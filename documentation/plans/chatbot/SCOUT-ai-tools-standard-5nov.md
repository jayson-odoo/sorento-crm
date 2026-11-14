# SCOUT: AI tools standard (every module gets assistant tools)

Status: done; owner answered 5 Nov, plan in `PLAN-ai-tools-standard-5nov.md`. Lane AI-TOOLS-SCOUT. Read-only, no
product code. Base main 93886d3b. `BE` = `sorento_crm_backend/app`, `MCP` = `sorento_crm_mcp/sorento_crm_mcp`,
`AG` = `BE/services/chatbot/agent`.

Owner, 5 Nov: a standard so that every module and table gets assistant tools, so the side panel can analyse and act on
any feature we ship "without bloating it".

## A. How the side panel gets tools today

There are **two panel paths**, chosen per user on every message (`BE/api/v1/system/ai_assistant.py:320`):

| | Old path (default) | Agent path ("the brain") |
|---|---|---|
| Who gets it | everyone without the rollout slug | holders of `system.ai_assistant_chat.agent` (`BE/services/chatbot/panel_service.py:56`), granted to nobody by a migration; admins only through a role that holds it (`panel_service.py:83-101`) |
| Code | `BE/services/ai_assistant_service.py` (3,626 lines) | `panel_service.run_panel_turn` (`panel_service.py:104`) into `AG/loop.py` |
| Tools offered | keyword rank over the admin's `enabled_tools`, **top 1 tool per turn** by default (`BE/config.py:372-376`, `ai_assistant_service.py:1536-1568`) | every tool the user's slugs allow, **all on every turn** (`AG/access.py:244-248`, `AG/loop.py:1253-1281`) |
| Reads go through | MCP server at `ai_assistant_mcp_url` (`BE/config.py:367`) | MCP for catalog reads (`AG/tools.py:110`), in process as the user for `USER_READS` (`AG/writes.py:422`) |
| Writes | MCP record-action tools, run as the **shared act-as integration user** (`ai_assistant_service.py:2072-2117`); audit row says `actor_type=integration` (`BE/dependencies.py:117`) | in process, calling the screen's route function as the **logged-in user** with `actor_type=user, auth_method=agent` (`AG/writes.py:143-174`) |
| Confirm step | Confirm/Cancel card, `pending_confirmation` in message metadata (`ai_assistant_service.py:1928-1980`; FE `app/components/common/AIAssistantBubble.tsx:889-906`) | proposal card with Confirm, Cancel, Undo, countdown; `/ai-assistant/agent/actions/{id}/confirm` (`ai_assistant.py:374-400`; FE `AIAssistantBubble.tsx:100-124, 838`) |
| Which tools are writes | name suffix list + a hand list (`ai_assistant_service.py:126-153`) | explicit `WriteDef` table (`AG/writes.py:34-60, 327`) |

The MCP server (`MCP/server.py:1857-1905`) compiles each `ToolSpec` in `MCP/catalog.py` into an HTTP GET/POST against
`/api/v1/*`. For the panel's reads it forwards the staff member as `X-Staff-User` (`MCP/scope.py:73`), and the backend
only accepts that identity on routes listed in `STAFF_READ_ROUTES` (`BE/services/company_scope_resolver.py:72, 150-158`),
pinned equal to the catalog's reads by `tests/test_staff_read_identity.py:1049`. Even then, every slug check asks
**both** the staff member and the key's act-as user (`BE/dependencies.py:151-163`).

**Dead mechanism, already in the code:** `MCP/module_loader.py` merges per-module `app/modules/<key>/mcp/tools.json`
files into the catalog (`server.py:1882`). There are **zero** such files in `BE/modules/`, and the MCP Docker image copies
only its own package (`sorento_crm_mcp/Dockerfile:4-5`), so in production it could never find them anyway.

### Tools today (MCP catalog: 55 entries, `MCP/catalog.py:56-1828`)

| Domain | Tools |
|---|---|
| products | products list, `crm_find`, brands, categories, UoM, product attachments, certificates |
| orders / sales | orders list, orders by product, outstanding report, sales report, `crm_report_ask`, sales analysis, order analytics, sales target progress, opportunity options + log, customers (debtors) list, order cancel |
| inventory | stock balance, warehouses, low stock report |
| incoming stock | by product, shipments, list |
| procurement / SCM | PR approve/reject/by number, GRN summary, PO placed, PO last cost, SPO last receipt |
| projects | list, detail, quotations, forecast |
| complaints, SLA | complaints list, analytics, close; SLA conversation dashboard, list, event logs |
| other | promotions x3, resources x3, forms list, lookup resolve, portal link, guides, IT ticket create, ideation turn |

The agent path offers a subset plus its own in-process tools: 21 catalog reads in `REGISTRY` (`AG/tools.py:110-143`),
`USER_READS` (customer asks, opportunities, contacts, purchase requests, complaint and project finds, ideas) and
`WRITES` (customer ask update, opportunity create/update, contact access update, PR decide/undo, idea create/update,
complaint close, order cancel, IT ticket) (`AG/writes.py:247, 582-585, 904-905, 1391-1392, 1679-1680, 1805, 1946-1948,
2356, 2489, 2578`). Catalog tools **not** on the agent path: sales target progress, sales report, outstanding report,
orders list, promotions, customers, warehouses, low stock, forms, resources, products list.

### Modules with NO tool on either path (sidebar, `sorento_crm_frontend/config/menu.config.tsx`)

Sales targets / teams / agents / yearly comparison (`:142-201`, agent path), project leads, lead acceptance, my tasks,
stock claims, sample requests, AutoCount differences, parties (`:213-249`), customers / groups / branches (agent path,
`:295-306`), campaigns, billing documents (`:342-354`), SCM dashboard / simulation / market signals / policies
(`:366-385`), fulfilment planning / plans / planning changes (`:394-405`), suppliers, product-suppliers, cost uploads,
packing lists, picking lines, stock inquiries, NPAs (`:423-464`), **reorder planning, stock debt, loading plan, order
inquiries, purchase orders (beyond "placed"), proforma invoices** (`:476-507`), storage zones, stock status / position /
batches / ledger / transfers (`:526-560`), product sets and specifications (`:586-607`), **all of dealer kit and price
tags** (`:650-719`), complaint root causes / resolutions, SLA policies, form SLA, team tasks, KPI (`:739-799`), SCM sales
orders, consignment, sponsorship (`:810-833`), workflow forms, users and access, system, chat/omnichannel screens
(`:856-1232`). Roughly 15 of about 150 screens have a tool.

## B. A generic query tool: feasible, and half of it exists

`POST /api/v1/list-query/search` (`BE/api/v1/list_query.py:356-400`) is already a generic list query: a resource key,
a nested `FilterGroup` (`BE/schemas/list_query.py:42-72`) compiled per resource (`BE/services/query/filter_compiler.py`),
sort, page, limit up to 1000. Field metadata (label, type, allowed operators) is introspected from the model and synced
into tables (`BE/services/list_query_metadata_sync_service.py:64-146`) and served at
`/list-query/resources/{key}/fields` (`list_query.py:226`). It checks the view slug, or `.view_own`, per resource
(`list_query.py:195-208, 366`), and runs through each entity's **own list service** (`list_query_search_service.py:58-150`),
so company scope and any narrowing the list service applies are the screen's. Not verified in this scout: that each
of the 6 handlers narrows a `.view_own` holder to their own rows; phase 1 needs a test per resource.

Gaps: 10 adapters registered (`BE/services/list_query_registry.py:101-215`) but only 6 have search handlers
(`list_query_search_service.py:45-52`): orders, products, suppliers, promotions, workflow definitions, submissions. No
group-by or aggregate. Each new entity needs an adapter, a compiler adapter and a handler (three places).

How it would run with the user's permissions: as an in-process `USER_READS` tool on the agent path, called under
`run_as_user` (`AG/writes.py:143`), the same way the existing finds work. No MCP change, no new identity path, no
`STAFF_READ_ROUTES` entry. Limits: one result is capped at 16,000 characters before it reaches the model
(`AG/tools.py:27`), so aggregates must be computed in SQL (count / sum / min / max grouped by at most 2 fields, at most
200 groups), and row listings return at most 50 rows plus a total.

A semantic layer (metrics as code) is not needed now: the screen's list service is already the definition of "what a
row is" for that screen. Trigger to build one: two modules defining the same metric differently.

## C. Tool loading and token cost

- Old path: 1 tool bound per turn, so it is cheap but cannot combine data; anything outside the top-ranked tool fails.
- Agent path: every permitted tool on every call. A static estimate from source (characters / 4, run in this
  scout) is about **10,000 tokens** for the 21 catalog reads' descriptions and parameters plus about **3,300 tokens**
  for the 20 schema literals in `writes.py`, so roughly **13,000 to 15,000 tokens of tool schema per model call** for a
  full-permission user, repeated on each round of a turn. `crm_report_ask` alone has a 6,286 character description.
- Neither path loads tools by page. The panel already sends the page path and the open record
  (`sorento_crm_frontend/lib/aiPageSnapshot.ts:3-9`), read only for context (`panel_service.py:115-183`).
- Adding tools for ~135 more screens the same way (one catalog tool per screen) would make it 4 to 5 times bigger.
  So the standard must not add a tool per screen.

Proposed: about 8 core tools always loaded (generic query, generic describe, resolve, guides, knowledge, the 3 heaviest
reports), plus the current module's verb tools picked from `page_snapshot.path`, plus a `tools_search(query)` tool that
returns other modules' verb tools by name for the next round. The schemas are already per-turn lists
(`AG/loop.py:1274-1281`), so this is a filter on that list, not a new mechanism.

## D. Actions

The agent path's `WriteDef` already satisfies the proposed contract: it names the route's own slug and checks it at
exposure, proposal and execution (`AG/writes.py:1-8, 36-38`), reads the record before (`read_before`), shows a
code-built summary, waits for the user's Confirm, runs the route function as the user, and writes the audit row as
that user with `auth_method=agent` and the tool name (`AG/writes.py:143-174`). The old path does not: its writes run as
the integration user (`ai_assistant_service.py:2072-2077`), with a hand-kept permission map
(`ai_assistant_service.py:1860-1880`).

So the standard for actions is "a `WriteDef` per verb", not a new framework.

## E. The standard (proposed text)

Lines for PRINCIPLES.md "Definition of Done gate" (and the crew's worker-contract.md, which lives outside this repo):

> 6. **The assistant can read it.** A new list screen registers its entity for the generic query (adapter + compiler
>    + search handler, `list_query_registry.py`), or carries `# ai: not-for-assistant <reason>` on its list route.
> 7. **The assistant can do its verbs.** Each new state-changing button a user would ask for by chat (approve, link,
>    send, reserve...) gets a `WriteDef` in `AG/writes.py` calling the same route function, or the plan says why not.
> 8. **Two eval prompts per feature** in `scripts/chatbot_eval/gold/assistant_<module>.jsonl`: one read, one action
>    (or two reads), each naming the expected tool.

CI check (fast gate, no DB, same shape as `scripts/pii_guard.py`, wired like `.github/workflows/deploy.yml:243`):
`scripts/ci_ai_coverage.py` lists `@router.get` routes added in the PR diff that take `page`/`limit` (877 GET routes in
246 files today, 113 files with paged lists), and fails unless the route's resource key is in `ADAPTERS` or the route
carries the opt-out comment. Existing routes are grandfathered by a committed baseline file, so the gate only bites new
work.

Eval hook: the existing bench (`sorento_crm_backend/scripts/chatbot_eval/`, gold sets in `gold/*.jsonl`) gains an
`assistant_*` case type that checks which tool the agent called; it is not run in CI (fast gate only, CI-CLOUD-GATE),
it runs in the lane's `scripts/crew-tests.sh`.

## F. Rollout and evidence of failed requests

There is **no usable log of panel requests that failed for lack of a tool**:

- The wishlist tags only old-path turns, and only when the reply is empty or a fixed fallback string
  (`ai_assistant_service.py:1317-1319, 1373-1378, 3382-3392`). A polite "I can't do that" is counted as answered.
- Its clustering job needs an OpenAI key (`BE/jobs/ai_wishlist_clustering.py:43-47`); the owner dropped OpenAI on 31 Oct
  (`documentation/plans/system/PLAN-no-openai-31oct.md:49`), so clusters stop updating.
- The agent path does not tag the wishlist at all (`documentation/plans/chatbot/CARD-agentic-unify-v2-31oct.md:102`).

The raw messages are in `ai_assistant_messages` on production; this sandbox cannot read them. Phase 0 therefore adds the
signal before the module picks are final.

| Phase | What | Size |
|---|---|---|
| 0 | Gap signal: the agent's answer tool gets a `no_tool` field, saved on the turn; wishlist reads it. Owner (or crew with a prod copy) pulls the last 60 days of panel messages to rank modules. | S |
| 1 | Generic `crm_query` + `crm_describe` as in-process `USER_READS` over `list_query`; add group/aggregate; move the 11 catalog tools missing from the agent path onto it or onto `REGISTRY`. | M |
| 2 | Page-aware loading + `tools_search`; measure tokens before/after on the same eval set. | S/M |
| 3 | First 3 modules: entities on `list_query` + their top verbs as `WriteDef`. | M each |
| 4 | DoD lines, CI gate with baseline, eval case type. | S |
| 5 | Retire the old path's tool selection once everyone is on the agent path. | S |

Proposed first modules (owner's own recent lanes, until phase 0 data says otherwise): **SCM purchase orders + stock debt
+ order inquiries**, **procurement (packing lists, stock inquiries, suppliers)**, **dealer kit price tag requests**.
