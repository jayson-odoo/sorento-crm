# PLAN - AI Assistant Per-Node Trace + Role Split (M2 / M2.5)

**Status:** DONE (2026-07-04) - M2 + M2.5 implemented, all UAC (§9) satisfied and verified end-to-end. Uncommitted. See §10 completion record.
**Depends on:** M1 prompt registry (`PLAN-ai-assistant-prompt-registry.md`) - specifically the `prompt_name`+`prompt_version` stamp that lets a span link to the exact prompt variant that produced it.
**Owner:** jayson
**Date drafted:** 2026-07-03

---

## 1. Problem

Diagnosis today = coarse. `AIAssistantUsageLog` (tokens, latency, was_answered) + `Message.metadata_json` (links, sources, `tools_used[name,ok]`). You cannot see, per turn:
- what the reformulator received vs emitted,
- which tools were called with which args and what they returned,
- what each LLM round reasoned/decided,
- where a bad answer diverged.

No n8n-style "click a node, see its input and output." And the agent loop is a **monolith** - plan + reason + tool-call + synthesize fused in one LLM call site (:1322), so even with a trace it's one opaque box.

## 2. Goal

Two coupled deliverables:
- **M2 - Trace/spans:** one **trace** per turn, nested **spans** per node, each with typed input/output + model + tokens + latency + `prompt_version`. FE waterfall/tree; click a node → in/out panels. Schema aligned to **OpenTelemetry GenAI semantic conventions** (`gen_ai.*`) so we can export to Langfuse/Phoenix/any OTel backend later for free.
- **M2.5 - Role split:** break the agent monolith into explicit nodes - `planner` → executor/`agent_system` → `synthesizer`, plus `semantic_compressor` (raw tool JSON → token-tight sentences, Grafana 4x pattern). Each split node = its own prompt key (already seeded dormant in M1) + its own trace span. You split *because* the trace makes the monolith visible.

## 3. Data model (draft - from research §3)

Two tables. Trace = root, spans = tree.

### `ai_assistant_traces`
```
id            uuid pk
message_id    fk -> ai_assistant_messages   (assistant turn)
conversation_id, user_id
session_id    text                          (multi-turn grouping)
started_at, ended_at
total_tokens_in, total_tokens_out, total_cost
status        ok | error
release/env   text                          (attribution)
```

### `ai_assistant_spans`
```
id            uuid pk
trace_id      fk
parent_id     uuid null                     (tree)
dotted_order  text                          (sortable path key for sibling ordering)
span_kind     enum: LLM | TOOL | RETRIEVER | EMBEDDING | CHAIN | AGENT |
                    GUARDRAIL | EVALUATOR
name          text                          (e.g. "chat gpt-4o", "execute_tool crm_stock_balance")
input_json    jsonb
output_json   jsonb
status, error
start_time, end_time, latency_ms
-- LLM spans:
request_model, response_model, finish_reason, invocation_params(jsonb),
tokens_in, tokens_out, cache_read_tokens, reasoning_tokens, cost,
prompt_name, prompt_version   <-- BRIDGE to M1
-- TOOL spans:
tool_name, tool_call_id, tool_args(jsonb), tool_result(jsonb, truncated)
-- RETRIEVER spans:
query, documents(jsonb: [{id,content,score,metadata}]), top_k
```

OTel field mapping (if we go semconv): `gen_ai.request.model`, `gen_ai.usage.input_tokens`/`output_tokens`, `gen_ai.response.finish_reasons`, `gen_ai.input.messages`/`gen_ai.output.messages`, tool spans `gen_ai.tool.name`/`.call.id`/`.call.arguments`/`.call.result`. (Retrieval has NO OTel convention yet → use OpenInference names for RETRIEVER/EMBEDDING.)

## 4. Instrumentation

A span-recorder context manager wraps each pipeline stage in `ai_assistant_service.py`; captures in/out/timing/status. The agentic loop then reads: `AGENT root → RETRIEVER → (EMBEDDING) → LLM → TOOL → LLM → TOOL → … → synthesize`. Deterministic stages (RBAC, link injection, entity resolution, short-circuits) - **open question** whether they get CHAIN spans too or stay invisible.

## 5. FE (draft)

- **Trace tab per message** (in the usage/recent-queries detail, or the chat bubble admin view): waterfall/tree of spans, latency bars, token badges, per-node status.
- Click a node → **input panel left / output panel right** (n8n inspector). LLM node shows messages + prompt_name@version (link to the M1 prompt detail). Tool node shows args + result. Retriever shows query + ranked docs+scores.
- Filter/collapse by span_kind; highlight error spans.

## 6. Role split (M2.5)

- Activate dormant keys `planner`, `synthesizer`, `semantic_compressor`.
- Refactor `_run_agent_loop`: explicit planner call (decompose + tool ordering) → executor rounds → semantic_compressor on tool outputs before feeding back → synthesizer for final answer. Each = own span + own prompt version.
- Grafana precedent: they split the monolith explicitly "because delegation is easier to debug and extend."

## 7. Resolved decisions (grill 2026-07-03)

Baseline fact: **zero tracing infra exists** in the stack (no OpenTelemetry / Langfuse / Tempo / Jaeger / Sentry in deps or compose). Clean slate.

| # | Decision |
|---|---|
| Q1 storage | **In-house tables** (`ai_assistant_traces` + `ai_assistant_spans`) + in-app UI. Primary consumer = admin debugging in the CRM, not SRE. **Field names OTel GenAI semconv-shaped** (`gen_ai.*`) so a future OTLP export is a straight field-map. Real OTel/collector export = **deferred, optional** (later adapter reads spans → emits OTLP). Not built in M2. |
| Q2 retention/PII/trunc | **TTL default 30d**, swept by existing background scheduler; **error + thumbs-down traces kept 90d/until-reviewed** (feed M3 evals). **Admin-only gating** (same perm as AI-config), **no scrubbing layer** (data already in CRM under same RBAC - a span is not new exposure). **Truncate** `tool_result`/`documents`/message content at **~16KB** each + `truncated:true` flag. TTL + caps **`system_settings`-configurable** (singleton pattern). |
| Q3 sampling | **Trace 100% of turns.** No sampling - internal-staff volume, and you want the failed turn guaranteed captured. Storage bounded by Q2 TTL, not sampling. |
| Q4 which nodes span | **Decision-or-data-transform → span; mechanical → attribute.** Spanned: RETRIEVER (tool-select + scores), CHAIN (entity resolution), routing/short-circuit (branch taken + why), GUARDRAIL (RBAC denial - link `GovernanceEvent`), all LLM + TOOL. NOT spanned: link-inject / URL-strip / turn-cache → attributes on the synthesize span (noise control). |
| Q5 UI home | **Extend `usage/` recent-query detail into a full Trace view** (waterfall + click-node in/out panels) - reuses existing `message_id` linkage; today's `tools_used[name,ok]` becomes the span tree. **Dedicated route / full drawer** (too rich for a modal). **Plus** a "View trace" **deep-link in the admin chat bubble** → closes the tune loop (send → see trace → edit prompt in M1). |
| Q6 write strategy | **Buffer spans in-memory on the request-scoped trace, flush once post-turn as a single bulk insert.** Near-zero added latency, atomic. Flush is **best-effort - catch + warn, never raise** (CLAUDE.md: trace-write failure must not 500 a successful answer). Chat is in-process (worker never runs chat) → **no cross-process** in M2; trace_id→worker propagation noted as future. Mid-turn crash loses that trace - accepted. |
| Q7 sequencing | **Strictly sequential: M2 (trace) first, M2.5 (split) second, separate PRs, M2.5 gated on M2 live.** Trace = zero-behavior-change observability (ship safe win now); split = behavioral refactor (risky). Split *because* traces show the monolith is opaque; **trace = the test harness that verifies the split.** Same schema across both (M2.5 just emits finer spans - no migration). |
| Q8 cost | **Tokens (in/out/total) per span + trace = core** (free, already captured; makes the M2.5 semantic_compressor 4x win visible without $). **Cost $ = optional stretch**: admin-editable model-price config (model → in/out $ per 1M tokens) + computed $ per span/trace. Prices editable never hardcoded. Does NOT block M2. |

## 8. Non-goals (M2/M2.5)
- Evals / golden-set / LLM-judge (M3).
- Alerting on eval pass-rate (M3).

---

## 9. UAC - User Acceptance Criteria (locked 2026-07-04)

End goal: an admin, from a recent assistant turn, opens a **trace view** that shows every pipeline node (reformulator, retriever, entity-resolver, each LLM round, each tool call, synthesizer) as a nested waterfall; clicking a node reveals its exact input and output. Zero behaviour change to the answer itself.

### M2 - Backend (trace capture)

- **B1** Every assistant turn served by `respond()` writes **exactly one** `ai_assistant_traces` row + **N** `ai_assistant_spans` rows. Deterministic short-circuits (capability answer) also write a trace (root + the deterministic span).
- **B2** Trace + spans are **buffered in-memory** during the turn and flushed **once post-turn** as a bulk insert. Flush is **best-effort**: any exception is caught + logged, never raised - a telemetry failure must not 500 a successful answer (CLAUDE.md post-commit-side-effect rule).
- **B3** `ai_assistant_messages` gains a nullable `trace_id` FK (SET NULL) → the assistant message links to its trace.
- **B4** Spans captured (Q4 - decision-or-transform → span; mechanical → attribute):
 - `AGENT` root (whole turn),
 - `LLM` reformulator, `LLM` router/record-classifier, each `LLM` agent-loop round, each `LLM` record-render round,
 - `RETRIEVER` RAG tool-selection (query + selected tools + scores),
 - `CHAIN` entity resolution,
 - `TOOL` per MCP tool call (incl. the deterministic guide pre-fetch),
 - `GUARDRAIL` when a tool is denied (tool_not_available / budget_exceeded / write-suppressed).
- **B5** Each `LLM` span records: `request_model`, `tokens_in`, `tokens_out`, `finish_reason` (null if provider omits), `input_json` (messages), `output_json` (content + tool_calls), `latency_ms`, `status`, and **`prompt_name` + `prompt_version`** (M1 bridge - null version = fallback used).
- **B6** Each `TOOL` span records: `tool_name`, `tool_call_id`, `tool_args` (json), `tool_result` (truncated), `status` (ok/error), `error`.
- **B7** Each `RETRIEVER` span records: `query`, `documents` (`[{id,content,score}]`), `top_k`.
- **B8** `input_json` / `output_json` / `tool_result` / `documents` truncated at a configurable byte cap (**default 16 KB** each) with a `truncated: true` flag on the payload.
- **B9** Trace row records: `message_id`, `conversation_id`, `user_id`, `session_id` (conversation id), `started_at`, `ended_at`, `total_tokens_in`, `total_tokens_out`, `status` (`ok`|`error`), `env`.
- **B10** **100 % of turns traced** - no sampling.
- **B11** Retention config in `system_settings` (singleton): `ai_trace_ttl_days` (default 30), `ai_trace_error_ttl_days` (default 90), `ai_trace_max_payload_bytes` (default 16384). Editable via settings API (added to BOTH GET builder AND `SystemSettingUpdate` - singleton rule). A scheduled sweep deletes `ok` traces older than TTL and `error`/`flagged` traces older than error-TTL; spans cascade.
- **B12** `GET /api/v1/system/ai-assistant/usage/queries/{message_id}/trace` returns the trace + ordered span tree. Admin-only (`system.ai_assistant_settings.view`). 404 when no trace.

### M2 - Frontend (trace view)

- **F1** Recent-query detail (usage page expanded row) shows a **"View full trace"** action when a trace exists → dedicated route `/system-management/ai-assistant/usage/trace/[messageId]`.
- **F2** Trace view renders a **waterfall/tree**: one row per span, indented by nesting, with a latency bar (proportional), a token badge on LLM spans, a span-kind chip, and a status colour (ok/neutral, error/destructive).
- **F3** Clicking a span opens an **inspector**: input panel (left) + output panel (right), n8n style. LLM span shows messages + `prompt_name@version` **linking to the M1 prompt detail** (`/system-management/ai-assistant/prompts/[name]`). Tool span shows args + result. Retriever shows query + ranked docs with scores.
- **F4** Filter/collapse by span-kind; error spans visually highlighted; empty/loading/error states all render.
- **F5** Admin chat bubble (`AIAssistantBubble`) gets a **"View trace"** affordance on each assistant message → opens the same trace view (via `?ai_trace=<messageId>` deep-link pattern, mirroring existing `ai_message`).

### M2 - Tests (land in Phase 2, not deferred)

- **T1** pytest: a turn writes 1 trace + expected spans; flush failure is swallowed (answer still returned); truncation applies at cap; TTL sweep deletes only expired rows; trace endpoint returns the tree + 403 for non-admin + 404 for missing.
- **T2** vitest: TraceView + inspector components across loading / empty / error / data; waterfall renders spans; clicking a node shows in/out; prompt link resolves.
- **T3** playwright: send a turn in the bubble → open usage → expand → View trace → assert waterfall + node in/out + the `/api/v1/*/trace` network call.

### M2.5 - Role split (gated on M2 live)

- **S1** Activate dormant prompt keys `planner` + `semantic_compressor` (publish `production` labels); `synthesizer` already active.
- **S2** `_run_agent_loop` refactored into explicit nodes: **planner** (decompose + tool ordering) → executor rounds → **semantic_compressor** (raw tool JSON → token-tight sentences before feeding back) → **synthesizer** (final answer). Each is its own prompt key + its own trace span - **same schema, no migration** (M2.5 just emits finer spans).
- **S3** Answer quality is **not regressed** vs the monolith on a spot-check set; the trace shows the split nodes distinctly; semantic_compressor's token reduction is visible in span token counts.
- **S4** Tests: pytest per node (planner emits a plan, compressor shrinks a payload, synthesizer composes); playwright shows the finer span tree.

### Definition of done

Every B/F/T line above verified end-to-end against the live stack (BE :8000 + FE :3000 + worker) via Playwright before handoff (memory: verify both sides before handoff). M2 ships as its own PR; M2.5 as a second PR gated on M2 being live.

---

## 10. Completion record (2026-07-04)

Built in one pass, verified end-to-end against the live stack (BE :8000 + FE :3000 + worker + MCP :8765).

### M2 - trace/spans (backend)
- Migration `259_ai_assistant_trace` - `ai_assistant_traces` + `ai_assistant_spans` (OTel-shaped), `ai_assistant_messages.trace_id` FK, 3 `system_settings` retention/cap columns. Single alembic head.
- Models `AIAssistantTrace` / `AIAssistantSpan` (`app/models/ai_assistant.py`).
- `app/services/ai_trace.py` - `TurnTrace` in-memory buffer (`add_span`/`add_llm_span`/`add_tool_span`), one-shot best-effort `flush()` (**FK ordering fix: `db.flush()` the trace row before the spans** - batched insertmany doesn't order the parent first without an ORM relationship), `_truncate_payload` (16 KB cap → `{truncated,byte_size,preview}`), `sweep_expired_traces`.
- Instrumented `respond()` + `_reformulate_query` + `intent_is_record_class` (router) + `_run_agent_loop` (per-round LLM + per-tool + guardrail) + `_render_record_answer`: AGENT root, LLM (prompt_name+version M1 bridge), RETRIEVER, CHAIN, TOOL, GUARDRAIL spans. Flush + link to assistant message post-turn; capability short-circuit also traced.
- `GET /api/v1/system/ai-assistant/usage/queries/{message_id}/trace` (admin-only, 404 when none).
- Daily retention sweep wired into `task_scheduler.start_scheduler`.

### M2 - trace view (frontend)
- `services/aiUsageService.ts` (`getQueryTrace` + `Trace`/`TraceSpan` types), `hooks/useAIUsage` (`useQueryTrace`).
- `components/TraceView.tsx` - waterfall (indented, latency bars, token badges, kind chips, status colour) + node inspector (input/output panels, LLM shows model/tokens/finish + **`prompt_name@vN` link to the M1 prompt detail**, truncation banner) + kind filter + loading/empty(404)/error states.
- Route `usage/trace/[messageId]/page.tsx`; "View full trace" link in the usage recent-query detail; "View trace" link on each admin chat-bubble assistant message (admin-gated, new tab).

### M2.5 - role split (opt-in via `system_settings.ai_assistant_role_split_enabled`, default off)
- Activated `planner` + `semantic_compressor` prompt keys (registry).
- `_run_agent_loop`: planner node up front (own span) → executor rounds → semantic_compressor on each non-guide tool result before feeding back (own span; **skips `user_guides_read` to preserve inline links**, and small/error payloads). Verified live: product-list turn showed planner + `semantic_compressor` span compressing **2623 → 768 tokens (~3.4×)**, answer intact.
- `components/TraceSettingsCard.tsx` on the AI-assistant admin page - role-split toggle + retention/cap fields, saves via `/general`. Toggle persist verified.

### Tests (Phase 2, all green)
- pytest: `test_ai_trace.py` (11) + `test_ai_trace_endpoint.py` (4) + `test_ai_role_split.py` (12) + `test_settings_ai_trace_fields.py` (2) = 29 new; 56 passing incl. neighbours; no regressions.
- vitest: `TraceView.test.tsx` (7) - loading/empty/error/data/inspector/prompt-link/filter.
- Browser (Playwright MCP): sent bubble turns → trace written (8 spans, prompt versions bridged, tokens summed) → trace view waterfall + inspector + prompt link + truncation banner + empty(404) state + settings save all confirmed; zero console errors.

### Follow-ups (not blockers)
- Optional OTLP export adapter (Q1, deferred). Cost-$ per span (Q8 stretch).
- `sweep_expired_traces` reads the `system_settings` singleton via `.first()` - inherits the documented singleton invariant (migration 253 index) rather than re-pinning it.

---

## 11. Post-review enhancements (2026-07-04, user feedback)

Two display/UX refinements after reviewing the live trace view:

1. **Structure-preserving payload truncation** - `_truncate_payload` (`ai_trace.py`) now trims long string leaves + long lists **in place** (inline `…[+N chars/items truncated]` marker) instead of replacing the whole payload with a flat `{truncated,byte_size,preview}` string. So `input_json`/`output_json` stay valid nested objects and the inspector renders **pretty-printed indented JSON**, not an escaped one-line blob. Flat-envelope kept only as the last-resort fallback (non-JSON-able / pathological). Tests updated (`test_ai_trace.py`: structure-preserved dict + list-cap cases).

2. **Find-in-text (Cmd/Ctrl+F) - reusable widget** (`components/common/find-in-text/`): `useFindController` (match ranges + wrap-around active index) + `FindBar` (query, `N/M` count, prev/next, close; Enter/Shift+Enter/Escape) + `SearchableTextarea` (editable - **highlight overlay backdrop**: transparent textarea over a metrics-synced div that paints `<mark>` rectangles behind matches, since a textarea can't show custom highlights natively; + native selection + scroll) + `SearchableCode` (read-only - inline `<mark>` highlight, active in `bg-primary`). Wired into the **prompt editor** (`PromptDetail.tsx`, editable, n8n-style) and the **trace inspector input/output panels** (`TraceView.tsx` `JsonPanel`, read-only). Verified live: editor 1/18→2/18 with native selection; trace panel 1/4→2/4 with mark highlight; zero console errors.
