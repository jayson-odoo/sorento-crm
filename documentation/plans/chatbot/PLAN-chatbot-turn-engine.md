# PLAN - Chatbot Turn Engine: n8n business logic moves into the CRM

Status: S0 + S1 IMPLEMENTED on lane feat/chatbot-turn-engine (4 Sep 2026); approved "ok good to go", 6 review rounds, D1 to D16; re-ported onto the LIVE n8n body 5 Sep (see S1 "pending re-port"); S1b DELIVERED 5 Sep (-40.0% prompt, published unlabelled, promote is the owner's call); S6a MERGED 5 Sep, behind `CHATBOT_BUSINESS_LANE_ENABLED` (default off) until the n8n edit in `n8n-changes.md` S6a is made
UAC: `documentation/plans/chatbot/chatbot-turn-engine-acceptance-criteria.md`
Classification: **MODULE** (`chatbot`), own Postgres schema `chatbot` (D12)
Owner decisions: D1 to D13 in the UAC; rulings R1 to R6 in the UAC
Source maps (scratch, regenerate if lost): n8n spine map + CRM inventory produced 4 Sep 2026
from `sorento_crm_n8n/n8n-workflows-init/export/*` and `sorento_crm_backend/app/*`

## Why

Every chatbot change today is an n8n change: 18 workflows on the turn path, 305 nodes, about
12,000 lines of JavaScript held inside JSON strings across ~120 Code nodes, 165 by-name
`$('node')` reads that no rewiring redirects, and a scheduler whose fan-out order is not stable
(measured 37 vs 612 on the same edge). Nothing greps, nothing type-checks, and the only
regression net is a custom replay harness in the n8n repo. The owner has no confidence in n8n
as a business-logic layer and every change takes a long planning session.

The CRM already owns most of the ingredients: the session store, the ideation turn (the one lane
already built this way), a three-provider LLM client with structured output, a versioned prompt
registry with an admin UI, the entity resolver, the MCP catalog and an in-process MCP client,
the access, team, assignee and SLA services. What n8n adds on top is the glue and the state
compiler. That glue is what moves.

## What exists (measured)

### n8n turn path (live spine `S4N1LiisAqA4hpMC`, export `spine-rs-1a`, 2 Sep 2026)

| stage | n8n today | lines JS |
|---|---|---|
| ingress + dispatch | `sorento-main` webhook > redis `q:{contact}` + `ready-contacts`; `sorento-dispatcher` 1 Hz tick, per-contact `INCR` lock TTL 120 s, calls the spine | small |
| media intake | `sub-media-intake` > `POST /external/media/process` (CRM), patches transcript into the envelope | 450 |
| head | `get-session-vars` (CRM GET) > `sub-semantic-parser` (gpt-5.4-mini, 48 KB prompt, then `output_exchange.js`) > `check-access` (CRM POST) > `build-ctx` > `route-turn` (13 predicates) | 2,300 |
| lanes | canned x6, `ideate` (CRM POST), `offer_hold`, `low_signal` (gpt-4.1-mini), `out_of_scope` (`sub-escalation` + `sub-human-intervention`), `business_query` / `check_promotion` / `stock_denied` (`sub-main-processing` + 6 subs, up to 5 MCP calls, deterministic answer text) | 7,000 |
| tail | `sub-output`: `build-outcome` > `compile-current-state` (1,948) > `crossdomain-compose` > `PUT conversation-variables` (wholesale) + `sub-sendmsg` + `send-attachments` | 2,400 |

Two LLM calls per turn at most (parser; small-talk clarifier on `low_signal` only). The answer
text on the happy path is deterministic (`output-structurer.js`, 482 lines). The `AI Agent`
nodes in `sub-get-results` are orphaned.

Contracts that carry everything: `ctx` (6 keys), `qf` (27 LLM keys + 69 derived),
`session_vars.variables` (~35 keys, 9 write-only, 1 read-only), `branch_kind` (13),
`_exit_kind` (4), `_fetch_arm` (3), the `sub-output` input (13 nullable values),
`reply = {text, quick_replies, session_patch}`.

External surface n8n touches on the turn path: 14 CRM REST endpoints, 1 MCP endpoint (14 tool
names), 1 direct pgvector SQL on the production DB, 1 OpenAI embeddings call, 2 OpenAI chat
calls, respond.io send / assign / update-contact, 8 redis key families.

Replay corpus in the n8n repo: `tests/fixtures/nodes/<slug>/<node>/*.json`, 1,535 files
(111 MB), 602 real captures across 181 executions, each `{ctx, input, expected, ran}` and
PII-scrubbed; 11 full-execution `worlds`; 5 `regression-guards`; 5 named canaries. Coverage by
`branch_kind` is dense for `not_found`, `out_of_scope`, `access_choice`, `check_promotion`,
`business_query`, `not_supported`, thin for `low_signal` (2) and `ideate` (4).

### CRM (main at `ca9babee3`, 4 Sep 2026)

| capability | where |
|---|---|
| external auth | `X-API-Key` > `get_external_api_user` > integration principal (DB-backed) > RBAC slug via `require_external_permission`; map in `app/api/v1/external/permissions.py` |
| session store | `respond_contacts.session_vars` JSONB; `conversation_variables_service.get_for_contact` / `overwrite_for_contact` (`FOR UPDATE`, wholesale) |
| the pattern | `app/services/ideation_turn_service.handle_turn` + `app/api/v1/external/ideation.py`: fail-closed config, LLM in a never-raising extractor, integration_log on every call |
| LLM | `llm_provider.get_provider(...).chat(messages, json_schema=...)`, OpenAI / Anthropic / Gemini |
| prompts | `ai_prompt_registry` (17 keys, versioned, 60 s cache, DB-down fallback, admin UI) |
| MCP | `sorento_crm_mcp/catalog.py` (40 tools; ideation NOT yet a tool, added in S3 per D6) + `ai_assistant_service.MCPRuntimeClient` (in-process JSON-RPC client) |
| tool search | `EmbeddingReadService` behind `POST /external/rag/tool-search` |
| resolver | service behind `POST /system/references/resolve` (`app/api/v1/system/references.py:2133`), `entity_pins` supported |
| access / teams / assignee / SLA | `mcp_access_service.evaluate_agent`, `ContactAccessTypeService`, `company_routing_service` (team members), next-assignee service (`next_assignee.py`, commits a round-robin cursor), `ConversationSLATrackingService` |
| worker | RQ, 7 queues in `worker.py:DEFAULT_QUEUES`, worker_fast latency split (#569) |
| modules | `app/modules/runtime/module_manifest.py` + `bootstrap.py` per module + `require_module_enabled_with_api_key` |
| settings | `system_settings` singleton, two manual GET dict builders in `user_management/settings.py` |

## Target architecture

### Package (module-private, one public entry point)

```
app/services/chatbot/
  __init__.py            # exports run_turn, complete_turn ONLY
  contracts.py           # Pydantic: Envelope, Ctx, ParseOutput (qf), SessionVars (extra=forbid),
                         #   BranchKind, Reply, Action, TurnResult; every enum as ONE Literal
  engine.py              # run_turn(envelope, *, session_factory) -> TurnResult ;
                         #   complete_turn(turn_id, fragments, *, session_factory)
                         #   A session FACTORY, not a session: the capacity rule below
                         #   forbids holding one across the LLM call, which a
                         #   request-scoped Depends(get_db) session cannot satisfy.
  head/parser.py         # LLM call (prompt key chatbot_semantic_parser), strict schema
  head/output_exchange.py# port of output_exchange.js + suggest-follow-up.js
  head/access.py         # contact-to-agent access check (service behind /external/access-agent/check; not MCP)
  head/route.py          # port of route-turn.js -> BranchKind + item stamp
  lanes/canned.py        # escalate-catalog copy, tag-only arms, offer_hold
  lanes/ideate.py        # calls MCP tool crm_ideation_turn (D6), folds session_vars.ideation
  lanes/casual.py        # low_signal: resolve for prompt + clarifier LLM + central-exchange
  lanes/escalation.py    # escalation-input/context/gates + assignment actions
  lanes/business/resolve_gate.py   # get-access-types, resolve-entity, tier-gate,
                                   #   disallowed-entity-gate, pickers, resolve-exit-*
  lanes/business/fetch.py          # tool search, tool-filter, tier-probe, entity-ids-transformer,
                                   #   MCP call, output-structurer, fetch-result
  lanes/business/answer.py         # validator, promo-picker, crossdomain-*, build-result,
                                   #   sub-answer, sub-miss-suggest, build-suggest-offer
  tail/outcome.py        # build-outcome (15-key map)
  tail/compile_state.py  # compile-current-state -> SessionVars
  tail/compose.py        # crossdomain-compose + reply seal
  copy.py                # registry keys for canned replies (fallback = today's text)
  delegate.py            # migration-only: the {delegate, ctx, item} envelope for n8n lanes
  dispatch.py            # S7: per-contact FIFO ticket in redis, inside the request
app/api/v1/external/chat.py      # POST /chat/turn, POST /chat/turn/{id}/complete
app/tasks/chat_turns.py          # RQ: run_turn_job, optional offload behind CHATBOT_TURN_ON_WORKER (S7)
app/models/chatbot_turn.py       # chatbot_turns inbox
app/modules/chatbot/bootstrap.py # MODULE_KEY = "chatbot"
tests/chatbot/                   # replay + unit + endpoint + inbox + boundary
tests/fixtures/chatbot/          # vendored golden subset (< 3 MB)
```

Boundary rule (guardrail test): nothing outside `app/api/v1/external/chat.py`,
`app/tasks/chat_turns.py`, `app/modules/chatbot/`, `tests/chatbot/` imports
`app.services.chatbot`. The package imports core services freely. That is the whole
"liftable later" story: the day a measured trigger fires, the package moves behind an HTTP
boundary with the same contracts. **Lift trigger (named, not built):** p95 turn latency above
`chat_latency_p99_target_seconds` for a week, or API-box CPU above 70 percent sustained with
the chatbot queue as the top consumer. Until then it is a modular monolith.

### Transport contract with n8n (D4, D9, D14)

Synchronous at every stage of the migration and at the end state. The caller sends.

```
POST /api/v1/external/chat/turn            body { envelope: A }
  -> 200 { turn_id, ctx, item, branch_kind, delegate: "<lane>" | null,
           reply?: {text, quick_replies, result_set, attachments_src},
           actions?: [...], session_patch?: {...} }      # session_patch only on dry run
POST /api/v1/external/chat/turn/{id}/complete   body = sub-output input contract (S2 to S6)
  -> 200 { reply, actions, session_patch? }
```

`delegate` names the n8n lane that must still run during migration (`business_query`,
`check_promotion`, `stock_denied`, `out_of_scope`, `low_signal`); n8n's `route` Switch
shrinks by one output per migrated lane. `delegate = null` means the CRM finished the turn:
the caller sends `reply` and executes `actions`. From S7 there is no `/complete` and no
`delegate`.

`actions[]` vocabulary (the caller executes, in order): `send_message {text, quick_replies,
result_set}`, `send_attachments {attachments_src, reply}`, `assign_conversation
{respond_user_id}`, `add_comment {text, mention_user_ids}`, `update_contact_fields {fields}`.
Every action carries `dry_run` (true on test envelopes, D14) so the clone's `test-guard`
records instead of sends, exactly as today.

**D14's input half (O2, AC-112).** A dry-run envelope may also carry three optional harness
keys, and the engine honours them ONLY on a dry run: `mock_reformulator_output` replaces the
parser call (no provider is asked; the mock goes through the same `post_process` +
`suggest_follow_up` a real emission does, so the harness exercises the code instead of
bypassing it, and a malformed mock is a failed `understood` stage exactly like a malformed
model answer), while `previous_conversation_state` and `referenced_result_set` replace the
stored memory for that turn and are never written back. They are `Envelope` EXTRAS rather
than declared fields on purpose: a harness contract that a live producer should have no
reason to reach for. On a live envelope all three are ignored and listed in the `received`
record's `harness_keys_ignored` (empty list when there are none), so a stray key is visible
rather than silently answering a real customer from a mock. Tests are named after the n8n
guards they replace: `TestHarnessInjectionsG6` (reformulator bypass),
`TestHarnessInjectionsG8` (session injection).

**Why not an outbound webhook (rejected at review round 3):** a fixed CRM-to-n8n URL would
decide egress on the CRM side, so a chat-console or clone turn would push to the live sender.
Returning the data keeps egress with the caller and keeps the harness's containment model
(`plans/spine-decomposition-plan.md` G1 to G10) intact. n8n already waits the whole turn
(`call-spine` `waitForSubWorkflow: true`), so nothing gets slower.

**Per-contact ordering moves to the CRM at S7 (round 4, owner: 50 dealers, 100 questions at
once).** The n8n dispatcher pops ONE contact per 1 s tick, so a 50-contact burst is served one
per second regardless of what the CRM does. From S7 the request itself serialises per contact:
on arrival `ticket = INCR chatbot:seq:{contact}` (expire 1 h); the request waits (200 ms poll,
max `CHATBOT_QUEUE_WAIT_SECONDS` = 45) until `chatbot:done:{contact} == ticket - 1`, runs the
turn, and advances `done` in `finally`. A waiter that sees `done` stalled with no
`chatbot:running:{contact}` key for more than 2 s (predecessor process died) repairs the
counter and proceeds; both paths are pytest-covered. Different contacts never wait on each
other. The dispatcher and its redis lists are retired; n8n's ingress posts each message
directly. Until S7 the dispatcher stays and bounds load at ~1 turn/s. The CRM inbox row stays a
record and a trace, never a queue. Retry from the trace screen re-posts the envelope through
the same ordering; the CRM never sends.

**Switchover must survive S7 (AC-714).** The carve state (`failover_watermark`), the producer's
`in-failover?` gate and the poller stay exactly as they are; the only S7 change on each
injector is "push to redis" becoming "call the thin spine". Both injectors flip in the same
promote (the concurrency plan's own lesson). Clone run: carve, message via poller, un-carve,
message via webhook, duplicate during the switch runs once.

**Webhook fallback (D15).** The failover poller (`CYNq34WZx83POLQ5` > `sorento-main-INJECT`)
and the webhook producer are two injectors of one envelope shape; both call `/chat/turn`. The
engine is idempotent per respond `message_id` (`chatbot.turns` unique on
`(contact_respond_id, message_id)`): a duplicate returns the original reply with
`duplicate: true` and the caller's Switch sends nothing. The poller posts a buffered batch in
respond timestamp order; the per-contact ticket keeps it in order and never interleaves it
with a live message. The carve state (`failover_watermark`) stays in n8n's own tables.

**Worker offload is optional** (`CHATBOT_TURN_ON_WORKER`, default off): enqueue on `chat` and
wait for the result inside the request, the pattern `/external/media` already uses. Built in
S7 behind the flag, switched on only when the lift trigger is measured.

### The `chatbot.turns` inbox and trace (D12, D13)

Schema `chatbot` (migration does `CREATE SCHEMA IF NOT EXISTS chatbot`; model pins
`__table_args__={"schema": "chatbot"}`). One table, `chatbot.turns`: `id uuid,
contact_respond_id text, envelope jsonb, is_test bool, status
(processing|delegated|done|failed), stage text, branch_kind text, error text, attempt int
default 1, message_id text, ingress text, trace jsonb, created_at, started_at, finished_at`, index
`(contact_respond_id, status, created_at)`, UNIQUE `(contact_respond_id, message_id)` (D15), plus `shadow_of text null` (the n8n turn id
when the row is a shadow-mode dry run, gate 4). A row is created by `/turn` and closed by
`/complete` (or by `/turn` itself when `delegate = null`), status `delegated` in between. It
is a record and a trace, never a queue (the dispatcher in n8n is the queue). Retention: 90
days, pruned by the existing scheduler sweep pattern.

`trace` is an ordered array of stage records written by the engine as each stage ends:

```
{ stage: received|understood|access|routed|looked_up|replied|remembered|sent,
  status: ok|failed|skipped, started_at, ms,
  summary: "Understood as a business query about product SRTWC8517, dealer tier",
  why:     "Routed to the business lane: access allowed, no escalation asked",
  facts:   { ...small flat dict for the UI rows... },
  error:   "...one sentence..." | null,
  raw:     { ...technical payload, byte-capped like the AI trace... } }
```

`summary` and `why` are sentences produced by the engine from structured state (D11: never
from the customer's text), so the screen in S2b renders words, not JSON. `raw` feeds the
"Technical details" viewer. The n8n `state_trace` on `chat_histories` keeps being written by
the S1 head for the existing StateTracePanel until S2b replaces that panel.

### Session state contract

`SessionVars` is a Pydantic model with `extra = "forbid"`. Allowlist = every key
`compile-current-state` writes today (R2: the owner keeps all of them, including the nine
with no reader yet): `message_type, intent_hint, domain_hint, user_goal, query_scope,
query_brands, access_levels, entities, routing, escalation, response, last_result_set,
selection_context, date_filter_start, date_filter_end, date_mode, requested_attributes,
match_mode, contains_flyer, dym_offer, dym_candidates, ideation, dym_last_result_set,
tier_menu, picker_last_result_set, picker_families, picker_domain, picker_selection_context,
picker_families_carried, routing_roster_plan, routing_brand, routing_brand_source,
routing_company, routing_companies`, plus the new `pending {kind, team?, domain?}` marker
(R3). `extra = "forbid"` still matters: it is what stops harness keys leaking into customer
sessions (H15). `is_active` stays a phantom read (the parser port reads it as null).
Top-level siblings `user_response` and `quick_reply` persist as today. The ideation service
keeps writing `ideation` through the same store (already in-process, already the CRM).

### Text-sniffing inventory (D11)

The owner's rule: understanding text is the parser's job; everything after it is
deterministic over structured state. The port reproduces existing behaviour first (D8), so
every place the JS matches raw customer text or a previous reply outside the parser is
inventoried during S1 and listed here with its disposition:

| site | what it matches | disposition |
|---|---|---|
| `output_exchange.js` `offeredEscalation` regex over previous `response` | "would you like me to escalate" | replaced by `pending.kind = escalation_offer` (R3, S1/S2) |
| `crossdomain-compose.js` `isAnswered` regex over previous `response` | "Previous turn (" | replaced by `pending.kind`/`last_answer_domain` (R3, S2) |
| `route-turn.js` `tierRepick` | bare digit or exact menu word in the raw message | reproduced (owner's own Fix 6 rule; exact match, not fuzzy); candidate to move into the parser as `tier_pick` after parity |
| `escalation-context.js` `_CO_ALIASES` company name / code match | company name or alias in `escalation.company_pick` | reproduced; the parser already emits `company_pick`, the alias table is a STOPGAP mirror, candidate to delete once the parser output is trusted |
| `output_exchange.js` `domain_switched_by_keyword` and sibling keyword checks | domain keywords in the raw message | reproduced for parity; listed as divergence candidates for the parser prompt (backlog issue) |
| `output_exchange.js` `_coCompanyPick` deterministic tier | the reply minus fillers, word-boundary matched against the offered company pool; refused by a negator or a product-code-like token | reproduced (5 Sep re-port): the LIVE body still has it. The export's rev 8 deletes it and hands the whole job to the prompt, but rev 8 is the unpromoted B-TEAM-1' change, so parity keeps the tier until the owner promotes it |
| `output_exchange.js` member-offer `extract()` + `_ORD` | a bare number or an ordinal WORD in the raw reply | reproduced; the same shape as `route-turn.js` `tierRepick` and inventoried with it |
| `output_exchange.js` `_statedTiers` / `_statedBrands` | tier and brand words in the raw message (English and Malay literals only) | reproduced. The prompt is what covers every other language, which is why the ACCESS LEVELS vocabulary cannot move out of it |

Rule for new code in the package: no regex or substring match over `ctx.text` or over a
previous reply. A reviewer finding one is a merge blocker.

### Configuration (D5)

| what | where | why here |
|---|---|---|
| parser prompt, clarifier prompt | prompt registry keys `chatbot_semantic_parser`, `chatbot_clarifier` | versioned, admin UI, per-key model override already exist |
| canned replies (7) | prompt registry keys `chatbot_reply_*` | same store, owner journey B |
| respond.io `space_id` | default respond workspace row (`respond_workspaces.space_id`) | already the integration's home; kills the hard-coded `364817` |
| unsupported domains | `system_settings.chatbot_unsupported_domains` (JSON, default the two today) | the one list the owner has changed; column, not table (CLAUDE.md "both dict builders") |
| stock denial lanes | `system_settings.chatbot_stock_denial_enabled` (bool, default false) | R1: the corrected vocabulary turns two never-tested lanes on; a data switch with a test, not a surprise |
| worker offload, wait | env `CHATBOT_TURN_ON_WORKER` (off), `CHATBOT_TURN_WAIT_SECONDS` (60), `WORKER_QUEUES` | ops, not owner |

### Test strategy (the reason for the port)

1. **Node replay (golden, written first).** For each ported node, `tests/chatbot/test_replay.py`
   parametrises over `nodes/<slug>/<node>/*.json`, feeds `input` + `ctx` to the Python port,
   compares to `expected` after a JSON round trip. Corpus path from `CHATBOT_FIXTURES_DIR`
   (default: the sibling checkout); absent = skip. A curated subset (one fixture per node per
   `branch_kind`, the 11 worlds, the 5 regression guards, the 5 canaries; under 3 MB) is
   vendored to `tests/fixtures/chatbot/` and always runs, in CI too.
2. **Divergence register.** `tests/chatbot/divergences.py` lists `(node, fixture, hazard,
   reason)`. A mismatch passes only if registered. This is how "parity before improvement"
   (D8) is enforced mechanically.
3. **World replay.** The 11 `worlds` run end to end through `run_turn` with the LLM, MCP,
   resolver and access services stubbed from the world's captured node outputs. Asserts
   `reply.text`, `quick_replies`, `session_patch`, `actions`.
4. **Contract tests.** Enum single-source (H28), `SessionVars` allowlist (H15), by-entity-type
   iteration (H16), `_isTimeline` sentinel (H46), dry-run before side effects (H37).
5. **Endpoint + dry-run tests** on Postgres via `tests/_pg_fixture.py` (`ZZT` prefix, scoped
   deletes): auth 401/403, module guard, dry-run writes nothing (row counts), failure path,
   retry re-push.
6. **Live LLM parity (opt-in, not CI).** `scripts/chatbot_parser_parity.py` replays the
   `regression-guards` inputs through the live parser N times and diffs against `_parser_raw`.
   Run before S1 promote and whenever the prompt key changes.
7. **Clone smoke (n8n side, unchanged).** The existing 15-turn clone set + canaries, run per
   slice via the n8n repo's harness in `uac` mode. This is the E2E gate before each promote.

Backend tests run on Postgres only. Brief for the tester names exact files; never the full
suite on the shared DB.


### Capacity and safety of the synchronous turn (owner question, round 3)

- Until S7, intake is capped by the n8n dispatcher (one contact per second). From S7 the
  target is the owner's burst: 50 dealers x 2 questions = 100 turns at once. First questions
  all run in parallel (5 to 10 s), second questions wait only for their own contact (10 to
  20 s), last reply of the burst about 20 s instead of about 65 s today.
- At 100 concurrent: API threads 150 of 320 busy (running + waiters); Postgres behind
  PgBouncer (compose) with the no-session-across-I/O rule; ~50 parser calls in flight at the
  LLM provider (429 = failed stage with backoff); MCP server run with 2 to 4 workers; **n8n
  queue mode's per-worker concurrency limit (default 10) is the first throttle** and is a
  config change (`N8N_CONCURRENCY_PRODUCTION_LIMIT` or more n8n workers). Beyond ~250
  concurrent, API threads become the limit: turn on the worker-offload flag and add replicas.
- Sync vs async does not change any of this; a callback design would have moved the same
  work and left the 1/s dispatcher in place.
- API: `WEB_CONCURRENCY: 8` uvicorn workers (compose), default 40-thread pool each for sync
  routes. DB: `pool_size=10, max_overflow=20` per worker (`app/database.py`).
- **Rule: never hold a DB session across LLM or MCP I/O.** The engine closes the session before
  the parser / clarifier / MCP calls and reopens after (the 96/100 connection incident is the
  evidence). Guardrail test asserts no open transaction during the parser call.
  - **ONE named exemption, S6a's resolver seam** (5 Sep 2026). The business lane runs inside
    the session opened for access / routed, so that session is held across the resolver's
    OPTIONAL spec-search model call (2 to 3 s, only when `understand_phrase` fires and the
    normal probes missed). It is an exemption rather than a bug because the resolver is a
    database service - it cannot be called without a session at all - and because the
    connection count is unchanged from today: n8n makes the same call over HTTP while its own
    request holds a pool connection for the whole turn. What is different is only WHERE the
    connection is held. **Trigger to remove it: S6b**, which adds the MCP fetch call and
    splits `looked_up` into its own stage; the session closes before that stage and reopens
    after, exactly as the parser call already does. Pinned by
    `tests/chatbot/test_s6a_gate_dry_run_and_seams.py::TestCapacityRuleDuringResolverSeam`,
    an `xfail(strict=True)` that goes red the day the split lands and the exemption should
    be deleted.
- Timeouts: n8n HTTP node 60 s explicit; parser 8 s **(bound not enforced until #656)**; each
  MCP call 10 s; over = failed stage. The parser bound is not wired because
  `llm_provider.LLMProvider.chat` takes no timeout at all - each provider builds its own
  SDK client - so enforcing it means changing that shared signature and all three
  implementations, which is core work this program does not own. A declared-but-unapplied
  constant reads as a guarantee, so S1 ships without one rather than with a fiction.
- Isolation when measured: a second backend container from the same image, nginx routes
  `/api/v1/external/chat` to it. That is the lift trigger's first step; no code change.

### Cutover ladder (five gates, each with an exit number)

0. **Corpus growth, every slice** (owner: 1,535 fixtures and 11 worlds are a floor). Before a
   slice PR opens, re-capture the nodes it ports from fresh live executions with the n8n
   repo's `scripts/capture-fixtures.py` + census recipe until every branch of every ported
   node has at least 5 real captures; grow worlds to 100+ with at least 5 per `branch_kind`
   and per shape (picker, did-you-mean, tier ask, escalation, offer-hold, media), including
   multi-turn worlds (3 to 5 turns of one contact) for the memory paths. Shadow mode (gate 4)
   keeps adding captures. Coverage matrix lives in `tests/chatbot/COVERAGE.md`, regenerated by
   `scripts/chatbot_fixture_coverage.py`; an empty cell blocks the slice.
1. Node replay (CI): 100% equal or registered divergence; per-node coverage target met.
2. World replay (CI): reply, quick replies, session patch, actions equal on every world.
3. Clone smoke before each promote: same lane and text as the pre-S1 baseline, zero egress.
3b. **Load** (round 4): `scripts/chatbot_load.py` fires 100, then 300, concurrent dry-run turns
   (50 contacts x 2 messages, `is_test: true`, real LLM behind `--live-llm`) at the lane's
   backend. Exit: p95 under 12 s, zero errors, DB pool below 60%, per-contact order preserved
   (ticket order == reply order), n8n concurrency limit raised to match. Runs before the S7
   promote and after any latency-adding change (the "spine p99 vs lock TTL" check the n8n
   plan asked for).
4. **Shadow mode** (new): the live spine also calls `/chat/turn` with `is_test: true` and keeps
   its own reply; the CRM stores its would-be reply beside n8n's actual one
   (`chatbot.turns.shadow_of = <chat_histories.turn_id>`). Exit on 500 consecutive live turns:
   branch parity 99%+, reply-text parity 97%+, every mismatch triaged, p95 under target, zero
   writes proven by row counts. Run at S1 (head) for 3 to 7 days and at S6c (full turn) for 3
   to 7 days. Costs one extra HTTP call per turn during the window; needs nothing beyond D14.
5. Pilot one contact, then one company, then all; no failed turns for 48 h before widening.

### Growth axes (owner question: more tools, more reasoning, horizontal scale)

Same six-layer shape as `PLAN-ai-assistant-architecture.md`. Each axis grows by configuration
and is proven by the ladder above, never by rewrite:

| axis | after this program | grows by |
|---|---|---|
| tools | MCP catalog (40 + `crm_ideation_turn`, which tool search can also pick like any other tool), embedding tool search | one `ToolSpec` + sync; rendering migrates to MCP presenters |
| understanding | registry prompt, strict schema, per-key model | registry publish replayed against the corpus first |
| reasoning | deterministic lanes (parity) | per-lane strategy flag `deterministic` / `agent`; `agent` reuses `ai_assistant_service._run_agent_loop` (tool budget `ai_assistant_tool_call_limit`, write tools stripped on dry run) behind the same Reply / actions / SessionVars contracts; on per lane, per tenant, measured in shadow mode |
| memory | allowlisted session vars | `FrameService` frames from the one Remembered stage |
| evals | replay + shadow | shadow mode permanent for any candidate; judge from `PLAN-ai-assistant-evals-guardrails.md` |
| scale | stateless engine, 8 workers, state in Postgres + Redis | replicas, dedicated chat container, worker offload flag; per-tenant rows, never code branches |

Sequencing: parity first (this program), agent strategy per lane afterwards, behind shadow
mode. Two unknowns at once (new engine + new reasoning) would have no baseline.

## Slices

Each slice = one lane branch = one PR, independently deployable, revertible by re-wiring n8n
(old nodes stay disabled one release). n8n edits follow the n8n repo's plan-build-test-promote
flow; promotion is the owner's call each time. Line counts are the JavaScript being ported.

### S0 - Scaffold (with S1 in the first PR)

Module bootstrap + manifest entry (deps: `base, product, inventory, order, marketing,
procurement, resources, sla`); `chatbot` schema + `chatbot.turns` migration with the `trace`
column and stage writer (AC-003, AC-007; chain onto the current main head,
`scripts/alembic-reparent.sh` at pre-PR gate); `contracts.py` with every enum; slug
`integration.chat_turn.submit` in `EXTERNAL_ENDPOINT_PERMISSIONS` + grant migration for the
n8n integration role; router mount; replay harness + divergence register + vendored subset;
import-boundary test. AC-001 to AC-006.

### S1 - Head (2,300 lines)

`head/parser.py` (prompt key + strict `ParseOutput` schema; model from `agent_model` override
else AI-assistant config; temp 0), `head/output_exchange.py` (1,882 + 55: the deterministic
post-processor, including `deriveRouting` and the dash normaliser), `head/access.py`,
`head/route.py` (245: the 13 predicates, lazy, in ladder order; tier re-pick; `TAG_ONLY`
item shape). `engine.run_turn` up to routing; `delegate.py` returns the n8n envelope.
Human-intervened check becomes an `update_contact_fields` action (AC-108). Audio-not-patched
becomes a failed turn (AC-107). R3 reader accepts both forms. R5 fail-loud.
n8n: replace five spine nodes with one `httpRequest` + two re-emitters (AC-110).

#### S1 pending re-port: B-TEAM-1' (added 5 Sep 2026)

**The port was made from the working-tree EXPORT, and the export is not what production
runs.** The n8n partner session fetched the LIVE `sub-semantic-parser` read-only and the
two bodies differ:

| | live | working-tree export |
|---|---|---|
| `output_exchange.js` | 1,881 lines, sha `a837333a13a2` | 2,043 lines, MANIFEST `locally_edited` |
| system message | 46,942 chars, sha256 `90c0741997...bdf87b66` | 49,318 chars |

The extra material is one unpromoted lane change, **B-TEAM-1'** (+241/-83 over 10 hunks):
`routing.team_source`, a 4-rank team ladder replacing the `?? 'customer_service'` default,
a `resource_attachment` row in `deriveRouting`, a pending `team_clarify` completion block,
and a state-only company-pick resolver with the deterministic word-match tier deleted.

`head/output_exchange.py`, `head/parser.py`'s `ParseOutput` schema and
`chatbot_parser_prompt.py` are now faithful to the LIVE body. Evidence, both directions:

* the five `parser-*` fixtures that sat in `STALE_FIXTURES` because the port emitted a null
  team where they expect `purchasing` / `marketing_product` / `warehouse` now replay EQUAL,
  and their entries are retired. They were live-faithful captures graded against the wrong
  body, which is what a stale-fixture list looks like when the port is the stale side;
* the 19 hand-built fixtures that now fail are reproduced EXACTLY by the pre-re-port Python
  and by nothing else (19 of 19, no residue). They pin the unpromoted body, so they take
  those entries instead. **Every real capture in the corpus is graded; not one `parser-*` or
  `exec-*` fixture is excluded.**

**Re-port B-TEAM-1' when the owner promotes the escalation-routing lane's B3 step**, and
retire the 19 entries in the same change. Diffs:
`output_exchange.LIVE-vs-WORKTREE.diff` and `output_exchange.HEAD-vs-LIVE.diff` in the n8n
session scratchpad (`.../11a092cf-e08a-4fa0-b142-99499e993633/scratchpad/`), beside
`output_exchange.live.js` and `sub-semantic-parser.systemMessage.live.txt`. Nothing goes in
`divergences.py`: this is parity with production, not a deliberate hazard fix.

One consequence worth stating, because it reads as a regression and is not: with the live
body the LLM's own `suggested_team` is used ONLY on a `request_for_help` turn, and every
other turn falls through `deriveRouting` -> prior state -> the hard `customer_service`
default. This body therefore never emits a null team, and `resource_attachment` routes by
the prior-state carry rather than to `marketing_product`.

**The Switch on `duplicate` must sit BEFORE the `build-ctx` / `route-turn` re-emitters.**
A duplicate delivery (D15) returns the FIRST turn's stored answer, and a duplicate of a
turn that FAILED has no `ctx` to replay - the re-emitters read
`$('build-ctx').first().json.ctx.<key>` and throw on a null. Gating first also skips the
work n8n would otherwise redo for a message it must not answer twice. The CRM persists
`ctx` and `item` on `chatbot.turns.response` precisely so the happy-path duplicate has
something real to hand back; the ordering is what stops the failed-turn case throwing.
Parity gate: AC-102, AC-103, AC-111.

### S1b - Parser prompt slim-down (same lane as S1, after parity, before promote)

D16. Inventory the 46 KB system message section by section
(`documentation/plans/chatbot/parser-prompt-inventory.md`): `understanding` stays;
`rule` moves into `output_exchange.py` where it already has a deterministic twin; `example`
survives only when it stands for a phrasing class the corpus shows; `dead` goes. AC-151 to
AC-155. This is where the owner's "no overfitting, no bloat, LLM only for language" lands.

**Delivered (5 Sep 2026), on the LIVE body after the re-port above.**

* 46,906 -> 28,124 characters, **-40.04%** (AC-154). Published as registry version 2 with
  NO label by migration `475_chatbot_parser_prompt_slim`; `production` stays on version 1,
  so the promote is a label move and the rollback is the reverse move. The migration seeds
  both on a fresh database.
* Six `rule` sections deleted, all six with an existing twin in `output_exchange.py`
  (domain-to-team map, the `business_query` force, the `attachment_type` drop on
  `master_products`, the `broaden_axis` domain restore, the brand-plus-tier access-level
  split, the legacy promotion-team suffix). Four `dead` sections deleted, including 700
  characters of n8n JavaScript the registry cannot evaluate and hands to the model as
  source code. **No new post-processor code**: `output_exchange.py` is untouched by S1b.
  Unit cover in `tests/chatbot/test_output_exchange_rules.py`, every case feeding a
  deliberately non-compliant emission.
* Date maths, `demand_qty` and ordinal resolution were each investigated and REJECTED as
  moves, on evidence, in the inventory. Two date gates were measured against the replay
  corpus and would have rewritten fixtures the post-processor deliberately produces.

**AC-153's 99% bar cannot be met by any prompt, and the measurement says why.** A control
run sending the LIVE prompt down BOTH lanes agrees with itself on only 99.0% of key
instances, and on the free-prose `user_goal` only 81.6%. The parser is not deterministic at
temperature 0. Old vs new is 95.8% post-processed (97.5% excluding `user_goal`), i.e. 3.2
points from the noise floor, with every disagreement triaged: 13 improvements, 11
regressions, 20 "neither matches the capture", 38 noise, 1 ungraded, zero untriaged. The
regressions are enumerated in the inventory and none is systematic. **Owner call at
promote**, and the bar in AC-153 should be restated against the measured floor.

**AC-155 could not be met as written**: the corpus contains no Malay capture at all (249
real captures, zero). The parity script uses eight real corpus turns with the message
translated and the real previous state kept, labelled `synthetic-from-corpus`; seven of the
eight agree on every key. Capturing real Malay turns is a backlog item.

### S2 - Tail (2,400 lines)

`tail/outcome.py` (117), `tail/compile_state.py` (1,948 > `SessionVars`), `tail/compose.py`
(110), `copy.py` (escalate-catalog 104, registry keys), CS member offer (23 + 163, team
members in-process). `engine.complete_turn` writes session vars via
`overwrite_for_contact` and closes the turn. R2 drops, R3 marker written.
n8n: `sub-output` body + `save-session-vars` replaced by `/complete` (AC-207). After this PR
the CRM is the only session writer on the turn path (AC-207 grep is the proof).
Parity gate: AC-202, AC-204, AC-205, AC-208.

### S2b - Turn trace in Chat History (FE first, then a read endpoint)

The one screen in the program (D13). **Phase 1:** `ChatTranscript` gains a `TurnPanel` under
each incoming message (replaces `StateTracePanel` once S2b ships): status line, stage timeline
in sentences, failed-stage reason + Retry + "Technical details" (`SearchableCode`), Kept / New /
Cleared memory rows; a "Failed turns only" filter on the list. Built against a mock in
`services/chatbotTurnService.ts` with the contract at the top of the file. Verified with
agent-browser from `/` via System > Chat History at 375 and 1280. **Phase 2:**
`GET /api/v1/system/chatbot/turns` + `POST .../{id}/retry` (`app/api/v1/system/chatbot.py`,
reads `chatbot.turns`, slugs `system.chat_history.view` / `.manage`), mock swapped at the
service boundary. AC-251 to AC-259. Mockup: review page section 10.

### S3 - Canned lanes, offer-hold, ideation (150 lines + bridge)

Eight branch kinds complete inside `run_turn` (AC-301). Copy via registry (AC-302). Ideation
as MCP tool `crm_ideation_turn` (new catalog entry + `sync_catalog`, AC-303, AC-307), called
through `MCPRuntimeClient` like every business tool. `chatbot_unsupported_domains` column + both dict builders + schema
(AC-304). n8n: eight Switch outputs and eleven nodes deleted, one `delegate == null` gate added
(AC-305). This is the first PR that makes n8n visibly smaller.

### S4 - low_signal (150 lines)

`lanes/casual.py`: resolve-for-prompt (in-process), `construct-user-prompt` port, prompt key
`chatbot_clarifier`, `central-exchange` fence-stripping. Error = failed turn + today's text
(AC-403). n8n: three nodes deleted (AC-404).

### S5 - Escalation (400 lines)

`lanes/escalation.py`: `escalation-input`, `fresh-entity-gate` (calls S6a's resolve + gate,
so S5 lands AFTER S6a, or ships with a temporary in-process call to the resolver only; decide
at ticketing, default = after S6a), `escalation-context` (six-rank ladder, null never
defaults, H27), team / company clarify gates and replies (`pending.kind`), assignment path as
`actions[]` with next-assignee + SLA create in-process behind a dry-run gate evaluated first
(H37). H2 is structurally impossible in one function (AC-505). n8n: four spine nodes deleted,
two subs unpublished; the outbound executes assign / comment (AC-506).

### S6 - Business lane (about 7,000 lines, three PRs)

- **S6a resolve + gate (1,500):** `get-access-types`, `resolve-entity` (references resolve
  service, `entity_pins`, H38), `tier-gate` (230), `disallowed-entity-gate` (1,001),
  `build-ctx-resolved`, incoming / customer pickers (157) with their probes,
  `resolve-exit-*`. H16, H46 contract
  tests. Ships behind `delegate` for the fetch step: `/turn` returns `_exit_kind` + `ctx'` and
  n8n's `sub-main-processing` enters at `resolve-arm`.

  **As built (5 Sep 2026), four things the slice learned and the plan did not say:**

  1. **A config flag, not a silent cutover.** `CHATBOT_BUSINESS_LANE_ENABLED` (default
     FALSE) decides whether the three business arms run the lane. It exists because the n8n
     edit is a separate, hand-made, owner-gated step: until it happens n8n still calls
     `sub-resolve-and-gate` itself, so an unflagged CRM would run the resolver twice on
     every business turn, spec-search model call included. The flag is the shadow window's
     switch and the rollback. See `n8n-changes.md` S6a.
  1b. **n8n retries `resolve-entity`; the port does not.** The httpRequest node carries
     `retryOnFail` and the in-process call has no equivalent, so a transient resolver
     failure that n8n would have survived becomes a shadow-lane failure here (recorded at
     `looked_up`, turn still delegated). Deliberately not added: an in-process call to a
     local service has none of the failure modes a network hop does, and a retry around a
     database call that has already opened a transaction is its own hazard. Revisit if the
     shadow window shows any resolver failures at all; that is the same evidence gate the
     cutover already has.
  2. **The pickers' probes need S6b.** `probe-incoming` / `probe-customer-orders` call
     `sub-get-results`, whose `entity-ids-transformer` and `output-structurer` are S6b, so
     the S6a probe seam raises and both annotators take their own documented UNPROBED arm
     (bare picker with `customer_probe_skip_reason: 'probe_unavailable'`; today's "None of
     these have incoming stock right now."). That is a real difference on picker turns and
     it is the reason the shadow window has to include picker traffic.
  3. **H50 is REPRODUCED, not fixed.** The plan said "brand / company carried once from the
     resolved row (H50)". Carrying it once changes `resolved_company` /
     `resolved_companies` / `routing_brand` / `routing_companies` on real turns, and D8
     says parity before improvement: a fix is a separate, named, tested divergence, and
     there is no evidence yet about which of the node's two derivations is the right one to
     keep. Ported faithfully; the trigger for the fix is a captured turn where the two
     disagree and the owner says which is correct.
  4. **Every capture predates two output keys the shipping bodies emit.** All 254 captures
     were taken against `disallowed-entity-gate` at 934 lines and `tier-gate` at 195; the
     export ships 1,001 and 230. The delta is five changes, of which two are unconditional
     new keys (`specific_options`, `tier_pick_domain`). They are excluded from the replay
     comparison and carry unit tests instead - see `tests/chatbot/_corpus.py`
     `CAPTURE_BODY_ADDITIONS` for the evidence. With them excluded, 212 of 212 gate
     captures, 6 of 6 tier-gate captures and 10 of 10 whole-sub replays are byte-equal.
     **Superseded 5 Sep** by a capture run against the LIVE sub (`tKeQUkZK5cFK9BFa`,
     version `4f367b1c`, pool 682/682): 84 files whose bodies ARE the shipping ones, so
     both keys are graded on them and nothing is excluded. The exclusion is now applied per
     FIXTURE, derived from whether that capture's own `expected` carries the key, so it
     cannot outlive the captures that need it.
- **S6b fetch (700):** tool search in-process (H53), `tool-filter` (59, zero tools = `not_found`
  outcome, H11), tier probe plan / collect, `entity-ids-transformer` (145), `MCPRuntimeClient`
  call at the configured URL (H52), `output-structurer` (482), `fetch-result` (48). Verify the
  live tool-selection distribution before porting any per-tool branch (H49).
- **S6c answer + miss (3,500):** `validator` (46), `promo-picker` (596), `crossdomain-zeroset`
  (151) + probe + `crossdomain-render` (181), `build-result` (88), `sub-answer` (central-exchange,
  miss roster 342, partial dym 553), `not-found-error-message` (667), `sub-miss-suggest`
  (`dym-transform` 561, `dym-annotate` 247, three probes, `family-fetch` via the products
  service), `build-suggest-offer` (925), `access-level-choice-message` (96). H45 one predicate.
  n8n: the whole business lane and seven subs gone (AC-610). Full smoke + canaries (AC-611).

### S7 - Thin spine + CRM per-contact ordering

`/turn` and `/complete` collapse into `/turn` returning the finished reply; `delegate.py` is
deleted. `dispatch.py`: redis ticket FIFO per contact inside the request (AC-709, AC-710).
D14 dry-run asserted by row counts (AC-702). Retry re-posts the envelope through the same
ordering (AC-705). Optional worker offload behind `CHATBOT_TURN_ON_WORKER` (AC-703). Load gate
3b before promote (AC-711). n8n: the dispatcher and its redis lists retired; ingress = webhook
> `sub-media-intake` > one HTTP node > one Switch on `action.kind` over the existing send /
assign / comment nodes; `N8N_CONCURRENCY_PRODUCTION_LIMIT` raised; old monolith unpublished;
the clone calls the same endpoint with `is_test: true` (AC-706). H6, H12, H30, H31, H54 land
here. Pilot on one contact first (AC-707), console containment proven (AC-708), then all.

### S8 - Retire (small)

Legacy regex readers removed (AC-801), disabled n8n nodes deleted and exports refreshed
(AC-802), hazard table closed out (AC-803), n8n repo `CLAUDE.md` updated to say the turn path
is the CRM. Worktree GC.

## Hazard disposition

From the n8n map's 55 catalogued hazards. `fix` = a named divergence with a test;
`reproduce` = load-bearing behaviour kept; `moot` = cannot exist in a synchronous port;
`backlog` = real but not this program.

| id | hazard | disposition |
|---|---|---|
| H1 | `stock_check` vs `check_stock`, two dead lanes | fix S1 + S3: correct vocabulary, lanes behind `chatbot_stock_denial_enabled` default off (R1 resolved). **Flag-off is not byte-identical and that is deliberate:** live still EVALUATES its dead predicate, so a contact with no `is_allowed_stock` custom field makes `custom_fields.find(...).value` throw and the turn dies; with the flag off the port skips the predicate and answers `business_query`. A strict improvement (an answered turn instead of a dropped one), invisible to the corpus because every captured contact carries the field, and visible in shadow mode as a CRM reply where live sent nothing. With the flag ON the throw is reproduced exactly, and the turn is recorded `failed` at `stage = routed` rather than escaping. The 4 Sep capture run found the first real turns the flag would wake: `rs1a-15118057`, `15129939`, `15137785`, `15139158`, all `check_stock` from contacts without stock access, all `business_query` in live and `demand_qty` with the flag on. |
| H2 | clarify-company-reply race | fix S5 (AC-505) |
| H3, H51 | fan-out order, 165 by-name reads | moot; each read enumerated in the port |
| H4a | test surface reaches billable media endpoint | moot in pytest; n8n intake unchanged |
| H5 | audio dead end | fix S1 (AC-107) |
| H6 | second unlocked spine entry | fix S7 (thin spine has one trigger) |
| H7 | orphaned answer LLM | reproduce: no answer LLM (D10) |
| H8, H9, H47 | sendmsg fallback / presign error / mimeType | backlog (n8n outbound, stays n8n) |
| H10 | dark-by-flag nodes | audit at S3; port intent or drop, per node |
| H11 | zero tools = empty turn | fix S6b (AC-604) |
| H12 | empty pop = silent success | fix S7 |
| H13 | frozen string contracts | fix S1 + S2 + S8 (R3) |
| H14 | pending state inferred from text | reproduce the principle: `pending` marker |
| H15 | fresh object literal | fix S2: `SessionVars extra=forbid` (AC-203) |
| H16 | by_entity_type keys rendered | reproduce as contract test S6a (AC-603) |
| H17 to H21, H24, H25 | resolver / MCP data bugs (LESSONS 66 to 85) | backlog, CRM-side, own issues |
| H22, H23 | cross-domain session pollution / dym leak | fix S2 (per-domain allowlist) + verify S6c |
| H26, H27 | escalation brand-blind / hard team default | port the fix S5 |
| H28 | enum drift | fix S0 (AC-109) |
| H29 | carried picker beats born roster | fix S2 (AC-205) |
| H30, H31 | per-contact FIFO + lock TTL | reproduce S7: redis ticket FIFO per contact, contacts parallel; the TTL check becomes load gate 3b |
| H32 | failed turn dropped | fix S0/S7: recorded as `failed` + error reply, manual Retry on the trace screen, no auto-retry (R4 resolved) |
| H33 to H36 | human-intervened sweeper | R6: backlog, own plan |
| H37 | next-assignee before is_test guard | fix S5 (AC-503) |
| H38 | duplicate codes across companies | port `entity_pins` S6a |
| H39, H40 | dym dedupe drop / cert twins | S6c: reproduce first, fix as registered divergence if owner says go |
| H41, H48 | parser prompt weaknesses | backlog (prompt, not port) |
| H42 | menu-word substring mis-map | reproduce exact-match S1 |
| H43 | missing `$4` | moot (in-process call binds domain) |
| H44 | soft default on malformed parser output | fix S1: strict structured output at the provider; anything else = failed `understood` stage, no default routing (R5 resolved) |
| H45 | did-you-mean offers rows already shown | fix S6c (AC-609) |
| H46 | `_isTimeline` contains-sentinel | S6a declares the sentinel and its reading ONCE (`contracts.TIMELINE_SENTINEL` + `is_timeline`, contract test incl. the mixed-array case) - the node that USES it, `output-structurer`, is S6b and consumes that reading rather than re-deriving it |
| H49 | `orders_by_product_list` never selected | verify before S6b |
| H50 | brand / company derived in five places | REPRODUCED at S6a, not fixed: carrying it once changes real turns and D8 wants a named, tested divergence with evidence first. Trigger: a captured turn where the node's two derivations disagree plus the owner's ruling on which wins |
| H52 | raw IP, plaintext MCP, SQL interpolation | fix S6b (config URL); SQL one is `live-respond-close-convo`, backlog |
| H53 | n8n hits production Postgres | fix S6b (tool search in-process); SLA reads by `live-respond-*` backlog |
| H54 | dead custom fields | fix S7 |
| H55 | scope continuity never implemented | backlog after parity |

## Non-goals

- One frontend surface only: the turn trace in Chat History (S2b, D13). Every other slice is
  backend-only and **skips Phase 1 (FE mock) by declaration**; those PR descriptions say so.
- No parser prompt changes in S1 beyond reading the `pending` marker. Parity first; S1b then
  slims the prompt under D16 with the corpus as the regression net.
- No CRM-side WhatsApp sending (D9). The primitive exists; not wired.
- No change to `live-respond-send-user`, `live-respond-close-convo`, the `ht-*` sweeper (R6).
- No multi-tenant resolution work: the module reads `DEFAULT_TENANT_ID` like every other module
  until tenant resolution lands.

## Rollout and rollback

Per slice: PR green (unit + replay + endpoint), clone smoke green on the n8n test clone
against the lane's backend, owner promotes the n8n edit, deploy CRM first then n8n (the CRM
endpoint must exist before n8n calls it; the old nodes still work until re-wired). Rollback =
re-wire n8n to the disabled nodes; CRM endpoint stays, harmless. S7 rolls out on one pilot
contact via the ingress workflow's contact filter, then all.

## Risks

- **Parser schema strictness.** n8n's agent node returns free JSON; the port validates a strict
  27-key schema. A model that occasionally emits an extra key would fail validation where n8n
  tolerated it. Mitigation: the live-parity script before S1 promote; `ParseOutput` ignores
  unknown keys but rejects missing required ones.
- **Fixture staleness.** The corpus was captured against exports dated 28 Aug to 2 Sep. Verify
  exports (`export-workflows.py --verify`) before vendoring the subset; re-capture the thin
  branches (`low_signal`, `ideate`) with the harness before S3 / S4.
- **Synchronous turn latency.** The parser call runs in the API request (2 to 5 s), same as
  the ideation turn today, and the full turn adds MCP calls (up to 5) from S6. Uvicorn's
  threadpool absorbs this at current volume (about 2,200 turns per capture window); the
  worker-offload flag exists for the day it does not.
- **Two writers for `ideation`.** Already true today (n8n nests, CRM writes flat). S2 makes the
  CRM the only writer and normalises to flat.
- **`sub-media-intake` stays in n8n** and still calls the CRM media endpoint. Fine, it is
  transport by D1, but the audio-patch dependency (H5) is now an explicit contract in AC-107.

## Backlog (written to `documentation/backlogs/backlog.md` at ticketing)

Turn inbox UI; CRM-side sending; human-intervened sweeper port (R6); H8 / H9 / H47 n8n
outbound fixes; H17 to H25 resolver and MCP data bugs as separate issues; H55 scope
continuity; parser prompt items H41 / H48; retention job for `chatbot_turns`.
