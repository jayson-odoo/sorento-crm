# PLAN - Industrial-grade AI assistant architecture (LLM-as-NLP, deterministic-first)

**Status:** DRAFT for internal grilling, 2026-06-29. Synthesized from two architecture audits (assistant hot-path + MCP/n8n semantic-parser pattern). Not yet user-approved.

## Why

Two user requirements:
1. **Novice-first coverage** - "what can the system do?", "where is X", "what am I looking at" must be answerable to someone who knows nothing.
2. **Fast** - stop using the LLM to do everything. LLM = NLP only (understand language, extract structured info). Deterministic tools/logic/registries do the work. Same discipline applied back to n8n.

## Current state (measured)

- **4 - 7 sequential LLM calls per message** (`ai_assistant_service.py`). Typical query ≈ 1.6s/3 calls; record path ≈ 2.0s/4+ calls; worst 3.5 - 5.5s.
- LLM used for work a deterministic layer could do: **query reformulation** (`:435`), **intent classification** (`:1395`), **free tool choice** despite RAG scores (`:1092`).
- **No caching** (no Anthropic `cache_control`, no tool-result/guide cache, query embedding recomputed). **FE doesn't stream.**
- Capability catalog **exists** (`crm_system_tool_capabilities_summary`) but "what can it do?" is still LLM-guessed.
- MCP pattern is good but **4 capability registries drift** and **shaping is hardcoded in server.py**.

## Target architecture - 6 layers

```
User text
  │
  ▼
[1] Deterministic Intent Router  (NO LLM; keyword + cosine over existing tool-intent embeddings)
  │   ├─ "what can you do / help"      → [Capability answer]  (deterministic, from registry)
  │   ├─ "how do I …"                  → [Guide answer]       (cached Outline read, templated)
  │   ├─ high-confidence data query    → [2] param extract → [3] execute → [4] template
  │   ├─ record-context ("this/it")    → record render (facts already in context)
  │   └─ ambiguous / low-confidence    → [5] LLM agent fallback (today's path)
  ▼
[2] LLM = NLP extractor ONLY  (ONE forced-tool call: text → {entity, filters, date_range, customer, …} JSON schema)
  ▼
[3] Deterministic execution  (MCP tool / list_query / SQL - already deterministic)
  ▼
[4] Templated formatting  (render rows/table/summary WITHOUT an LLM for the common cases; LLM narrates only when asked)
  ▼
[5] LLM agent fallback  (only for genuinely open-ended/multi-step - keep current loop but capped + cached)
  ▼
[6] Cross-cutting: caching + streaming + eval + guardrails
```

### Layer 1 - Deterministic intent router (biggest latency win)
- Replace the LLM **reformulation** + **intent-classification** calls with a fast router: keyword triggers (already exist: `_GUIDE_QUESTION_TRIGGERS`) + cosine similarity of the query embedding against the **already-built** tool-intent embeddings. Threshold gate: top score > τ → route deterministically; else → LLM fallback.
- Pronoun/abbrev expansion ("this", "it", customer aliases) → deterministic resolver, not an LLM round-trip.
- Saves 1 - 2 LLM calls on the hot path.

### Layer 2 - LLM as NLP extractor only
- When routed to a data query, the LLM gets ONE job: extract params into a JSON schema (forced tool / constrained output). No free agent loop for the common case → 1 LLM call, not 3 - 6.

### Layer 3 - Deterministic execution
- Already solid (MCP tools, list_query_registry, two-call dynamic params). Keep.

### Layer 4 - Templated formatting
- For list/aggregate answers, render deterministically (table + counts + links) instead of paying an LLM round-trip to phrase rows. LLM only narrates on request ("summarize", "explain").

### Layer 5 - LLM agent fallback
- Keep today's agent loop for open-ended/multi-step, but: cap iterations, force-gate tool choice on RAG>0.85, and feed it cached context.

### Layer 6 - Cross-cutting
- **Anthropic prompt caching** (`cache_control: ephemeral`) on the stable prefix: system prompt + USER GUIDE PROTOCOL + tool list. Big token+latency save across turns. (Verify model tier supports it - consult claude-api skill; don't run this on a Haiku fallback if unsupported.)
- **Per-conversation caches:** tool-result memo (args hash → output), guide-content cache (don't re-read same guide each turn), reuse query embedding.
- **FE streaming** - stream tokens so perceived latency drops even when total compute is similar.

## The structural fix - single capability registry (kills drift + hardcoding + powers "what can it do")

Merge `ToolSpec` (MCP signature) + `ToolIntent` (semantic) + the `server.py` shaping consts into ONE `ToolDefinition`:

```python
@dataclass(frozen=True)
class ToolDefinition:
    # signature
    name; description; path; method; query_params; domain; escalation_team; related_tools
    # semantic (was TOOL_INTENTS)
    intent; typical_user_questions; aliases; category
    # shaping (was hardcoded in server.py)
    required_narrowing_filters; default_query_params; drop_row_keys; key_remap
    # ownership
    default_agent_codes
```

One source generates: `mcp_tools` sync, RAG embedding chunks, MCP server shaping, default agent assignment, AND the deterministic **"what can the system do?"** catalog. No more CATALOG↔TOOL_INTENTS↔embeddings drift; no more server.py code-change-per-tool.

## Novice-first deliverables
- **Capability catalog answer** served deterministically from the registry (grouped: module → what you can do → example questions). The per-module `data-analysis.md` example questions seed this.
- **`_shared/getting-started-for-new-users.md`** - zero-knowledge orientation.
- Re-frame each module `data-analysis.md` to open with "what is this / what can I ask."

## Apply back to n8n
- Same shape: a **semantic-parse node** (LLM → structured JSON) feeding **deterministic branches**; n8n should call the shared capability registry / MCP rather than re-encoding column maps inside workflows.
- Replace string trigger checks with a **TriggerSpec registry** carrying `multi_match` and routing metadata.

## Eval + guardrails
- **Golden-question eval set** = the example NL questions from every module `data-analysis.md` → measure router accuracy + answer correctness + latency on each change.
- Guardrails: never leak viewer-hidden fields (`cost_price`/`invoice_price`), respect RBAC/contact access levels in tool results.

## ⚠️ Internal grill verdicts (2026-06-29) - proposal revised

Adversarial review corrected several claims. Revisions:

- **Prompt caching - my original framing was WRONG.** The system prompt is built dynamically per turn (record facts `:949-965`, guide content `:973-1006`, page snapshot `:925-947`), so caching a "stable prefix" gets near-zero hits as written. **Revision:** to use Anthropic caching, RESTRUCTURE message assembly so the stable blocks (base system prompt + tool list + USER GUIDE PROTOCOL) come first with a `cache_control` breakpoint, and ALL per-turn dynamic content (record facts, guide text, snapshot) is appended AFTER the breakpoint. Only then is caching viable. If not restructured, drop this item.
- **Deterministic router - partially refuted but reconcilable.** Grill said "no cosine code exists"; it missed the existing RAG tool-search (`/api/v1/external/rag/tool-search`, embeddings via `mcp_tool_capability_service` typical_user_questions). So cosine infra DOES exist and is reusable. What's genuinely missing: a tuned threshold τ and a labeled eval set. **Revision:** router reuses RAG tool-search; τ tuned against the eval harness (below) before it gates anything; router NEVER silently answers - low confidence → today's LLM path (graceful fallback, no wrong-answer risk).
- **Forced single tool call - too aggressive (RISKY confirmed).** access_levels two-call + name→UUID resolution legitimately need ≥2 round-trips. **Revision:** short-circuit to single forced-extraction ONLY when all required params are resolvable up front; otherwise fall back to the (capped) agent loop. Never force when narrowing filters / dynamic params are required.
- **`default_agent_codes` vs admin-owned `agent_id`.** Sync must NEVER overwrite admin assignment. **Revision:** `default_agent_codes` seeds agent linkage ONLY on first insert (agent_id NULL); admin overrides are permanent. Registry refactor stays INCREMENTAL (shim TOOL_INTENTS + server.py consts into ToolDefinition behind the existing interfaces; no big-bang).
- **Eval set - sound but aspirational.** Not all modules have data-analysis questions; no harness yet. **Revision:** build the harness first, seed from existing module questions, expand coverage; don't block other work on it.

**Net:** the deterministic-first DIRECTION is sound and the pain points are real (4 - 7 LLM calls, no caching, no streaming). But the safe, proven-first slice is: (1) FE streaming, (2) tool-result + guide-content caching (both already per-request dynamic - cache them), (3) drop the redundant intent-classification LLM call using existing keyword triggers, (4) build the eval harness. These give ~30 - 40% latency cut with ZERO wrong-answer risk. Router/caching-restructure/registry-unification come after, gated on the eval harness.

## Rollout (incremental, low-risk first)
1. Prompt caching + guide/tool-result cache + FE streaming (pure speed, no behavior change).
2. Deterministic router for guide + capability + record-context intents (the safest, highest-frequency).
3. Forced-tool param extraction for data queries; template formatting.
4. Unify the registry (`ToolDefinition`); migrate server.py consts + TOOL_INTENTS into it.
5. Build the eval harness from the guide questions; then expand router coverage.
6. Port the pattern to n8n.

## Open questions for the user-grill
- Acceptable latency target (p50/p95)? Current p50 ≈ 1.6s.
- Is a deterministic-template answer (no LLM narration) acceptable for list/aggregate results, or must every answer be LLM-phrased?
- Model tier for the assistant (prompt-caching + quality vs cost)?
- Appetite for the registry refactor now vs. incremental shims?
