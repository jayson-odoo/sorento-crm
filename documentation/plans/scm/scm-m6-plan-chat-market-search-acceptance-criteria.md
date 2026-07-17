# SCM M6 — Plan-chat + market-search-in-planning — Acceptance Criteria

Status: DRAFT (2026-07-17). Branch `feat/scm-reorder-copilot`.
Classification: **MODULE** (scm), `public`/`scm.*` schema, normal FKs. Extends M5 semantic layer.

Two capabilities, both LLM-boundary-safe (LLM reads frozen numbers / web text, emits prose or
lifts existing figures; never writes a numeric recommendation field, no agent tool loop on chat):

- **A — Grounded plan-chat:** a run-level multi-turn conversation on the Reorder Planning page,
  grounded in the WHOLE run (aggregates + every recommendation, compact + matched market signals).
- **B — Market search from planning (soft):** an ad-hoc "search the market" entry-point on the
  planning page → Anthropic web search → cached `market_signal` → surfaces as advisory on matching
  recs (existing infra) AND is visible to the plan-chat. NO automatic quantity/rank change.

Decided (user, 2026-07-17): plan-chat = grounded-over-frozen-facts (NOT agentic live-tools);
market search impact = advisory + chat (soft), NOT engine uplift.

## Bug fixes (pre-req — live web search currently broken)

- **AC-M6.0a** — `market_research_service._web_search_topic` calls `_anthropic_api_key(db)` (was
  called with no arg → `TypeError`, swallowed per-topic → every live search silently yielded 0).
- **AC-M6.0b** — `_ANTHROPIC_MODEL` is a model verified to support the `web_search_20250305` server
  tool (`claude-haiku-4-5`, confirmed live 2026-07-17). Old pin `claude-3-5-sonnet-latest` unverified.

## A — Grounded plan-chat

- **AC-M6.1** — `POST /api/v1/scm/reorder-runs/{run_id}/chat` `{question, history?}` → `{answer}`,
  gated `scm.dashboard.view`. 404 on unknown run, 422 on empty question, 403 for a bare user.
- **AC-M6.2** — the model's context carries the run aggregates AND a compact snapshot of EVERY rec
  in the run (sku, type, order_qty, cash_impact, days_of_cover, net_position, supplier, rank,
  funding_status, disposition_action, reason). Large runs cap to top-N by cash + all urgent, and the
  context states the truncation (`shown`/`total`).
- **AC-M6.3** — multi-turn: prior `history` turns are forwarded so follow-ups resolve ("and the
  next one?"). History is client-held (stateless server, mirrors per-rec Ask).
- **AC-M6.4** — LLM boundary: a plan-chat turn touches NO numeric column on any rec / run; only
  prose is returned, never persisted. No `tools` kwarg passed to the provider.
- **AC-M6.5** — no provider configured → a single graceful sentence (not a crash, not a fabricated
  figure).
- **AC-M6.6** — matched market signals for the run's categories are included in the chat context so
  "given <trend>, what should I do?" is answerable.
- **AC-M6.7 (FE)** — a "Discuss this plan" control by the AI Overview opens a chat panel with a
  transcript + input; answers stream into the transcript; mobile-scrollable.

## B — Market search from planning (soft)

- **AC-M6.8** — `POST /api/v1/scm/market/search` `{query, category_ref?, currency?}` → runs the
  web search, extracts 0+ signals, caches them (`market_signal`, under an ad-hoc topic labelled from
  the query), returns `{signals[], run}`. Gated `scm.dashboard.view` (or market write perm).
- **AC-M6.9** — no Anthropic key → `run.status='failed'` with `NO_KEY_ERROR`, 0 signals, no crash
  (same honest degrade as `run_research`).
- **AC-M6.10** — a signal cached against a category immediately drives the existing per-rec advisory
  on matching recs (id-OR-code + currency match) — no engine re-run needed.
- **AC-M6.11 (FE)** — a "Search the market" box on the planning page: enter a query → findings list
  renders; the resulting signal(s) then appear as advisory on matching recs and in the plan-chat.
- **AC-M6.12** — LLM boundary: search writes ONLY `market_signal` (+ its run log), never a rec field.

## A2 — plan-chat correctness + UX parity (added 2026-07-17 after review)

- **AC-M6.13 (own prompt)** — plan-chat uses its OWN system prompt, NOT the
  single-rec explainer's (which forced the exact per-rec REFUSAL string on any
  run-level question). It authorises count/sum/rank/filter/compare over the run JSON.
- **AC-M6.14 (budget = engine, not LLM)** — a budget what-if ("what defers at RM
  20k") must NOT be computed by the LLM in prose. The service parses the amount, runs
  the deterministic `cash_ranking.allocate_funding` (greedy-by-rank, the same
  allocator the Cash-budget slider uses), and injects the result as an authoritative
  `budget_scenario` the LLM only narrates. Verified: RM 20k → 1 funded (C-FH24), 4
  deferred, 76 needs-cost, RM 1,652 funded cash — matches the allocator exactly.
- **AC-M6.15 (UX parity with the global assistant)** — the plan-chat mirrors the
  AI-assistant bubble: the user's message shows immediately, a "Thinking…" indicator
  (bot pulse + bouncing dots) runs while the answer generates, then the answer renders
  as markdown (lists/bold/tables). Optimistic message survives an error turn.

## Test report keys back to these ids (PASS/FAIL/DEFERRED).
