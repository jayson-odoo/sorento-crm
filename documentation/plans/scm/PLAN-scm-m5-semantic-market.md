# PLAN — SCM M5: Semantic Layer + Market Advisory

**Slug:** `scm-m5-semantic-market` · **Milestone:** M5 · **UAC:** `scm-m5-semantic-market-acceptance-criteria.md`
**Umbrella:** `PLAN-scm-reorder-copilot.md` · **Depends:** M0–M4 · **Status:** DRAFT (grilled, pre-code)
**Type:** BE (bounded LLM flow + web-search research job) + advisory/explanation/viz UI
**⚠ Read the `claude-api` skill before building the Anthropic web-search integration.**

## Goal
The "wow": plain-language explanation + scoped Q&A per recommendation, and market/economic advisory
from backend web search — all advisory-only, LLM never touches a number.

## 1. Schema
- **`reorder_recommendation`** (from M3/M4) + `explanation`, `market_advisory` (cached prose).
- **`scm.market_research_topic`**: label, category_ref, currency, search_prompt, cadence, is_active.
- **`scm.market_signal`**: topic_id, category_ref, currency, value, trend, summary, source_url, captured_at.
- **`scm.market_research_run`**: started/finished/status/counts/error (observability, like `scm_analytics_run`).

## 2. SCM explainer flow (bounded — NOT the agent flow)
`app/services/scm/explainer_service.py`:
- `explain_recommendation(rec)` — structured frozen numbers → `llm_provider.chat` with prompt key `scm_recommendation_explainer` (registry) → one sentence; cache to `recommendation.explanation`. Lazy on first view.
- `answer_question(rec, question)` — bounded context = that rec's numbers only; prompt instructs "never compute; if the number isn't given, say you can't." No tools, no agent loop.
- `market_advisory(rec)` — pull matching `market_signal` (category+currency) → condense to one advisory sentence; cache to `recommendation.market_advisory`.
- All via `llm_provider` (OpenAI/Anthropic), traced through `ai_trace`, governed by prompt registry (immutable versions + movable labels). Configurable as a new flow type (prompt/model/on-off). No numeric write anywhere (boundary test).

## 3. Market research job (Anthropic web search)
`app/services/scm/market_research_service.py`:
- `run_research(scope)` — iterate active `market_research_topic`; for each, call `llm_provider` (Anthropic) with the **web-search server tool** + the topic's `search_prompt`; **schema-forced extraction** → `market_signal` {value, trend, summary, source_url}. Write `market_research_run` log.
- Triggers: `scheduled_task` `scm_market_research` (cadence per topic) + manual `POST /scm/market-research/run`. **Cache signals; never search per recommendation.**
- Cost-aware: batch topics; log per-run search count/duration.

## 4. Endpoints
- `GET /scm/recommendations/{id}/explanation` (lazy generate+cache), `POST /scm/recommendations/{id}/ask` (bounded Q&A).
- `GET /scm/market-signals` (viz), `POST /scm/market-research/run`, topic CRUD.
- All under `require_module_enabled_with_api_key("scm")`.

## 5. FE (Phase 1 prototype → Phase 2 wire, test-first)
- **Recommendation detail:** explanation sentence (lazy, skeleton while loading), **Ask** input (bounded answers), market advisory line (when a matching signal exists).
- **Market signals panel** (dashboard): read-only trend cards/table per topic; "Run research" button with running→complete feedback (reuse the run-feedback pattern from M3).
- **Topic config CRUD** (`market_research_topic`): modal with category (`SearchableSelect`) + currency + free-form `search_prompt` textarea + cadence.
- Reuse DataGrid/modal-CRUD/SearchableSelect/stat-tiles; no UUIDs; mobile-scrollable.

## 6. Tests (test-first / TDD; LLM + web-search mocked)
- **pytest:** explanation echoes numbers unchanged (AC-M5.1); Q&A refuses to compute (AC-M5.2); flow uses no tools (AC-M5.3); research job writes structured signal + run log with mocked web-search (AC-M5.4); signal↔rec matching (AC-M5.6); market-acts-only-via-override (AC-M5.7); **LLM-boundary** no numeric write across all paths (AC-M5.8); auth.
- **vitest:** explanation lazy/cache, Q&A panel, advisory display, market viz, topic CRUD states.
- **playwright:** AC-M5.10.

## 7. Risks
- **Web-search infra = newest/riskiest.** Provision + validate the Anthropic web-search tool early (read `claude-api`). If it stalls → ship M0–M4 + explanation, defer market research to fast-follow; deterministic deal-closer doesn't depend on it.
- **No-overfit** — explainer/advisory examples pin format, not numbers; Q&A tested with paraphrases.
- **Source quality** — web-search results vary; store `source_url` for traceability; mark low-confidence signals; advisory is suggestive, never authoritative.
- **Cost** — cache signals, cadence-limited + manual; never per-rec search; log search counts.
