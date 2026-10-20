# CARD: CHAT-LATENCY-SCOUT, where slow check_stock turns spend ~9s outside the LLM (20 Oct)

Status: A+B+C built red-first (small fix track), in review. Crew go 20 Oct: (a) A+B+C, A gated on the code reader's own verdict.

## Question

Prod 14-20 Oct: 344 turns over 10 s averaged 12.7 s, parser LLM only 3.4 s of it. 234 of the
344 are inventory `check_stock`. Where does the remaining ~9 s go?

## Method

Sandbox only, synthetic data (no prod access, no customer rows):

- PG16 + pgvector + redis in the sandbox, schema from `scripts.bootstrap_env`, plus the
  trigram indexes from migrations 169 and 410 that prod carries.
- Volume (`sorento_crm_backend/scripts/chat_latency_seed.sql`): 8,000 products, 40 warehouses,
  64,000 stock rows, 640,000 ledger rows, 40,000 SO lines, 15,000 PO lines, 5,000 customers,
  200,000 orders.
- Backend (:8000) and MCP server (:8765) running locally, so the stock read takes the same
  CRM -> MCP -> CRM double hop it takes in prod.
- `sorento_crm_backend/scripts/chat_latency_probe.py` runs a real `engine.run_turn` with the
  parser stubbed (prod parser is a flat ~3.1 s and is not under study). It prints the turn's
  own trace (stage -> ms), every HTTP call, SQL count/ms per stage, and every NON-parser LLM call
  (`--live-llm` lets them go out and times them; default blocks them).
- Non-parser LLM calls ran on the sandbox default model (gpt-4o), not prod's gpt-5.4-mini.

## Stage table (ms, warm second run; parser stubbed, so `understood` excludes the LLM)

| stage | code hit, detailed | code hit, compact | code hit, availability + qty | code MISS | 5 hits + 1 miss | code MISS, LLM provider failing |
|---|---|---|---|---|---|---|
| received | 60 | 55 | 34 | 38 | 50 | 48 |
| understood | 13 | 11 | 6 | 7 | 8 | 6 |
| access | 7 | 12 | 6 | 6 | 8 | 7 |
| routed (resolve) | 132 | 94 | 99 | **2,016** | **2,377** | **2,150** |
| looked_up (MCP stock read) | 188 | 187 | 172 | 153 | 218 | 152 |
| remembered | 12 | 12 | 11 | 11 | 15 | 10 |
| **wall** | **453** | **418** | **376** | **2,269** | **2,720** | **2,407** |
| non-parser LLM calls | 0 | 0 | 0 | 2 live, 1,442 ms | 2 live, 1,770 ms | 6 attempts, blocked |
| SQL stmts / ms | 96 / 132 | 96 / 108 | 106 / 94 | 226 / 360 | 222 / 376 | 214 / 416 |
| HTTP (MCP) calls / ms | 1 / 134 | 1 / 138 | 1 / 114 | 1 / 102 | 1 / 156 | 1 / 108 |

Volume does not hurt the hit path: one MCP call, ~100 SQL statements, under 0.5 s in every
policy mode. All of the extra time sits in `routed` and appears only when a product token MISSES.

## Top 3 causes

1. **A product-token miss makes two more LLM calls, one after the other, in `routed`.**
   `resolve_reference_post` (`app/api/v1/system/references.py:3224`, reached in-process from
   `lanes/business/services.py:141`) runs two calls in sequence:
   - the resolver code reader, at `references.py:3243` -> `resolver_code_reader.read_codes`
     (`app/services/resolver_code_reader.py:309`). It inherits the parser's own model
     (`PARSER_PROMPT_KEY`, `:51`), so in prod that is gpt-5.4-mini at about 3 s.
   - the spec reading, at `references.py:3606-3618` ->
     `product_spec_understanding.understand_phrase` (`app/services/product_spec_understanding.py:562`).
     Its own comment at `references.py:3598` says this "costs 2-3 SECONDS on the reply path".
   - The spec reading fires whenever any token is unresolved (`references.py:3556-3565`), even
     when the token is code-shaped like `SRT1001-BK` and the code reader has already said
     "none".
   - On top come the tier-3 embeddings (`entity_resolver.py:3051`, two calls on the first turn,
     memoized afterwards).
   - Sandbox cost was 1.4-1.8 s on gpt-4o. At prod's model speed the two calls come to roughly
     4-6 s, which is most of the missing ~9 s on a check_stock turn that misses.
2. **The spec reading has no timeout and leaves the SDK retries on.**
   - `understand_phrase` calls `provider.chat(...)` with no `timeout`
     (`product_spec_understanding.py:635`).
   - `llm_provider.chat` therefore builds the default client (`app/services/llm_provider.py:441-444`):
     OpenAI's 600 s timeout and `max_retries=2`, with backoff sleeps between attempts.
   - Measured with the provider failing: 3 attempts per call and about 1.7 s of pure backoff in
     `routed`. A slow or 429/5xx provider moment becomes up to 3 attempts in a row, which fits the
     p99 of 14-17 s.
   - The code reader's "3 s budget" is httpx's per-operation timeout (connect, read), not a
     wall clock. One sandbox call took 3,492 ms.
3. **Every LLM call opens a fresh connection.**
   - `OpenAIProvider._client` builds a new `OpenAI(...)` on every call (`llm_provider.py:378-390`,
     `:441-444`): new TCP and TLS, no keep-alive.
   - A miss turn makes 3-4 such calls, the parser included.
   - Not measurable here because the sandbox's egress goes through a proxy. Estimated at
     0.1-0.3 s per call from Malaysia to OpenAI.

Smaller, measured:

- The MCP double hop opens a new connection on both legs:
  - `MCPRuntimeClient._rpc` makes a new `httpx.Client` per call (`app/services/ai_assistant_service.py:352`).
  - The MCP server's `CRMClient` runs with `max_keepalive_connections=0`
    (`sorento_crm_mcp/sorento_crm_mcp/http_client.py:54`).
  - Together that is 100-170 ms per tool call. A plain hit makes only one call.
- The miss path runs about 140 extra SQL statements (330-385 ms): cross-type probes over orders,
  customers, forms, shipments and the like.
  - The largest single one is `_probe_customer_debtor_name` (`app/services/entity_resolver.py:1373`),
    a DISTINCT over `orders` LEFT JOIN customers. It took 236 ms at 200k orders and grows with
    `orders`.

Looked for and not found:

- No N+1 on the hit path.
- No per-row policy lookup. Stock visibility is resolved about 3 times per turn, per call
  (`stock_visibility.resolve_policy`, `:229`), each 2-5 queries.
- No full-catalogue load into Python on a code ask.
- No missing index on the hit path.

Not measurable in a sandbox, but readable from the prod trace:

- the ordering queue wait (`dispatch.wait_for_turn`, 0.2 s polls up to 30 s, the `queued` stage);
- `_answer_earlier_messages` (`engine.py:1791`) replaying earlier messages inside the same turn.

## Smallest fixes, expected savings

| # | fix | where | expected saving | red-first test |
|---|---|---|---|---|
| A | SUPERSEDED by the Build section below (owner rule: no code-shaped pattern; the gate reads the code reader's own verdict). Original idea: skip the spec reading's MODEL call for code-shaped unanswered tokens. | `references.py:3606-3618` (`allow_model=payload.understand_phrase and not all_code_shaped`) | 2-3 s on every code-miss turn | a miss on `SRT1001-BK` makes at most 1 non-parser chat call (2 today) |
| B | Give the spec reading the code reader's budget: `timeout=3.0` (which also turns SDK retries off). | `product_spec_understanding.py:635` | caps the tail: no 600 s wait, no 3 attempts | `provider.chat` is called with a non-None timeout |
| C | Reuse one `OpenAI` client per (key, timeout, base_url). | `llm_provider.py:378-390` | ~0.1-0.3 s per LLM call, 3-4 per miss turn, the parser included (estimate) | two `chat()` calls construct the client once |
| D | (later) keep-alive on both MCP legs. | `ai_assistant_service.py:352`, `sorento_crm_mcp/http_client.py:54` | tens of ms per tool call | - |

A + B + C are about 40 changed lines plus tests, with no migration and no auth change, so they
fit the small fix track.

## Prod check for crew (read-only, run on the chat connector)

```sql
-- 1) Slow check_stock turns, 14-20 Oct: time per stage.
WITH slow AS (
  SELECT t.id, t.created_at, t.finished_at, t.trace
  FROM chatbot.turns t
  WHERE t.created_at >= '2026-10-14' AND t.created_at < '2026-10-21'
    AND NOT t.is_test
    AND t.finished_at - t.created_at > interval '10 seconds'
    AND EXISTS (SELECT 1 FROM jsonb_array_elements(t.trace) e
                WHERE e->>'stage' = 'understood'
                  AND e->'raw'->'derived'->>'intent_hint' = 'check_stock')
)
SELECT e->>'stage' AS stage, count(*) AS turns,
       round(avg((e->>'ms')::int)) AS avg_ms,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY (e->>'ms')::int) AS p50_ms,
       percentile_disc(0.9) WITHIN GROUP (ORDER BY (e->>'ms')::int) AS p90_ms
FROM slow, jsonb_array_elements(slow.trace) e
WHERE e ? 'stage'
GROUP BY 1 ORDER BY avg_ms DESC;

-- 2) Non-parser model calls in the same window (usage rows carry no turn id;
--    created_at is naive, so compare against the turn times in the DB's timezone).
SELECT feature, model, count(*) AS calls, round(avg(response_time_ms)) AS avg_ms,
       percentile_disc(0.9) WITHIN GROUP (ORDER BY response_time_ms) AS p90_ms,
       max(response_time_ms) AS max_ms
FROM ai_assistant_usage_logs
WHERE created_at >= '2026-10-14' AND created_at < '2026-10-21'
  AND feature IN ('resolver_code_reader', 'spec_search')
GROUP BY 1, 2;
```

If cause 1 is right, query 1 puts `routed` at roughly 4-8 s, and query 2 shows
`resolver_code_reader` near 3 s and `spec_search` at 2-3 s. If `queued` leads instead, the time
is going to the ordering wait, which is a different fix.

## Build (crew go 20 Oct, option a)

- **A** (`references.py`, `_open_tokens_are_codes_the_catalogue_lacks`): the spec MODEL reading is skipped
  only when every still-unanswered token carries the code reader's own verdict `kind: code, matched: 0`
  (crew ruling: a code that does not exist cannot be found by a spec reading). `none` (a description),
  `family`, `error`, `not_asked`, no verdict, AND-mode results, product words a partial row left
  unanswered, or a token only non-product rows answered all keep today's model reading. No pattern of ours;
  the deterministic word read still runs.
- **B** (`product_spec_understanding.py`): `timeout=3.0` on the spec reading, which also turns SDK retries
  off. On a timeout the reading degrades to the deterministic one (the existing provider-failure arm), the
  turn continues to spec search on the customer's literal words, and the customer gets that answer (or the
  usual not-found / did-you-mean reply) after at most about 3 s instead of up to 600 s with retries. Nothing
  is left pending.
- **C** (`llm_provider.py`): one `OpenAI` client per (class, key, timeout, retries, base_url), shared across
  threads under a lock, capped at 32.
- Tests: `tests/test_chat_latency_llm_budget.py`, 12 tests (A red without the gate, B and C red before the
  change).

Measured on the real engine (sandbox, gpt-4o, parser stubbed):

| ask | before | after |
|---|---|---|
| code miss `SRT1001-BK` | 2 model calls, routed 2,016 ms, wall 2,269 ms | 1 call, routed 1,353 ms, wall 1,631 ms, same reply |
| 5 found codes + 1 dead code | 2 calls, wall 2,720 ms | 1 call, wall 1,556 ms |
| found code `MWT1005-CR` | 0 calls, wall 418 ms | 0 calls, wall 400 ms |

Accepted risks (reviewer, 20 Oct), for crew and EVAL-BENCH to weigh:

- **B's budget is near the typical call, not only the tail.** The card puts prod `spec_search` at 2-3 s, so
  3.0 s (crew-set) will cut some description readings short; those turns then answer from the deterministic
  reading. Prod query 2 above (p90 / max `response_time_ms` for `spec_search`) measures the share; raise
  `_MODEL_TIMEOUT_SECONDS` above the p95 if it is large. The staff Product Specifications preview
  (`app/api/v1/master_data/product_specifications.py:590`, through `derive_search_inputs`) gets the same
  budget, which matches its "run exactly as the chatbot would" contract.
- **A looks at tokens; the model reads the whole `query`.** If the parser emits only the dead code as an
  entity and leaves other words of the message un-tokenised ("SRT9999 matt blk wall hung basin" with one
  entity `SRT9999`), the gate skips the model and those words get only the deterministic read. This is the
  crew rule as written ("every still-unanswered token"); the EVAL-BENCH spec replay is where it would show.
- **C is fork-safe:** a forked child clears the inherited clients (`os.register_at_fork`), the same rule
  `worker.py` applies to DB sockets.
