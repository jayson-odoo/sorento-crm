# PLAN — Post-security batch (UI-leak removal, lookup SQL hardening, AI-assistant safe slice, novice capability)

**Status:** DRAFT for user grill, 2026-06-29. No code written. Grounded against live code; every step cites `file:line`.
**Predecessors:** `documentation/plans/PLAN-audit-traversal-todo.md` (master findings), `documentation/plans/PLAN-ai-assistant-architecture.md` (already grill-revised — this plan only schedules its "safe slice").
**Owner:** Claude (planner). Implementation deferred until the open questions at the bottom are answered.

This batch follows the security-first work already merged on `security/audit-hardening-20260629`. Each item below is documented as: **(a) approach · (b) alternative rejected · (c) risks + blast radius · (d) verification · (e) open questions**. A recommended cross-item sequence and a consolidated grill list close the doc.

---

## ⚠️ Internal plan-grill verdicts (2026-06-29) — revisions before implementation

Adversarial review of THIS plan. Items 1, 2, 3d SOUND. Items 3a/3b/3c and 4 need the changes below.

- **Item 1 (UI leak) — SOUND.** Only `demo1` layout is mounted; `MENU_MEGA` consumed by demo1/7/9 only; `<Breadcrumb/>` exists + null-safe to replace `<MegaMenu/>`. Removing the mobile mega-menu sheet is safe (SidebarMenu stays). Gated only on user decisions (footer URLs, Support/ticket-management).
- **Item 2 (lookup SQL) — SOUND, defense-in-depth.** Injection is ALREADY closed: `lookup_eligibility.py:151-175` resolves table/column against `Base.metadata.tables[...].columns[...]` before the f-string. So this is a cleanup, not an open hole → LOW priority. Core `select(col).where(col.isnot(None)).distinct()` rewrite must preserve the `_REGISTRY` test-path `set()` fallback or tests break.
- **Item 3a (FE streaming) — RISKY, RE-SEQUENCED.** `llm_provider.py:180-242` is fully blocking; NO streaming method on either provider. Real work = (1) add `chat_stream()` to both providers, (2) new `/chat/stream` SSE endpoint, (3) **message persistence at stream-end with an idempotency key + orphaned-row cleanup** (dropped connection mid-stream must not orphan/dup), (4) `_inject_route_links` must run on FULL assembled text (buffer chunks). This is its own mini-project. **Revision: streaming becomes a separate scoped effort, NOT part of the first safe slice.**
- **Item 3b (tool-result cache) — RISKY unless keyed correctly.** MUST key on `(user_id, conversation_id, turn_id, tool_name, sorted_args_hash)` and be turn-scoped, or results leak across users/contacts (RBAC breach) or parallel requests. **Revision: explicit cache-key struct is a precondition; guide-content cache same discipline.** Only proceed with this design locked.
- **Item 3c (record classifier → keyword gate) — RISKY, NEEDS CORPUS.** `intent_is_record_class()` (:1395) does real NLP; a deictic-keyword + page-context gate WILL misroute real phrasings ("when did this change?", "who approved this?"), and the golden-question eval (3d) won't catch it (it only tests data-analysis.md examples). Fallback-to-loop is safe but adds latency for the misrouted ones. **Revision: before replacing it, build a validation corpus from `AIAssistantUsageLog` real record-page queries; gate the swap on measured routing accuracy. Possibly KEEP the LLM classifier and just cache/skip it when page has no record context.**
- **Item 3d (eval harness) — SOUND.** Assert routed tool CATEGORY, not exact prose. Build first.
- **Item 4 (capability + guides) — SOUND but add a HARD safeguard.** `/tool-capabilities/summary` (route :18) confirmed to include `internal_admin.*` + skip-tools + machine category codes → enrichment transform needed (drop admin/internal, friendly names, example Qs). Commercial-guide hold currently relies on `PARENT_TITLES` NOT listing commercial (`sync_user_guides_outline.py:52-61`) + a passive skip (:267) — **discipline only.** **Revision: add an explicit forbid-list assertion in `push()` that RAISES if `commercial` (or any held folder) is in PARENT_TITLES.** Don't rely on review discipline.

**Net revised plan:** ship 1 + 2 (quick, low-risk) and the SAFE AI slice = 3d (eval harness) + 3b (strictly-keyed tool/guide caching) + Item 4 (capability answer + getting-started + publish ready guides with the forbid-list safeguard). **DEFER** 3a (streaming) and 3c (classifier replacement) as separate, corpus/scaffolding-gated efforts — they carry the wrong-answer / latency-regression risk.

---

## ✅ FINALIZED DECISIONS (user grill, 2026-06-29) — locked scope

- **Scope APPROVED:** ship the safe set; defer streaming (3a) and the keyword-gate classifier *replacement* (3c-aggressive).
- **3c — Safe variant ONLY:** KEEP the `intent_is_record_class()` LLM call, but SKIP it when no record is open on the page (no record context → no classifier call). Zero change to what users can ask anywhere; just removes wasted calls on dashboard/settings/list pages. NOT a keyword-gate replacement.
- **Item 1 footer (REVISED — Outline is internal):** REMOVE `docsLink` (→`doc.foundryx.my`, Outline is a Foundryx-internal asset users shouldn't reach), `purchaseLink` (envato), `faqLink` (keenthemes), `licenseLink` (empty). KEEP **Support** (→`/ticket-management/tickets`, confirmed real module — consider also adding it to the sidebar) + copyright. (`config/general.config.ts` lines 2-6.)
- **Item 1 nav:** replace demo `<MegaMenu/>` with `<Breadcrumb/>` as planned.
- **NEW Item 5 — stop the assistant leaking the Outline URL** (user-reported): the assistant surfaces `doc.foundryx.my` links in answers. Root: `user_guides_read` (MCP `user_guides.py:103`) returns the Outline `url` into the tool result the LLM sees; `ai_assistant_service.py:1846-1894` tries to suppress raw doc URLs but doesn't fully. FIX: (a) drop/redact the `url` field from the guide tool-result BEFORE the LLM sees it (it should only get title + text + the internal `?guide_target`/route links), and (b) post-filter the final answer to strip any `doc.foundryx.my` (and Outline base) URL. Verify with a question whose guide answer previously showed the link. Goal: assistant cites in-app routes + inline steps only, NEVER the Outline URL.
- **Item 2 (lookup SQL):** confirmed defense-in-depth (already injection-safe) → LOWEST priority, optional cleanup.

**Still NOT executing — awaiting final user go-ahead on this locked scope.**

---

## Recommended SEQUENCE (read this first)

Ordered by risk/leverage and dependency:

1. **Item 1 — UI/template-leak removal** FIRST. Zero backend risk, user-flagged, visible-to-customers embarrassment (demo "Profiles/Network/Apps" nav + Envato/Keenthemes footer links on a listed-company product). Pure FE, single active layout (`demo1`). Quick, high signal. No dependency on anything else.
2. **Item 2 — lookup_binding SQL hardening** SECOND. Small, isolated backend change with existing test coverage to lean on. Independent of the others. Do it while UI rebuild/verify of Item 1 is in flight.
3. **Item 4 — Novice capability answer + getting-started guide + publish ready module guides** THIRD. It is a *prerequisite input* to Item 3's eval harness (the per-module `data-analysis.md` example questions are the golden-question seed) and it is mostly docs + one deterministic endpoint-render path. Lower risk than Item 3's streaming/caching plumbing. **Dependency:** the Outline publish sub-step must NOT publish `commercial/*` (held until the module is restored+enabled per the audit decision log).
4. **Item 3 — AI-assistant safe slice** LAST, and *internally sequenced by risk* (3a→3d below). It is the largest blast radius (hot path every user message) and benefits from Item 4's eval harness existing first so latency/correctness can be measured before/after.

Rationale: 1 and 2 are independent quick wins; 4 produces the eval harness + golden questions that 3 needs to prove "no regression"; 3 is the riskiest so it goes last with a safety net in place.

---

## Item 1 — UI / template-leak removal

**Findings grounded:**
- Active layout is **only `demo1`** — `app/(protected)/layout.tsx:62` renders `<Demo1Layout>`. The other `demo2..demo10` dirs exist but are never mounted by the protected app (they are template leftovers). **Blast radius for the running product = demo1 only.** Changing `demo2..10` footers/mega-menus is unnecessary and out of scope.
- **Top mega-menu**: `app/components/layouts/demo1/components/header.tsx:143` renders `<MegaMenu />` for non-mobile, non-`/account` routes. `MegaMenu` (`.../components/mega-menu.tsx:8,24-28`) reads `MENU_MEGA[0..4]` by index → demo routes "Home / Profiles / My Account / Network / Apps" (`config/menu.config.tsx:1589-1911`). Mobile equivalent: `MegaMenuMobile` (`header.tsx:131`) → `MENU_MEGA_MOBILE` (`menu.config.tsx:1993`).
- **Footer**: `app/components/layouts/demo1/components/footer.tsx` links `generalSettings.purchaseLink` (Envato), `faqLink` (keenthemes/metronic), `licenseLink` (`''` → renders an empty-href "License" link), plus a `Support` `<Link href="/ticket-management/tickets">`. Config: `config/general.config.ts` (purchase/faq/about → keenthemes; license empty; `docsLink` → Outline = correct).
- `ticket-management/tickets` route EXISTS (`app/(protected)/ticket-management/tickets/`) but is NOT in `config/menu.config.tsx` (no sidebar entry). FE audit already flagged this as orphaned/ungated.
- `MENU_MEGA` / `MENU_MEGA_MOBILE` are referenced ONLY by the `demo1/7/9` mega-menu components (grep confirmed). Removing demo1's render does not touch demo7/9 (unmounted) and does not require deleting the `MENU_MEGA` export.

### (a) Approach (recommended)
**Mega-menu — replace, don't blank.** In `demo1/header.tsx`, drop the `<MegaMenu />` branch and render the existing `<Breadcrumb />` for ALL routes (it already renders for `/account` only at `header.tsx:140-143`). `Breadcrumb` (`.../components/breadcrumb.tsx`) is driven by `MENU_SIDEBAR` + `getBreadcrumb`, returns `null` when no match — so it degrades gracefully and gives real product context (e.g. "Complaint Management › Complaints") instead of an empty gap in the header's `justify-between` flexbox. Also remove the mobile `MegaMenuMobile` sheet trigger (`header.tsx:113-135`) so the second hamburger (`SquareChevronRight`) doesn't open the demo tree on phones. Leave the `MENU_MEGA*` exports in `menu.config.tsx` untouched (dead but harmless; deleting them is a larger, riskier diff touching demo7/9 — defer to a separate cleanup).

**Footer — point to real Foundryx URLs, drop the dead ones.** Edit `config/general.config.ts`: keep `docsLink` (Outline, correct). Set `purchaseLink`/`faqLink`/`aboutLink`/`devsLink`/`licenseLink` to real Foundryx URLs OR remove the corresponding `<a>` elements from `demo1/footer.tsx`. **Decision needed (e).** Remove the `licenseLink` empty-href link regardless (an `href=''` link is a navigation bug). For `Support` → keep pointing at `/ticket-management/tickets` only if that module is intended+gated; otherwise remove the Support link until ticket-management is wired into the sidebar with RBAC.

### (b) Alternatives rejected
- **Delete `MENU_MEGA` + all mega-menu components outright.** Rejected for *this* batch: it spiders into demo7/9 components and the `partials/mega-menu/*` subtree, a much bigger diff with no added product value over simply not rendering it. Keep as a follow-up "remove template demos" cleanup.
- **Hide the mega-menu (CSS/conditional) but keep it mounted.** Rejected: leaves demo routes one inspector-toggle away and still ships dead nav config; replacing with Breadcrumb is cleaner and adds value.
- **Leave the header gap empty after removing MegaMenu.** Rejected: an empty centre column looks broken; Breadcrumb fills it with real nav.
- **Point footer links at Foundryx marketing pages we don't control yet.** Flagged as a decision, not auto-chosen — do not invent URLs.

### (c) Risks + blast radius
- Blast radius confined to `demo1` (the only mounted layout) + `config/general.config.ts`. demo2..10 untouched.
- `Breadcrumb` already imported in the same folder; rendering it for all routes is low risk but must be checked on routes with no `MENU_SIDEBAR` match (returns `null` → header centre simply empty, same as a deep page today). Verify `/store-client` and `/account` branches still behave (header.tsx has special-cases for both).
- Removing the mobile mega-menu sheet removes one of two hamburgers on mobile — confirm the remaining `SidebarMenu` sheet still gives full nav (it does; it renders `MENU_SIDEBAR`).
- Footer link removal could 404-proof the "Support" path; confirm with the ticket-management gating decision.

### (d) Verification
Per CLAUDE.md browser rule (sidebar-first, prod build):
- Rebuild FE (`npm run build && npm start`), Playwright MCP from `/`: desktop 1400px — confirm header no longer shows Profiles/My Account/Network/Apps; breadcrumb shows the current module path; footer shows only real links, no empty "License".
- Mobile ~375px — confirm only the sidebar hamburger opens product nav; no demo mega-menu; footer wraps (the audit noted "License" clipping at 390px — verify fixed or removed).
- `browser_console_messages` clean; click a deep page and a `/account` page to confirm breadcrumb/Breadcrumb special-cases.
- Vitest: a small render test for `demo1/footer.tsx` asserting it renders only the approved links and no `href=""`. Optional render test that header renders `Breadcrumb` not `MegaMenu`.

### (e) Open questions
- **OQ1.1** Footer links: give me real Foundryx URLs for Purchase/FAQ/About, or should I just remove those `<a>`s and keep Docs (Outline) only?
- **OQ1.2** `Support` footer link → is `ticket-management` an intended product module? If yes I'll add it to `menu.config.tsx` with RBAC gating (separate task); if no, remove the Support link for now.
- **OQ1.3** OK to leave the dead `MENU_MEGA`/`MENU_MEGA_MOBILE` exports + demo7/9 components in place (separate cleanup), or do you want the full template-demo purge in this batch?

---

## Item 2 — `lookup_binding_service.py` f-string SQL hardening

**Findings grounded:**
- `app/services/lookup_binding_service.py:40-44` runs `text(f"SELECT DISTINCT {data.column_name} FROM {data.table_name} WHERE {data.column_name} IS NOT NULL")` inside a broad `try/except Exception` that swallows to `existing_vals = set()`.
- This executes ONLY after `get_eligibility(data.table_name, data.column_name)` returns truthy (`:23-27`). `get_eligibility` (`lookup_eligibility.py:210-213`) resolves against `Base.metadata.tables[table].columns[column]` (the `_eligibility_from_metadata` path) OR the in-memory `_REGISTRY` override used by tests. The metadata path rejects unknown tables/columns, FKs, PKs, blacklisted names/suffixes. **So in production, `table_name`/`column_name` are constrained to real SQLAlchemy identifiers — the injection surface is already closed by validation.** This is defense-in-depth, not an open hole.

### (a) Approach (recommended)
**Build the query from the resolved metadata objects, eliminating string interpolation entirely.** Since eligibility already proves the `(table, column)` exist in `Base.metadata`, resolve `tbl = Base.metadata.tables[data.table_name]` and `col = tbl.columns[data.column_name]`, then issue a SQLAlchemy Core statement: `select(col).where(col.isnot(None)).distinct()` and execute via `self.db.execute(stmt)`. No f-string, identifiers emitted/quoted by SQLAlchemy. Also **narrow the bare `except Exception`** to log-and-continue (it currently hides real DB errors). Preserve the test-override path: when `_REGISTRY` is active and the table is NOT in `Base.metadata` (synthetic test tables), skip the existing-rows check (set `existing_vals = set()`), matching today's effective behavior so existing tests stay green.

### (b) Alternatives rejected
- **Wrap identifiers in `sqlalchemy.sql.quoted_name` / `literal_column` and keep the f-string.** Rejected: `literal_column` does not quote and still concatenates; `quoted_name` quotes but you're still hand-building SQL. Using the actual `Column` object is strictly safer and removes the string path.
- **Do nothing — rely on existing metadata validation.** Tenable (the audit marks this MEDIUM, "guarded"), but a listed-company codebase shouldn't ship interpolated identifiers even when guarded; the Core rewrite is cheap and removes the class of risk + the error-swallowing bug. Recommend doing it.
- **Reflect the table at runtime via `Table(..., autoload_with=engine)`.** Rejected: unnecessary round-trip; `Base.metadata` already has the table.

### (c) Risks + blast radius
- Single function (`create`). Behavior must stay identical: same DISTINCT non-null values feeding the `unknown = existing_vals - opt_values` guard (`:47`).
- **Behavior-change risk:** if the column's runtime type differs from metadata expectation the Core path could coerce differently than raw text; mitigate by selecting the column as-is (no cast) and comparing as Python values exactly like today.
- **Test-path risk:** `_REGISTRY` test fixtures register synthetic `(table,column)` whose physical table may not exist; the current `try/except` returns `set()`. Must replicate that (metadata-miss → skip check) or existing lookup-binding tests break.

### (d) Verification
- Run existing suite: `pytest tests/ -k lookup` (and any `test_lookup_binding*`/`test_lookup_eligibility*`). Confirm green.
- Add a pytest **injection-attempt** test: attempt to create a binding with a malicious `table_name`/`column_name` (e.g. `"x; DROP TABLE users"`) and assert it is rejected at the eligibility gate (422) and never reaches SQL. Add a happy-path test binding a real eligible column and asserting the existing-rows validation still runs (seed a row with an out-of-set value → expect the "values not in this set's options" 422).
- No browser step (pure backend).

### (e) Open questions
- **OQ2.1** Confirm appetite: do the Core rewrite now (recommended), or leave as-is given the metadata guard already blocks injection? (I recommend doing it — cheap, also fixes the error-swallowing `except`.)

---

## Item 3 — AI-assistant "safe slice" (from PLAN-ai-assistant-architecture.md)

The architecture plan's grill verdict already scoped the safe, zero-wrong-answer slice: **(3a) FE streaming, (3b) tool-result + guide-content caching, (3c) drop the redundant intent-classification LLM call using existing keyword triggers, (3d) build an eval harness.** Below each is grilled against the live code and **sequenced by risk: 3d → 3b → 3c → 3a** (build the measurement harness first; then the safest behavior-preserving caches; then the one LLM-call removal; then the FE/transport change last).

**Findings grounded:**
- Per-message hot path in `respond()` (`ai_assistant_service.py:365-655`): reformulate LLM (`:434-448`), entity resolve (`:450-464`), RAG tool-select (`:472-484`), then either deterministic record render or `_run_agent_loop`.
- **Intent-classify LLM call**: `intent_is_record_class()` (`:1395-1468`) is a dedicated cheap LLM round-trip (max_tokens=4, 2 retries) used to decide record-class short-circuit. Keyword triggers already exist for the *guide* path: `_GUIDE_QUESTION_TRIGGERS` + `_is_guide_question()` (`:823-834`).
- **Guide content re-read every turn, no cache**: `_run_agent_loop` pre-fetches `user_guides_read` via a fresh `MCPRuntimeClient` on every guide-question turn (`:973-993`). No memoization of guide text or tool results anywhere (confirmed by the architecture audit).
- **FE does not stream**: `sendAIAssistantMessage` (`lib/aiAssistantChatApi.ts:51-70`) POSTs `/api/v1/system/ai-assistant/chat` and `await r.json()`s the FULL conversation. BE route returns `AIAssistantConversationResponse` (`api/v1/system/ai_assistant.py:170-190`) — blocking, whole-conversation.
- **Transport is a DIRECT fetch to FastAPI** (`lib/api.ts:165,468` — `NEXT_PUBLIC_API_URL` + Bearer), NOT a Next.js route-handler proxy. → SSE/chunked streaming is feasible without rewriting a proxy buffer layer. Good.

### 3d — Eval harness (DO FIRST)
**(a) Approach:** Build an offline harness that loads the example NL questions from each module `documentation/user-guides/<module>/data-analysis.md` (inventory/delivery-orders/product/sla exist; Item 4 adds more) as a golden set, runs each through `AIAssistantChatService.respond()` (or a thin internal entrypoint) against a seeded test DB / recorded fixtures, and records per-question: routed path, tool(s) chosen, latency, and a correctness signal (did it answer / pick the expected tool category). Output a CSV/JSON baseline checked into `sorento_crm_backend/tests/eval/` (data only, not a report md). Run via a pytest marker (`pytest -m eval`) so it's repeatable and CI-skippable.
**(b) Alternative rejected:** live-LLM assertion in CI on every PR — too slow/flaky/costly; instead snapshot a baseline and diff latency/route, gate manually. Also rejected: hand-authoring a brand-new question bank — reuse the guide questions (they're the SoT and feed Item 4 too).
**(c) Risks:** needs an LLM key + seeded data to be meaningful; correctness scoring is fuzzy (mitigate: assert on routed tool *category* + non-empty grounded answer, not exact prose — aligns with the "no-overfit, paraphrase" memory rule). Don't block other items on full coverage.
**(d) Verification:** the harness IS the verification tool; sanity-check it reproduces a known-good answer for 3-5 questions before trusting deltas.
**(e) OQ:** see OQ3.1 (run mode/cost) and OQ3.4 (correctness bar).

### 3b — Tool-result + guide-content caching (DO SECOND — behavior-preserving)
**(a) Approach:** Add a **per-conversation, per-request** cache (in-memory, keyed within the `respond()` call / short TTL): (1) guide-content cache keyed by `user_guides_read` query so a multi-turn thread re-reading the same guide doesn't re-hit Outline (`:973-993`); (2) tool-result memo keyed by `(tool_name, sorted args hash)` so the agent loop doesn't repeat identical MCP calls within one response. Reuse the already-computed query embedding within the turn instead of recomputing.
**(b) Alternative rejected:** Anthropic `cache_control` prompt caching — the architecture grill already REFUTED this as written (system prompt is built dynamically per turn: record facts `:949-965`, guide text `:973-1006`, snapshot). It requires restructuring message assembly (stable blocks first, breakpoint, dynamic after) and is explicitly deferred. Do NOT attempt prompt caching in the safe slice.
**(c) Risks + blast radius:** **correctness risk = staleness.** Guide content rarely changes mid-conversation (safe). Tool results CAN change between turns (e.g. stock levels) — so the memo MUST be scoped to a SINGLE response/turn (within one agent loop), NOT across turns, or "what's the stock now?" asked twice could serve a stale number. This is the key grill point: turn-scoped only. Cache must be keyed including the act-as user / auth context to avoid RBAC leakage across users (the assistant runs per-user).
**(d) Verification:** eval harness latency delta (expect a cut on guide/multi-tool turns); add unit tests: same tool+args within a turn calls MCP once; different args call twice; guide cache hit on repeated query within a thread; assert NO cross-turn reuse of a volatile tool result.
**(e) OQ:** OQ3.2 (is turn-scoped tool memo acceptable, or do you want a short cross-turn TTL for read-only catalog tools only?).

### 3c — Drop the redundant intent-classification LLM call (DO THIRD)
**(a) Approach:** Replace the dedicated `intent_is_record_class()` LLM round-trip (`:1395-1468`) on the hot path with the existing deterministic signals: the user is on a record page (`page_snapshot.entity` present) AND the message contains record-deictic triggers ("this", "it", "here", record-type noun) — a keyword/heuristic gate analogous to `_is_guide_question`. Crucially, per the architecture-plan revision and the in-code comment at `:491-494`, **record facts are injected whenever the user is viewing a permitted record regardless of the classifier** — the classifier ONLY decides whether to short-circuit vs fall through to the agent loop. So a deterministic gate that errs toward "fall through to agent loop" has no wrong-answer risk (the loop still has the facts).
**(b) Alternative rejected:** keep the LLM classifier (status quo) — it's a measurable 200-400ms + a round-trip + a documented anti-overfit concern; the architecture audit flagged it as removable. Also rejected: a *semantic cosine* classifier — adds infra for a binary decision the page-context + deictics already answer.
**(c) Risks + blast radius:** the classifier today is "general NLP, not keyword" by deliberate design (anti-overfit memory rule). Moving to keywords risks misrouting edge phrasings. **Mitigation:** (i) only short-circuit to record-render on HIGH confidence (on a record page + clear deictic); (ii) low confidence → agent loop (which still has facts) — graceful, no wrong answer; (iii) validate against the eval harness (3d) before/after. This is why 3d goes first.
**(d) Verification:** eval harness route-accuracy on record-class questions (the architecture plan's record path) must not regress; add unit tests for the deterministic gate (deictic + page-entity → short-circuit; generic catalog question → fall through). Browser-verify on a complaint/PR detail page asking "who handled this?" vs "list all open complaints".
**(e) OQ:** OQ3.3 — acceptable to make record-class a deterministic page-context+deictic gate (with agent-loop fallback), accepting it errs toward the loop on ambiguity?

### 3a — FE streaming (DO LAST — transport/contract change)
**(a) Approach:** Add a NEW SSE endpoint `POST /api/v1/system/ai-assistant/chat/stream` returning `StreamingResponse` (text/event-stream) that streams assistant tokens then a final event carrying the persisted message id + metadata (links/sources/suggestions). Keep the existing blocking `/chat` for non-streaming callers/tests. FE: add a `sendAIAssistantMessageStream` in `lib/aiAssistantChatApi.ts` that reads `response.body.getReader()` (direct fetch already supported per `lib/api.ts:468`) and an `onToken` callback; `AIAssistantBubble.tsx` appends tokens to the in-flight assistant bubble. Markdown/link rendering stays (ReactMarkdown) — render incrementally or on final.
**(b) Alternative rejected:** convert `/chat` itself to SSE — breaks the documented Phase-1 contract + the existing `aiAssistantChatApi.test.ts` and any non-streaming consumer; a parallel endpoint is safer. Also rejected: WebSocket — overkill; SSE/chunked over the existing bearer fetch is sufficient.
**(c) Risks + blast radius:** biggest of the slice — touches the per-message endpoint, the provider call (needs streaming support in `llm_provider.py`), persistence timing (persist the full message at stream end, but a dropped connection mid-stream must not orphan/duplicate the row), and the deep-link re-injection (`_inject_route_links`) which currently post-processes the FULL text — it must run on the final assembled text, not per-chunk, or links break. Markdown rendered mid-stream can flash raw asterisks until complete (cosmetic). RBAC/permission gate (`require_permission("system.ai_assistant_chat.use")`) must be identical on the stream route.
**(d) Verification:** Playwright MCP: send a message, observe tokens streaming into the bubble; confirm `browser_network_requests` shows the `/chat/stream` SSE call; confirm final message has working clickable deep links (the `_inject_route_links` output). Vitest for the new FE stream reader (mock a ReadableStream). pytest for the stream route: happy path (events emitted, final message persisted once), auth denial, disabled-feature 404/400 parity with `/chat`. Verify guide-link integrity on the final text.
**(e) OQ:** OQ3.5 (latency targets p50/p95), OQ3.6 (is a streaming-but-final-rendered-markdown acceptable, i.e. show plain text while streaming then format on completion?).

---

## Item 4 — Novice "what can the system do?" capability + getting-started + publish ready guides

**Findings grounded:**
- Capability endpoint EXISTS: `GET /api/v1/system/tool-capabilities/summary` (`api/v1/system/tool_capabilities.py:18-28`) → `build_live_capability_summary()` (`mcp_tool_capability_service.py:1965+`). Output: two groups (`general_enquiries`, `form_submission`), each with `categories` (machine codes like `general_enquiries.product`, `internal_admin.procurement`), `tool_count`, and a `tools[]` list of `{tool_name, category, intent, description, method, path}`.
- **Gap for a novice answer:** categories are internal codes, tool names are `crm_*` slugs, and the list INCLUDES `internal_admin.procurement` admin-only tools (`mcp_tool_capability_service.py:1056-1148`) + `_EMBEDDING_SKIP_TOOLS` discontinued/hidden tools (`:79-97`). Raw output is machine-faithful but NOT novice-friendly: it leaks admin tools, exposes slugs/paths, and has no "module name → plain-English what you can do → example questions" framing.
- **Module guides exist**: `documentation/user-guides/{inventory(6), delivery-orders(4), product(5), sla(6), commercial(7)}` each with a `data-analysis.md`. `_shared/` has cover/escalate/dashboard/upload but **no `getting-started-for-new-users.md`** (confirmed).
- **Outline publish is folder-allowlisted by `PARENT_TITLES`** (`scripts/sync_user_guides_outline.py` PARENT_TITLES dict) = `_shared, purchasing, warehouse, marketing, project-sales-admin/manager/rep, technical-team`. It does **NOT** include `inventory/delivery-orders/product/sla/commercial`. The push loop SKIPS any folder not in PARENT_TITLES (`push()` child-sync: `if folder not in PARENT_TITLES: [skip]`). **Therefore the ready module guides currently CANNOT be published, AND `commercial/*` is already held by default** (not in the allowlist) — so a plain `push` will not leak commercial.

### (a) Approach (recommended)
**Novice capability answer — deterministic, with an enrichment layer (not raw passthrough).** Add a thin transform over `build_live_capability_summary()` that: (i) drops `internal_admin.*` categories and `_EMBEDDING_SKIP_TOOLS`; (ii) maps category codes → friendly module names; (iii) attaches 2-3 example questions per module sourced from the module `data-analysis.md` files (the same SoT used by the eval harness). Wire the AI assistant's "what can you do / what can the system do / help" intent (a `_GUIDE_QUESTION_TRIGGERS`-style keyword gate) to answer deterministically from this enriched summary — NO LLM round-trip — returning a grouped "Here's what I can help with: <module> — <plain English> — try asking: …" with clickable guide links. This realizes the architecture plan's "capability answer served deterministically from the registry."

**`_shared/getting-started-for-new-users.md`** — author a zero-knowledge orientation: login, sidebar map, where each data type lives, how to ask the assistant, link out to each module guide. Goes in `_shared` (already in PARENT_TITLES → publishes with a normal push).

**Publish only the ready module guides — via PARENT_TITLES allowlist.** Add `inventory`, `delivery-orders`, `product`, `sla` to `PARENT_TITLES` (with sort-prefixed titles, e.g. `8-Inventory`…). **Do NOT add `commercial`** — it stays held until the module is restored+enabled (audit decision log). Then `python scripts/sync_user_guides_outline.py push`. This is the cleanest selective-publish: the allowlist already gates folders; we extend it for the four ready ones and leave commercial out. After push, **verify via Outline `documents.info` API, never the UI** (CLAUDE.md gotcha: UI strips query-bearing links). Re-run `scripts/annotate_user_guides_routes.py` first so menu-path deep links are present.

### (b) Alternatives rejected
- **Render the novice answer straight from the raw `/summary` output.** Rejected: leaks admin tools + `crm_*` slugs + machine category codes; not novice-friendly; would need the assistant to LLM-summarize it (defeats the deterministic goal).
- **Hand-maintain a separate capability catalog doc.** Rejected: drifts from the live tool registry (the architecture plan's core complaint). Derive from the live summary + guide questions instead.
- **Add an `--only <folders>` CLI flag to the sync script for selective push.** Viable but more code than needed; the PARENT_TITLES allowlist already IS the folder gate — extending it is the smaller, intention-revealing change. (If you prefer an explicit flag for safety, that's OQ4.3.)
- **Use the `Outline` class directly for one-off single-doc updates** (as the earlier rename-guide did). Rejected for NEW folders: those docs don't exist in Outline yet and need parent-doc creation, which `push()` handles once the folder is in PARENT_TITLES. The single-doc approach fits edits, not first publish.

### (c) Risks + blast radius
- **Commercial-leak risk** is the headline: any change to the publish step must keep `commercial/*` out. PARENT_TITLES omission handles this, but the implementer must NOT add commercial and must verify the post-push Outline document list excludes it. (Belt-and-suspenders: also add `commercial/` to an explicit skip and assert in a script dry-run.)
- Enrichment layer must respect the same viewer-hidden-field guardrails (no `cost_price`/`invoice_price` leakage) and RBAC — but capability text is about *what tools exist*, not data, so low data-leak risk; still, don't enumerate admin-only tools to non-admins.
- Capability answer wired into the assistant = a (small) hot-path change; keep it deterministic and additive (new intent branch), with fallback to the existing path on any error.
- Outline round-trip fragility (CLAUDE.md): query-bearing deep links get stripped when a human opens the doc; mitigate per existing guidance (verify via API; prefer fragment form if `?guide_target` links are used).

### (d) Verification
- pytest: enriched-summary transform drops `internal_admin.*` + skip-tools, maps categories to module names, attaches example questions; endpoint/unit test that the assistant's "what can you do?" trigger returns the deterministic answer with NO LLM call (assert provider not invoked).
- Browser (Playwright MCP): open the assistant, ask "what can the system do?" / "help" → confirm grouped capability answer with clickable guide links; ask a novice "where do I find X" → getting-started guide surfaces.
- Outline: after `push`, call `documents.info` for the new docs to confirm text + links survived; confirm `commercial/*` is absent from the collection listing. Pull-diff (`status`) to confirm no unintended doc churn.
- Eval harness (Item 3d) consumes the same guide questions — confirm they load.

### (e) Open questions
- **OQ4.1** Is the enriched capability transform (drop admin/hidden tools, friendly module names, 2-3 example questions/module) the right novice framing, or do you want the answer to also surface "form submission" actions (PR/SF/complaint/stock-inquiry) prominently?
- **OQ4.2** Confirm the four folders to publish now = inventory, delivery-orders, product, sla (commercial HELD). Any others ready (e.g. a complaint data-analysis guide) to include?
- **OQ4.3** Publish mechanism: extend `PARENT_TITLES` (recommended, smaller diff) vs add an explicit `--only` flag to the sync script (more guardrails, more code)? Either way commercial stays out.
- **OQ4.4** Outline collection structure: module guides as new TOP-LEVEL parents (`8-Inventory`…) — the script only supports 2-level `folder/file.md`. Acceptable, or do you want a single "Modules" grouping (would need a script change for 3-level)?

---

## Consolidated OPEN QUESTIONS for the user grill

**Item 1 — UI leak**
- OQ1.1 Real Foundryx URLs for Purchase/FAQ/About, or remove those footer links (keep Docs→Outline only)?
- OQ1.2 Is `ticket-management` a real module? Add to sidebar+RBAC, or remove the Support footer link for now?
- OQ1.3 Leave dead `MENU_MEGA*` exports + demo7/9 components (separate cleanup), or full template-demo purge in this batch?

**Item 2 — lookup SQL**
- OQ2.1 Do the SQLAlchemy-Core rewrite now (recommended; also fixes error-swallowing), or accept the existing metadata guard and skip?

**Item 3 — AI assistant safe slice**
- OQ3.1 Eval-harness run mode + cost ceiling (offline baseline + manual gate vs CI)?
- OQ3.2 Tool-result memo: turn-scoped only (safe, recommended) vs short cross-turn TTL for read-only catalog tools?
- OQ3.3 OK to replace the record-class LLM classifier with a deterministic page-context+deictic gate (errs toward agent-loop fallback on ambiguity)?
- OQ3.4 Correctness bar for the eval harness — assert on routed tool *category* + grounded non-empty answer (paraphrase-tolerant), not exact prose?
- OQ3.5 Latency targets (p50/p95)? Current p50 ≈ 1.6s.
- OQ3.6 Streaming UX: show plain text while streaming then format markdown on completion (avoids mid-stream raw-asterisk flash), acceptable?
- OQ3.7 Model tier for the assistant (affects future prompt-caching viability — deferred but informs 3a/3b)?

**Item 4 — novice capability**
- OQ4.1 Novice framing: enriched general-enquiry capabilities only, or also surface form-submission actions prominently?
- OQ4.2 Confirm publish set = inventory/delivery-orders/product/sla (commercial HELD); any other ready guide to include?
- OQ4.3 Publish mechanism: extend PARENT_TITLES (recommended) vs add `--only` flag?
- OQ4.4 Outline structure: new top-level parents per module (supported) vs a "Modules" grouping (needs script change)?

**Cross-cutting**
- OQ-X1 Does this batch get its own branch off `main` (recommend yes: `feature/post-security-batch`), and do you want Items 1+2 landed/merged independently of 3+4 (they're decoupled)?
