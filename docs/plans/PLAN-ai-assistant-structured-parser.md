# PLAN — AI Assistant Structured Parser (M0: architecture revamp)

**Status:** PHASE 3 DONE (2026-07-04). Parser + router + provider forcing + migration 261 shipped; live-verified against real OpenAI on the full §12 table. Code review (3 finder angles) → 5 fixes applied (below). Tests green. Ready for commit + PR. Uncommitted.

### Phase 3 code-review fixes (2026-07-04)
1. **Capability confidence floor** — the short-circuit trusted `intent=="capability"` at any confidence; a low-confidence misclassification hijacked real questions. Now gated `>= _LOW_CONFIDENCE_FLOOR`; falls through to the agent loop otherwise. Pinned by 2 respond-level tests.
2. **`definition` no longer `skip_rag`** — only `smalltalk` skips RAG. A term question mislabelled from a real lookup ("what is DO-123?") must still reach MCP read tools + `user_guides_read`.
3. **Parser-error trace span timing** — used a fresh `perf_counter()` (reported ~0ms); now reuses the last attempt's `started` so the M2 waterfall shows real degrade latency.
4. **Anthropic forced-tool truncation** — a max_tokens/refusal response with no `tool_use` block silently validated to a confident `intent=unknown`; now raises so `_parse_turn` retries. Plus an empty-content guard in `_parse_turn` covering both providers.
5. **Capability token undercount** — the parser LLM now runs before the capability answer; `_serve_capability_answer` billed 0 tokens. Now stashes + logs the parser call's token usage.

**Accepted (documented, not fixed):** (a) capability/how_to no longer work with NO api key — reintroducing a keyword pre-gate contradicts the anti-overfit direction; a keyless assistant is non-functional anyway. (b) a model lacking OpenAI strict `json_schema` support degrades every turn to the agent loop (safe fallback, WARN-logged) — **the configured model must support structured outputs** (default `gpt-4o-mini` does; live-verified). (c) parser `entities.*` are extracted but not yet wired into `resolve_references` — future enhancement (they feed the trace + M3a today).
**Slots into roadmap:** M0, lands BEFORE M3. M1 (prompt registry) + M2/M2.5 (trace + role split) already shipped. M3a guardrails will READ this parser's signals instead of adding new nodes.
**Owner:** jayson
**Date drafted:** 2026-07-04

---

## 1. Problem

The front of the assistant pipeline throws away its own language understanding. `respond()` is an ad-hoc chain of mixed node types:

| Step | Type | Output | Problem |
|---|---|---|---|
| `_is_capability_question` | keyword gate (18-phrase allowlist) | bool | overfit; violates the `no-overfit-LLM-NLP` rule |
| `_reformulate_query` | LLM | **prose** | downstream can't branch on it; understanding discarded |
| `resolve_references` | deterministic | structured | fine |
| RAG tool select | embedding | tools | fine |
| `intent_is_record_class` | LLM | **"YES"/"NO"** | separate round-trip, 1 bit of signal |
| `_is_guide_question` | keyword gate (~24-phrase allowlist) | bool | overfit; violates the rule |
| agent loop | LLM + function-call | structured | already parameterized ✓ |
| synthesizer | LLM | prose | correct — final node ✓ |

Two keyword allowlists (each a maintenance liability and a direct violation of our own anti-overfit principle) plus two separate LLM calls that emit prose / a single bit. The pipeline understands the user, then routes on string-matching and a coin-flip.

## 2. Goal

Collapse the front half into **ONE structured Semantic Parser node** whose only job is *understand language → emit parameters*. A deterministic router switches on those parameters. Principle (the user's): the in-between LLMs output **parameters + signals**, not words; only the final synthesizer speaks prose. Like Claude — understand language first, then drive deterministic tools off that understanding.

Non-goals for M0: the agent loop (already function-calling), the synthesizer (must stay prose), evals/judge (M3b), the write-confirm UI (M3a — M0 only *emits* the `is_write_intent` signal).

## 3. Target architecture

```
user turn ──▶ [Semantic Parser]  (1 schema-forced LLM call)
                    │  emits ParseResult (JSON, schema-validated)
                    ▼
              [Deterministic Router]  (pure Python switch on intent + signals)
                    │
      ┌─────────────┼───────────────┬──────────────┬───────────────┐
      ▼             ▼               ▼              ▼               ▼
 capability   record_question   how_to        catalog_lookup   form_submit
 (no LLM)     _render_record    guide read    agent loop       agent loop
                                 + agent       (RAG tools)      (form choreography)
                    │
                    ▼
              [Synthesizer]  (final, prose — unchanged)
```

`resolve_references` (deterministic entity resolver) and RAG tool-select stay where they are — the parser's `standalone_query` still feeds RAG embedding, and its extracted `entities` can seed / cross-check the resolver.

## 4. The ParseResult contract

Schema-forced output (§6). Draft shape — grill in §10:

```jsonc
{
  "standalone_query": "string",        // self-contained NL query, for RAG embedding ONLY (KEPT — user grill Q2)
  "intent": "capability | smalltalk | how_to | definition | record_question | record_action | data_query | form_submit | unknown",
  "language": "en | ms | zh | ...",    // detected reply language (user grill Q1)
  "confidence": 0.0,                     // parser self-confidence 0–1; low → router biases to agent loop / clarify (user grill Q1)
  "form_target": "complaint | stock_inquiry | purchase_request | sponsorship_form | null",  // only for form_submit
  "entities": {
    "record_ref": "string|null",        // code/id the user named, verbatim
    "domain": "stock | orders | products | promotions | customers | sla | shipments | null",  // data_query bucket (user grill: one data_query + domain param)
    "customer": "string|null",
    "product": "string|null",
    "date_range": { "from": "YYYY-MM-DD|null", "to": "YYYY-MM-DD|null" },  // relatives pre-resolved to absolute
    "time_scope": "point | range | recent | all | null"  // coarse temporal shape of the ask (user grill Q1)
  },
  "signals": {
    "targets_open_record": "bool",      // replaces intent_is_record_class YES/NO
    "is_write_intent": "bool",          // M3a write-confirm seed
    "needs_clarification": "bool",      // M3a clarifier seed
    "clarify_question": "string|null",
    "clarify_options": ["string", ...]  // enumerable → FE chips; empty → free-form follow-up
  }
}
```

- `intent` subsumes both keyword gates (`capability`, `how_to`) AND the record/agent split (`record_question` vs `catalog_lookup`/`form_submit`).
- `standalone_query` is the ONLY prose the parser emits, and it is used only as an embedding seed — never shown to the user.
- Extensible by design: need more downstream branching → add a field, no new node.

## 5. Node-collapse mapping (what dies, what moves)

| Old | New |
|---|---|
| `_is_capability_question` (keyword) | `intent == "capability"` |
| `_is_guide_question` (keyword) | `intent == "how_to"` |
| `_reformulate_query` (prose LLM) | parser `standalone_query` field |
| `intent_is_record_class` (YES/NO LLM) | parser `signals.targets_open_record` |
| relative-date expansion (in reformulator prompt) | parser `entities.date_range` (absolute) |
| form-intent detection (in agent_system prompt) | parser `intent == "form_submit"` + `form_target` |

Two LLM round-trips (reformulator + router) → **one**. Two keyword allowlists → **zero**. All routing signals become trace-visible params.

## 6. Enforcement — schema-forced output (provider work)

Decision: provider structured-output + validate + one retry (a real contract, not prompt-and-pray).

- **OpenAI** — `response_format = {"type":"json_schema","json_schema":{...,"strict":true}}`. Provider already forwards `response_format` (llm_provider.py:205), so this mostly works today; add a strict-schema helper + parse into `ParseResult`.
- **Anthropic** — current provider only handles `response_format.type == "json_object"` (llm_provider.py:412) and never forces `tool_choice`. Add: a single forced tool `emit_parse_result` with the schema as its input, `tool_choice={"type":"tool","name":"emit_parse_result"}`, read args back. This is the cross-provider-safe path.
- **Validation** — parse into a Pydantic `ParseResult`; on schema/JSON failure, ONE retry with the validator error appended; on second failure, deterministic fallback = `{intent:"unknown", standalone_query: raw_message, signals:{needs_clarification:false...}}` so the router still routes (degrades to today's agent-loop path). Never raises on the hot path (mirror the reformulator's fallback-to-raw posture).

Provider change is additive (new optional kwarg / helper), no signature break for existing `chat()` callers.

## 7. Prompt registry changes (M1 integration)

- **New key `semantic_parser`** (user grill Q5) — replaces `reformulator` + `router` as the active front node. `variables=["current_date"]` (absolute-date resolution stays a parser duty). Fallback body = the "understand language, emit these params" instruction + schema description.
- `reformulator` + `router` keys → mark **dormant** (`active=False`), keep seeded rows for trace history / rollback; remove their call sites. Do NOT delete versions (immutable-version rule).
- Seed `semantic_parser` at v1, `production` label → v1 (mirror existing seed pattern in `ai_prompt_seed.py`).
- Trace: parser emits ONE `add_llm_span(name="semantic_parser", ...)` carrying `prompt_version`; the ParseResult JSON lands in the span output so every field is inspectable in the M2 trace view. Router is deterministic → `add_span(kind=KIND_CHAIN, name="route", output_json={intent, chosen_path})`, no LLM span.

## 8. Rollout / safety

- **Straight cutover, no flag** (user grill Q4) — AI is in beta for the system, so we replace the reformulator+router path outright rather than carry two paths. Removes the two-path maintenance burden.
- Fallback (§6) is the safety net: a parser schema/JSON failure degrades to `intent:"unknown"` → agent loop (today's default path), never a hard error. This is the only "second path" and it is failure-only, not a parallel feature flag.
- Delete `reformulator`/`router` call sites in the same PR; keep their registry rows dormant for trace history + prompt rollback.

## 9. Three-phase breakdown

**Phase 1 — prototype the contract (no FE surface; internal).** Nail `ParseResult` schema against a table of ~25 real/paraphrased questions (per anti-overfit: paraphrases, not an allowlist) covering every `intent` + edge cases (ambiguous, multi-entity, relative dates, write intent). Dry-run the parser prompt, hand-inspect outputs, lock the schema. Output: frozen schema + the question table as the eval seed for M3b.

**Phase 2 — wiring + tests.**
- BE: `ParseResult` Pydantic model; provider schema-forcing helper (OpenAI + Anthropic); `semantic_parser` prompt key + seed migration; `_parse_turn()` method; deterministic `_route(parse)`; rewire `respond()` (cutover — no flag); delete keyword gates + reformulator/router call sites.
- pytest: `_route()` switch (every intent → right path), parser schema-validation + retry + fallback-to-unknown, provider forcing for both providers. Anti-overfit: parametrized paraphrase table, not literal-string asserts.
- No new FE (parser is server-internal). FE only later reads `signals.clarify_options` in M3a.

**Phase 3 — code review** (`/code-review`), Playwright end-to-end against the live stack (every intent path), then PR.

## 10. Internal grill (resolved before user grill)

- **Q: One fat parser vs the agent also being schema-first?** A: Agent loop already emits structured tool calls — leave it. M0 is the front half only. Synthesizer stays prose.
- **Q: Does the parser duplicate `resolve_references`?** A: No — resolver hits the DB to canonicalize codes→ids; parser only EXTRACTS what the user named as text. Keep both; parser output can seed the resolver query. (Do NOT make the LLM invent ids — memory: never hallucinate ids.)
- **Q: Latency?** A: Net −1 LLM call (2→1) for most turns. Parser is a small max_tokens call. Win.
- **Q: `standalone_query` still prose — contradiction?** A: No. It's an embedding seed, an input to a deterministic tool (RAG), never user-facing. Consistent with "params for the next processing step."
- **Q: What if `intent` is wrong?** A: `unknown`/misroute degrades to the agent loop (today's default), not an error. Tie-breaker bias toward the agent loop, same as `intent_is_record_class`'s current safe default.

## 11. User grill — RESOLVED (2026-07-04)

1. **Schema fields** — ADD `language`, `time_scope`, `confidence` (§4). Keep the drafted set.
2. **`standalone_query`** — KEEP (embedding seed).
3. **Capability/smalltalk** — STAY deterministic (zero-LLM catalog short-circuit unchanged).
4. **Rollout** — STRAIGHT CUTOVER, no flag (AI in beta). Fallback-to-`unknown` is the only safety path.
5. **Naming** — `semantic_parser`.

---

## 12. Phase 1 — frozen contract + paraphrase table (sign-off gate)

Intent enum — closed set of 9, **one intent = one router branch** (domain is a param, not an intent):

| intent | route | notes |
|---|---|---|
| `capability` | deterministic catalog (no LLM) | short-circuit unchanged |
| `smalltalk` | synthesizer direct (no tools) | greetings/thanks |
| `how_to` | guide read + agent | replaces `_is_guide_question` gate |
| `definition` | synthesizer / glossary (no live data, no guide) | "what does resolved mean?" |
| `record_question` | `_render_record_answer` | requires an open record; `targets_open_record=true`; facts already loaded, no query |
| `record_action` | agent loop (write) → M3a write-confirm | mutate existing record: close/cancel/approve; `is_write_intent=true` |
| `data_query` | agent loop (RAG tools) | live system data; `entities.domain` = stock/orders/products/promotions/customers/sla/shipments |
| `form_submit` | agent loop (form choreography) | CREATE a form; `form_target` names which |
| `unknown` | agent loop | parser low-confidence / parse failure default |

Router precedence (deterministic, first match wins): `capability` → `form_submit` → `record_action` → (`targets_open_record && record open` ⇒ `record_question`) → `how_to` → `definition` → `data_query` → `smalltalk` → `unknown`. `confidence < 0.4` on a non-capability intent ⇒ demote to `unknown` (agent loop, the safe default). Both write intents (`record_action`, `form_submit`) set `is_write_intent=true` → M3a confirm gate.

**Paraphrase eval table** (anti-overfit: paraphrases per intent, NOT an allowlist — the parser must generalize). ~4 per intent; expected = the discriminating fields only.

| # | user turn | expected intent | key fields |
|---|---|---|---|
| 1 | "what can you help me with?" | capability | — |
| 2 | "give me a rundown of what this assistant does" | capability | — |
| 3 | "anything useful you can do here?" | capability | — |
| 4 | "who signed off on this?" (record open) | record_question | targets_open_record=true |
| 5 | "why's this one still stuck?" (record open) | record_question | targets_open_record=true |
| 6 | "how long did the approval take on this case" | record_question | targets_open_record=true, time_scope=point |
| 7 | "what's my next move here" | record_question | targets_open_record=true |
| 8 | "how do I upload a packing list" | how_to | — |
| 9 | "walk me through sending a PR for approval" | how_to | — |
| 10 | "where's the button to attach a photo" | how_to | — |
| 11 | "steps for the OTP portal login" | how_to | — |
| 12 | "which products are on promotion right now" | data_query | domain=promotions, time_scope=recent |
| 13 | "list DOs for ACME last month" | data_query | domain=orders, customer≈ACME, date_range=absolute(prev month), time_scope=range |
| 14 | "stock on hand for SKU 40021" | data_query | domain=stock, product≈40021, time_scope=point |
| 15 | "orders delivered in Feb 2026" | data_query | domain=orders, date_range=2026-02-01..2026-02-28, time_scope=range |
| 16 | "I want to file a complaint" | form_submit | form_target=complaint, is_write_intent=true |
| 17 | "raise a stock inquiry for me" | form_submit | form_target=stock_inquiry, is_write_intent=true |
| 18 | "need to submit a purchase request" | form_submit | form_target=purchase_request, is_write_intent=true |
| 19 | "start a sponsorship form" | form_submit | form_target=sponsorship_form, is_write_intent=true |
| 20 | "hi there" | smalltalk | — |
| 21 | "thanks, that's all" | smalltalk | — |
| 22 | "boleh tolong check order saya?" | data_query | domain=orders, language=ms |
| 23 | "这个投诉谁处理的" (record open) | record_question | language=zh, targets_open_record=true |
| 24 | "what does 'resolved' mean" | definition | — |
| 25 | "is a GRN the same as a DO?" | definition | — |
| 26 | "close complaint C-1042" | record_action | record_ref=C-1042, is_write_intent=true |
| 27 | "approve this PR" (record open) | record_action | targets_open_record=true, is_write_intent=true |
| 28 | "cancel order SO-9931" | record_action | record_ref=SO-9931, is_write_intent=true |
| 29 | "do the thing" | unknown | confidence<0.4, needs_clarification=true |

Rows 24–25 = `definition` probes (no live data, no guide). Rows 26–28 = `record_action` write probes (distinct from `form_submit` CREATE). Row 29 = ambiguity probe — parser flags `needs_clarification` rather than guessing. Sign-off = schema (§4) + 9-intent set + this table frozen; then Phase 2 wiring.
```