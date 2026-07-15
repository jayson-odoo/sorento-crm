# UAC — SCM M5: Semantic Layer + Market Advisory

> Given/When/Then contract for milestone M5. Parent umbrella: `scm-reorder-copilot-acceptance-criteria.md`.
> Depends on M0–M4. Governs: `PRINCIPLES.md`. **The "wow" layer — all advisory, LLM never touches a number.**

**Slug:** `scm-m5-semantic-market` · **Domain:** scm · **Milestone:** M5 · **Status:** DRAFT (grilled, pre-code)

## Scope
Plain-language explanation per recommendation, scoped Q&A over displayed numbers, and market/economic
advisory sourced by backend web search — all **advisory-only**. The LLM is given computed numbers and
emits prose; it has no path to compute or alter a number. Read the `claude-api` skill before building
the Anthropic web-search integration.

## Locked decisions (from M5 grill)

| # | Decision |
|---|---|
| M5-D1 | **Separate configurable "SCM explainer" flow** — NOT the agent/MCP flow. Bounded: structured recommendation in → prose out. No semantic_parser, no MCP tools, no agent loop (can't fetch or compute). Reuses `llm_provider`, `ai_prompt_registry`, `ai_trace`, governance/config. Configurable prompt/model/on-off as a new flow type. |
| M5-D2 | **Explanation** — prompt key `scm_recommendation_explainer`; input = the recommendation's **frozen numbers**; output = one plain sentence. Generated **lazy on first view, cached** to `recommendation.explanation`. Examples pin **format only, never numbers** (no-overfit). |
| M5-D3 | **Q&A** — scoped per-recommendation, bounded to that rec's frozen numbers. **LLM never recalculates**; if a question needs a number not in context it says "I can't compute that." Reuses the explainer flow, not the agent. |
| M5-D4 | **Market = advisory-to-human, NEVER auto-mutates a number.** LLM analysis of market research produces an advisory attached to the recommendation for the human. It flows into a qty/ROP/SS **only** through a human **Adjust/override** (captured, deterministic, auditable). Golden-set + reproducibility preserved. |
| M5-D5 | **Web search = Anthropic web-search server tool** via `llm_provider` (already does Anthropic + tools). No separate search-API key. Consult `claude-api` skill for tool specifics + cost at build. |
| M5-D6 | **`market_research_topic` config (user-editable):** label, `category_ref` (optional — for matching to recs), `currency` (optional), **`search_prompt`/keywords (free-form — drives the actual web search)**, cadence, is_active. Structured mapping AND free-form search input. |
| M5-D7 | **Research job** (scheduled_task + manual "Run research" button): iterate active topics → Anthropic web search → **schema-forced extraction** → `market_signal` {value, trend, summary, source_url, captured_at}. Run log (observability). **Cache signals — never web-search per recommendation.** |
| M5-D8 | **Signal → recommendation matching** by **product category + supplier currency**. No match → no advisory (fine). |
| M5-D9 | **Advisory** generated **lazily per-recommendation from stored signals** via the explainer flow, cached on the rec. Advisory-only. |
| M5-D10 | **`market_signal` viz** = read-only dashboard panel (trend cards/table per topic) — the "visualize in our system" requirement. |

## Acceptance criteria

### Explanation & Q&A
- **AC-M5.1** GIVEN a recommendation WHEN first viewed THEN an explanation sentence is generated from its frozen numbers and cached; a test asserts the displayed qty/ROP/SS in the prose equal the engine's (no LLM drift).
- **AC-M5.2** GIVEN a follow-up question about a recommendation WHEN asked THEN the answer is bounded to that rec's numbers; a question requiring an uncomputed number returns "I can't compute that", **never a fabricated/recalculated figure**.
- **AC-M5.3** GIVEN the explainer flow WHEN traced THEN it uses no MCP tool / agent loop and has no path to write a numeric field.

### Market research
- **AC-M5.4** GIVEN an active `market_research_topic` with a free-form `search_prompt` WHEN the job runs THEN Anthropic web search executes that prompt and a structured `market_signal` (value/trend/summary/source_url/captured_at) is written; a run log records status/counts/duration.
- **AC-M5.5** GIVEN the "Run research" button WHEN clicked THEN the job runs on demand and new signals appear in the viz panel.
- **AC-M5.6** GIVEN a recommendation whose SKU category + supplier currency match a stored signal WHEN viewed THEN an advisory sentence is shown, generated from stored signals (no per-rec web search); no-match → no advisory.
- **AC-M5.7** GIVEN a market signal (e.g. "FX +8%") WHEN the human acts on it THEN the qty changes **only** via an Adjust/override (reason captured) — the computed recommendation number is unchanged by the signal itself.

### Boundary / conventions
- **AC-M5.8 (LLM-boundary test)** GIVEN any M5 code path WHEN traced THEN no LLM output (explanation, Q&A, advisory, extraction) writes a quantity/ROP/SS/budget/rank field.
- **AC-M5.9** GIVEN the no-orphan matrix THEN `market_research_topic` has a config CRUD list and `market_signal` a read-only viz; SearchableSelect, extractApiError, no UUIDs.
- **AC-M5.10 (verify)** Playwright: open a recommendation → explanation renders → ask a follow-up (bounded answer) → run market research → advisory appears on a matching rec → confirm acting on it goes through Adjust; 375px + 1280px, console clean.

## Tests (test-first — TDD; LLM mocked for determinism)
- **pytest:** explanation echoes numbers unchanged (mock LLM); Q&A refuses to compute; market job writes structured signal + run log (mock web-search tool); signal↔rec matching by category+currency; **LLM-boundary** (no numeric write) across all M5 paths; auth.
- **vitest:** explanation lazy-load + cache, Q&A panel, advisory display, market viz panel, topic config CRUD states.
- **playwright:** AC-M5.10.

## Deferred
Full agentic SCM assistant (routing SCM questions through the MCP tool loop) — a later flow;
auto-refresh cadence tuning; multi-language advisory.

## Risk
**Web-search infra is the newest/riskiest piece.** If Anthropic web-search provisioning stalls, ship
M0–M4 + explanation (M5 partial) and defer market research to fast-follow — the deterministic
deal-closer (M0–M4) does not depend on it.
