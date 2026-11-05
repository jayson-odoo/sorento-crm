# PLAN: AI tools standard (one query tool, one action tool, every module registered)

Status: planned 5 Nov 2026, waiting on crew to spawn lanes. Track: full (permission gates, writes, multi-company
reads, a new CI gate); no migration planned. Scout: `SCOUT-ai-tools-standard-5nov.md`. UAC:
`ai-tools-standard-acceptance-criteria.md`. Lane AI-TOOLS-SCOUT, PR #2185.

`BE` = `sorento_crm_backend/app`, `AG` = `BE/services/chatbot/agent`, `MCP` = `sorento_crm_mcp/sorento_crm_mcp`.

## 0. Owner rulings (5 Nov, ~11:00 MYT)

- Q1: build on the **agent path only**. The rollout slug stays with the owner while he trials it; the old path is
  left untouched (no retire phase).
- Q2: **both channels**, side panel and WhatsApp, behind the per-contact switch, which stays **off** by default.
- Q3: **all modules**, in parallel waves.
- Q4: CI gate fails the PR. In one plain sentence: **if a PR adds a new list screen's API and does not register that
  list for the assistant, or mark it "not for assistant" with a reason, the PR check goes red.**
- Q5: one general read tool that does everything (rows, filters, totals and group-by, lookups across related
  records), plus **one generic action tool** that can run any registered screen action through the existing
  propose / confirm / audit path, found through `tools_search`.

## 1. Do the panel and WhatsApp run the same brain? Yes, with four differences

Same function: the panel calls `agent_loop.run_agent_turn` (`BE/services/chatbot/panel_service.py:211`), the WhatsApp
inbox calls the same `loop.run_agent_turn` (`BE/services/chatbot/inbox_queue.py:875`), defined once at `AG/loop.py:1060`.
Same tool lists (`AG/loop.py:1253-1281`), same prompt key, same verifier.

| | Side panel | WhatsApp |
|---|---|---|
| Who may enter | holder of `system.ai_assistant_chat.agent` (`panel_service.py:56, 83-101`) | contact with `chatbot_agent_enabled` on every row of that WhatsApp id (`BE/models/access.py:352`, default false; checked `AG/access.py:95-102`; set by `PATCH` contacts, `BE/api/v1/user_management/contacts.py:539-540`) |
| Identity | the staff member (`StaffPrincipal`, `AG/access.py:136-138, 185-191`): their active company, every brand | the contact's linked user if any, else a contact principal (`AG/access.py:139-143`); company scope = the contact's companies, brand scope = the contact's brands (`AG/access.py:152-167`) |
| MCP catalog reads | run as the staff member (`X-Staff-User`, `MCP/scope.py:73`) | run as the shared integration key scoped by contact id (`AG/access.py:125-127`). This is why `PANEL_ONLY_TOOLS` exists (`AG/tools.py:94-105`) |
| In-process reads and writes | `run_as_user` as the staff member (`AG/writes.py:143-174`) | `run_as_user` as the linked user, same function |
| Confirm of a write | a Confirm button (`BE/api/v1/system/ai_assistant.py:374-400`) | a typed yes, read by the model through `confirm_action` / `cancel_action` tools (`AG/loop.py:630-642`); a known limit the owner accepted for order cancel (`PLAN-agentic-unify-tools-1nov.md`) |
| No linked user | n/a | contact principal: only `CONTACT_TOOLS` (`AG/tools.py:147`) |

Consequence for this plan: the new tools run **in process under `run_as_user`**, never through the MCP shared key, so
the 2 Nov reason for `PANEL_ONLY_TOOLS` does not apply to them, and they are safe on WhatsApp for a contact with a
linked active staff user. They are **never offered to a contact principal** (dealers, customers) in this plan.
On WhatsApp the contact's brand scope stays on the session (`BE/models/base.py:78`), so a brand-scoped staff contact
sees the same brands it does today; `run_as_user` replaces the company scope with the user's own
(`AG/writes.py:172`).

## 2. Design

### 2.1 The registry (core, one file per module)

`BE/services/assistant_registry/` (core: it must not import `app/services/chatbot`,
`tests/chatbot/test_import_boundary.py`). `__init__.py` collects every `<module>.py` in the folder.

```python
@dataclass(frozen=True)
class FieldDef:
    label: str
    permission: str | None = None     # extra slug to read this field (cost price, phone, margin)

@dataclass(frozen=True)
class EntityDef:
    key: str                          # "purchase_order"
    label: str                        # "Purchase orders"
    module: str                       # module key for require_module_enabled ("scm")
    model: type                       # SQLAlchemy model
    view_permission: str              # the list screen's slug
    own_permission: str | None        # ".view_own" slug; with owner_column, narrows to own rows
    owner_column: str | None
    fields: dict[str, FieldDef]       # ALLOWLIST: what the screen shows; nothing else is readable
    relations: dict[str, tuple[str, str]]  # name -> (entity key, fk column), for lookups and joins
    screen_path: str                  # "/scm/purchase-orders/{id}", for row links
    pages: tuple[str, ...]            # path prefixes where this module's actions load first
    routes: tuple[str, ...]           # the list routes this entity answers for ("GET /api/v1/scm/purchase-orders"), read by the CI gate

@dataclass(frozen=True)
class ActionDef:
    key: str                          # "purchase_order.approve"
    entity: str
    write: "WriteDef-shaped"          # slug, read_before, summary, execute calling the route function
```

Simplest-thing check: why not reuse `list_query` (`BE/services/list_query_registry.py`)? It needs three places per
entity (adapter, compiler adapter, search handler, `list_query_search_service.py:45-52`) and has no aggregates. One
`EntityDef` per entity is one place. Company isolation needs no code: every `CompanyScoped` model is filtered by
`do_orm_execute` on the session (`BE/models/base.py:113-141`), and `run_as_user` stamps the user's scope. What the
registry must state explicitly, because nothing enforces it automatically: the view slug, own-row narrowing, the
field allowlist and field-level slugs.

### 2.2 `crm_query` (one read tool)

```json
{"entity": "purchase_order",
 "fields": ["number", "supplier.name", "status", "total"],
 "filters": [{"field": "status", "op": "in", "value": ["approved"]},
             {"field": "supplier.name", "op": "contains", "value": "Kohler"},
             {"field": "created_at", "op": "between", "value": ["2026-10-01", "2026-10-31"]}],
 "group_by": ["supplier.name", {"field": "created_at", "bucket": "month"}],
 "aggregates": [{"fn": "sum", "field": "total"}, {"fn": "count"}],
 "sort": [{"field": "sum_total", "dir": "desc"}],
 "limit": 20}
```

- Ops: eq, ne, in, not_in, lt, lte, gt, gte, between, contains, starts_with, is_null, is_not_null.
- Lookups across records: dotted paths through declared relations, up to 2 hops. A filter on a related field becomes
  a join; there is no free SQL.
- Group-by: up to 4 fields (cheap: it is one GROUP BY), date buckets day / week / month / quarter / year (Malaysia
  time). Aggregates: count, count_distinct, sum, avg, min, max on numeric fields.
- Limits: rows at most 50, groups at most 200, always with `total` and `truncated`; `SET LOCAL statement_timeout =
  5000`; result capped by `RESULT_CHAR_CAP` (`AG/tools.py:27`).
- Refusals, each a plain `ToolResult` the model reads: unknown entity or field (lists the valid ones), field without
  its slug (`restricted`), module disabled, no view slug, own-only holder on an entity without `owner_column`.
- Each row carries `id` and `link` (`screen_path`), so the answer can link the record; ids are never shown as text.

`crm_describe(entity?)`: with no entity, the entities this user may read (key, label, module); with one, its fields,
types, ops, relations and actions. This is how the model learns a new module with no prompt change.

### 2.3 `crm_act` (one action tool)

`crm_act({"action": "purchase_order.approve", "args": {...}})`. Validates `args` against the action's schema, then
goes through the existing `_propose` path (`AG/loop.py:667`), so it gets the same slug checks at exposure, proposal and
execution, the same `read_before` summary, the same Confirm (button on panel, typed yes on WhatsApp) and the same audit
row as the user (`AG/writes.py:143-174`). The existing hand-written `WRITES` stay as they are; new screen verbs are
`ActionDef`s, built with one helper `route_action(route_fn, slug, record_key, summary)` so a registration is about 15
lines.

### 2.4 Loading without bloat

- Always offered (staff with a linked user, either channel): `crm_query`, `crm_describe`, `crm_act`, `tools_search`,
  plus today's `REGISTRY` / `USER_READS` / `WRITES`.
- `tools_search(query)` returns matching `ActionDef`s (key, label, one-line summary, arg schema) by keyword over label,
  entity and module, best 8. No embeddings.
- Page-aware: on a panel turn, the actions of the module whose `pages` prefix matches `page_snapshot.path`
  (`panel_service.py:115-183`) are listed in the system prompt by key and label (not full schemas), so the first round
  needs no search.
- Measure: input tokens per model call before and after on the same eval set, recorded in the PR. Target: no more than
  today's for a full-permission user, while covering every module.

### 2.5 The standard (DoD text, goes into `PRINCIPLES.md` DoD gate and crew's worker-contract.md)

> 6. **The assistant can read it.** A new list screen adds its entity to `BE/services/assistant_registry/<module>.py`
>    (fields = what the screen shows, with the screen's slugs), or its list route carries
>    `# ai: not-for-assistant <reason>`.
> 7. **The assistant can do it.** Each new button that changes a record and that a user would ask for in words gets an
>    `ActionDef` calling the same route function, or the plan says why not.
> 8. **Two eval prompts** per feature in `scripts/chatbot_eval/gold/assistant_<module>.jsonl`, each naming the
>    expected entity or action.

CI gate `scripts/ci_ai_coverage.py`, run in the fast PR gate next to `pii_guard.py`
(`.github/workflows/deploy.yml:243`): it reads the PR diff against its merge base, finds added `@router.get`
functions that take `page` or `limit`, and fails unless that route is in some `EntityDef.routes`, or the decorator is
preceded by the opt-out comment. Diff-based, so there is
no baseline file to conflict on. A pytest also checks every `EntityDef`: model columns exist, slugs exist in the
permission seed, relations resolve.

## 3. Phases

| Phase | Lanes (parallel where marked) | Size |
|---|---|---|
| 0 | GAP-SIGNAL | S |
| 1 | QUERY-CORE, then ACT-CORE and AI-GATE in parallel | L, M, S |
| 2 | Module waves A to D, every lane in a wave in parallel | see section 5 |

Phase 0 can start now and in parallel with QUERY-CORE. Waves start only after QUERY-CORE and ACT-CORE merge (they
define `EntityDef` / `ActionDef`). The 20 Oct dev copy is not used: it predates the agent path's panel traffic.

## 4. Lane briefs, phase 0 and 1

### GAP-SIGNAL (S, small fix track)

- Goal: know which asks failed for lack of a tool, from now on.
- Change: `ANSWER_SCHEMA` in `AG/loop.py` gains optional `no_tool: [{ask, area}]` ("what the user asked that no tool
  could answer"). Saved on the turn's trace (`ChatbotTurn.trace`), and the Wishlist screen
  (`/system-management/ai-assistant/wishlist`) gains a plain list of the last 30 days of `no_tool` items with user,
  channel, date. No clustering (the job needs OpenAI, `BE/jobs/ai_wishlist_clustering.py:43-47`).
- Tests: answer with `no_tool` saves it; answer without it saves nothing; the list shows only rows the viewer may see
  (same slug as the Wishlist).
- Out: the old path's wishlist logic is not touched.

### QUERY-CORE (L, full track, security reviewer required: multi-company reads, RBAC)

- Goal: `assistant_registry` package, `crm_query`, `crm_describe`, wired into the agent loop for staff principals on
  both channels; 4 pilot entities to prove the shape: `order` (orders), `product`, `purchase_order`, `complaint`.
- Files: new `BE/services/assistant_registry/{__init__,types,query,orders,products,scm,complaints}.py`; tool wrapper in
  new `AG/query_tools.py` (an `UserRead`-shaped entry run under `run_as_user`); `AG/writes.py:471`
  `permitted_user_reads` includes them when `ctx.principal != "contact"`; tool label in `TOOL_LABELS`.
- Tests (tester writes first, Postgres via `tests/_pg_fixture.py`, seed own data):
  1. filter + sort + limit returns only allowlisted fields;
  2. a field with a slug the user lacks is refused, with the others still answered;
  3. user of company A never sees company B rows, on panel and on a WhatsApp linked-user turn;
  4. `.view_own` holder sees only own rows; own-only holder on an entity without `owner_column` is refused;
  5. group-by 3 fields + month bucket + sum/count equals a hand SQL sum on the seeded data;
  6. relation filter `supplier.name contains` joins correctly; 3 hops refused;
  7. 51 rows asked returns 50 and `truncated: true`; 201 groups returns 200;
  8. statement timeout returns a plain refusal, not a 500;
  9. module disabled for the tenant is refused;
  10. contact principal is never offered `crm_query`;
  11. `crm_describe` lists only entities the user may view;
  12. registry self-check: columns, slugs, relations of every `EntityDef` resolve.
- Out: actions, tools_search, the CI gate.

### ACT-CORE (M, full track, security reviewer required: writes)

- Goal: `ActionDef`, `route_action` helper, `crm_act`, `tools_search`, page-aware action listing; 2 pilot actions on
  the pilot entities (purchase order approve, complaint reopen or the nearest existing route).
- Files: `BE/services/assistant_registry/types.py` (`ActionDef`), `AG/act_tools.py`, `AG/loop.py` (offer the three
  tools; page module listing in `_system_prompt`).
- Tests: `crm_act` with a missing slug is refused at proposal and again at execution if the slug was removed in
  between; confirm on panel runs the route as the user and writes an audit row with `actor_type=user`,
  `auth_method=agent`, `tool_name=crm_act:<action>`; typed yes on WhatsApp confirms, anything else does not; cancel
  writes nothing; bad args are refused before a proposal; `tools_search` returns only actions the user may run;
  page path `/scm/purchase-orders/...` lists SCM actions in the prompt and no others.

### AI-GATE (S)

- Goal: `scripts/ci_ai_coverage.py` + wiring in the PR gate + pre-push hook; DoD lines 6 to 8 in `PRINCIPLES.md`;
  `assistant_*` case type in `scripts/chatbot_eval/cases.py` that checks the entity or action the agent used.
- Tests: an added paged GET without registration fails; with the opt-out comment passes; with a registered entity
  passes; an edit to an existing route does not trigger it.

## 5. Module waves (all modules)

Size per module lane: S = up to 5 entities, read only or 1 to 2 actions; M = 6 to 12 entities or 3 to 6 actions;
L = more, split where noted. Entities come from the sidebar (`sorento_crm_frontend/config/menu.config.tsx`, line
numbers below); each lane confirms its list against the models and marks screens that should opt out. Every lane
also adds 2 eval prompts per entity group. Lanes in one wave touch different `assistant_registry/<module>.py` files, so
they run in parallel.

### Wave A (what staff ask most; start right after phase 1)

| Lane | Screens (menu line) | Likely actions | Size |
|---|---|---|---|
| A1 SALES | targets, opportunities, customer asks, teams, sales agents, yearly comparison, by debtor type, top selling, sales and outstanding, set-apart customers (`:142-201`) | target set, opportunity stage move | M |
| A2 ORDERS | delivery orders, order statuses, customers, customer groups, branches (`:285-306`) | order cancel (exists), customer group assign | M |
| A3 INVENTORY | warehouses, storage zones, stock, stock status, stock position, batches, ledger, transfers (`:521-560`) | transfer create / receive | M |
| A4 PRODUCTS | products, attachments, sets, specifications, spec verification, flyer proposals, categories, brands, item classes, UoM, countries, certificates, lookup sets (`:576-642, 1192`) | spec verify, flyer proposal accept / reject | M |

### Wave B (supply side)

| Lane | Screens | Likely actions | Size |
|---|---|---|---|
| B1 SCM-BUY | reorder planning, purchase orders, proforma invoices, loading plan, simulation, market signals, policies, SCM dashboard (`:366-385, 476-507`) | PO approve / send, reorder line accept | L |
| B2 SCM-SELL | stock debt, order inquiries, SCM sales orders, consignment (`:484-496, 810-817`) | stock debt link PO, inquiry close | M |
| B3 PROCUREMENT | suppliers, product-suppliers, cost price uploads, packing lists, SPO allocations, GRN, picking lines, stock inquiries, NPAs, purchase requests, sponsorship forms + report (`:423-464, 822-833`) | PR decide (exists), stock inquiry answer, NPA approve | L |

### Wave C (projects and selling tools)

| Lane | Screens | Likely actions | Size |
|---|---|---|---|
| C1 PROJECTS-PIPELINE | projects, leads, awaiting acceptance, my tasks, stock claims, sample requests, AutoCount differences, parties (`:213-249`) | lead accept / reject, task done, claim approve | L |
| C2 PROJECTS-PLANNING | fulfilment planning, plans, planning changes, forecast and reports, setup, series, price floors, quotation templates (`:253-272, 394-410`) | planning change approve | M |
| C3 DEALER-KIT | catalogue pages, editions, collections, tile designs, brochure images, flyers, bundles, room designs, price tag requests, tag templates, tag sizes (`:655-719`) | price tag request approve / render, flyer read retry | L |
| C4 MARKETING | promotions, types, promotion products, attachments, campaigns (`:317-343`) | promotion activate / end | S |

### Wave D (service, admin and system)

| Lane | Screens | Likely actions | Size |
|---|---|---|---|
| D1 SERVICE | complaints, root causes, resolutions, SLA policies, conversations, conversation and form SLA tracking, team tasks, form SLA config, event logs, message snippets, KPI (`:734-799`) | complaint close (exists), reassign, SLA extend | M |
| D2 FORMS-TICKETS | forms, workflow form definitions and submissions, tickets, ideas (`:115-126, 845-857`) | submission approve, ticket assign / close | M |
| D3 FINANCE-RESOURCES | billing documents, files, trash, attachment types, document access (`:354, 869-885`) | none in v1 | S |
| D4 PEOPLE (security reviewer required) | users, internal users, teams, onboarding requests, roles, permissions, AI agents, contact access types, contact tags, market segments, logs (`:898-964`) | onboarding approve; role and permission edits opt out | M |
| D5 SYSTEM (security reviewer required) | companies, app store, import jobs / logs, tracking validation, audit logs, health, activity, scheduled tasks, API call log, client errors, integrations, integration logs, WhatsApp templates, mail and Respond outboxes, chat history / overview, top asks, bot failures, topic audit, chatbot config screens, email config, Respond workspaces / contacts, automation, work calendar, running numbers, import mappings, status graphs, translations, embeddings, AI assistant screens (`:983-1232`) | import job retry; most config screens opt out | L |

Order inside the plan: phase 0 and QUERY-CORE now; ACT-CORE and AI-GATE when QUERY-CORE's types are merged; waves A
and B together (7 lanes), then C and D (9 lanes), each lane capped by crew's own concurrency.

## 6. Risks and triggers

- **Field leaks.** The allowlist is the guard; a reviewer checks every `FieldDef` against what the screen shows and its
  route's own reveal rules (cost price, phone, sales reveal). Trigger to add automatic derivation from the screen's
  response schema: a second leak found in review.
- **Heavy group-by on large tables** (orders, stock ledger). Statement timeout plus limits; trigger for read replicas or
  summary tables: timeouts in more than 1% of `crm_query` calls in the phase 0 / trace data.
- **Typed yes on WhatsApp** for every new action: accepted for order cancel; each wave lane lists its actions in its PR
  so the owner can opt any of them out of WhatsApp.
- **Old path users** (everyone but the owner today) see none of this until the slug is granted. Owner's call.
