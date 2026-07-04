# PLAN — AI Assistant Per-Node Trace + Role Split (M2 / M2.5)

**Status:** GRILLED (2026-07-03, §7 resolved below) — ready to build after M1 ships.
**Depends on:** M1 prompt registry (`PLAN-ai-assistant-prompt-registry.md`) — specifically the `prompt_name`+`prompt_version` stamp that lets a span link to the exact prompt variant that produced it.
**Owner:** jayson
**Date drafted:** 2026-07-03

---

## 1. Problem

Diagnosis today = coarse. `AIAssistantUsageLog` (tokens, latency, was_answered) + `Message.metadata_json` (links, sources, `tools_used[name,ok]`). You cannot see, per turn:
- what the reformulator received vs emitted,
- which tools were called with which args and what they returned,
- what each LLM round reasoned/decided,
- where a bad answer diverged.

No n8n-style "click a node, see its input and output." And the agent loop is a **monolith** — plan + reason + tool-call + synthesize fused in one LLM call site (:1322), so even with a trace it's one opaque box.

## 2. Goal

Two coupled deliverables:
- **M2 — Trace/spans:** one **trace** per turn, nested **spans** per node, each with typed input/output + model + tokens + latency + `prompt_version`. FE waterfall/tree; click a node → in/out panels. Schema aligned to **OpenTelemetry GenAI semantic conventions** (`gen_ai.*`) so we can export to Langfuse/Phoenix/any OTel backend later for free.
- **M2.5 — Role split:** break the agent monolith into explicit nodes — `planner` → executor/`agent_system` → `synthesizer`, plus `semantic_compressor` (raw tool JSON → token-tight sentences, Grafana 4x pattern). Each split node = its own prompt key (already seeded dormant in M1) + its own trace span. You split *because* the trace makes the monolith visible.

## 3. Data model (draft — from research §3)

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

A span-recorder context manager wraps each pipeline stage in `ai_assistant_service.py`; captures in/out/timing/status. The agentic loop then reads: `AGENT root → RETRIEVER → (EMBEDDING) → LLM → TOOL → LLM → TOOL → … → synthesize`. Deterministic stages (RBAC, link injection, entity resolution, short-circuits) — **open question** whether they get CHAIN spans too or stay invisible.

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
| Q2 retention/PII/trunc | **TTL default 30d**, swept by existing background scheduler; **error + thumbs-down traces kept 90d/until-reviewed** (feed M3 evals). **Admin-only gating** (same perm as AI-config), **no scrubbing layer** (data already in CRM under same RBAC — a span is not new exposure). **Truncate** `tool_result`/`documents`/message content at **~16KB** each + `truncated:true` flag. TTL + caps **`system_settings`-configurable** (singleton pattern). |
| Q3 sampling | **Trace 100% of turns.** No sampling — internal-staff volume, and you want the failed turn guaranteed captured. Storage bounded by Q2 TTL, not sampling. |
| Q4 which nodes span | **Decision-or-data-transform → span; mechanical → attribute.** Spanned: RETRIEVER (tool-select + scores), CHAIN (entity resolution), routing/short-circuit (branch taken + why), GUARDRAIL (RBAC denial — link `GovernanceEvent`), all LLM + TOOL. NOT spanned: link-inject / URL-strip / turn-cache → attributes on the synthesize span (noise control). |
| Q5 UI home | **Extend `usage/` recent-query detail into a full Trace view** (waterfall + click-node in/out panels) — reuses existing `message_id` linkage; today's `tools_used[name,ok]` becomes the span tree. **Dedicated route / full drawer** (too rich for a modal). **Plus** a "View trace" **deep-link in the admin chat bubble** → closes the tune loop (send → see trace → edit prompt in M1). |
| Q6 write strategy | **Buffer spans in-memory on the request-scoped trace, flush once post-turn as a single bulk insert.** Near-zero added latency, atomic. Flush is **best-effort — catch + warn, never raise** (CLAUDE.md: trace-write failure must not 500 a successful answer). Chat is in-process (worker never runs chat) → **no cross-process** in M2; trace_id→worker propagation noted as future. Mid-turn crash loses that trace — accepted. |
| Q7 sequencing | **Strictly sequential: M2 (trace) first, M2.5 (split) second, separate PRs, M2.5 gated on M2 live.** Trace = zero-behavior-change observability (ship safe win now); split = behavioral refactor (risky). Split *because* traces show the monolith is opaque; **trace = the test harness that verifies the split.** Same schema across both (M2.5 just emits finer spans — no migration). |
| Q8 cost | **Tokens (in/out/total) per span + trace = core** (free, already captured; makes the M2.5 semantic_compressor 4x win visible without $). **Cost $ = optional stretch**: admin-editable model-price config (model → in/out $ per 1M tokens) + computed $ per span/trace. Prices editable never hardcoded. Does NOT block M2. |

## 8. Non-goals (M2/M2.5)
- Evals / golden-set / LLM-judge (M3).
- Alerting on eval pass-rate (M3).
