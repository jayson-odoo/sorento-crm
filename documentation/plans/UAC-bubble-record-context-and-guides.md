# UAC - Bubble Record-Context + System Guides

**Status:** Draft (pre-implementation regression baseline).
**Companion to:** [`PLAN-bubble-record-context-and-guides.md`](./PLAN-bubble-record-context-and-guides.md)
**Owner:** Jayson
**Date:** 2026-06-28

## Purpose

The plan adds a **deterministic pre-route** to the in-system bubble (`AIAssistantChatService.respond`): when `page_snapshot.entity` is present **and** the message is record-class intent, the agent loop is bypassed and the record-context assembler answers instead.

The danger is **regression by theft** - the pre-route (or the new guide collection split, or the added `enabled_tools`) silently captures questions that today the agent loop answers correctly. This UAC pins the answers that **must not change** so we can run it before the change (baseline) and after (no-regression proof).

**Three answerability surfaces under test:**

1. **Operational MCP enquiries** - product, product attachments, promotion, order, incoming stock, marketing form. Must stay answerable via the **agent loop + MCP tools** exactly as today.
2. **User-guide how-to** - the new plan-related guide question must be answerable via `user_guides_read`.
3. **Pre-route discipline** - record-context assembler fires **only** for record-class + entity, never steals (1) or (2).

## How to run

- Stack up per CLAUDE.md dev sessions: BE `:8000`, FE `:3000`, MCP `:8765`, worker. Confirm MCP tools registered (`GET /api/v1/system/ai-assistant/tools` returns the 28-tool set).
- Drive the bubble through the **FE sidebar** (open a page, open the assistant bubble) per the Playwright-via-sidebar rule - not a deep URL.
- For each scenario: type the **Ask**, then confirm **Expected tool/route**, **Pass criteria**, and the **must-not** guard.
- Inspect which tool fired via `browser_network_requests` (the `/ai-assistant/chat` response carries `tool_calls: [{tool_name, ok}]`) and/or backend usage log `GET /ai-assistant/usage/queries/{message_id}`.
- LLM prose varies run-to-run - **assert on the tool that fired + the key facts present**, never exact wording.
- Run the whole sheet **twice**: once on `main` (baseline column), once on the feature branch (result column). Any baseline-PASS that flips to FAIL is a regression and blocks merge.

Legend: ✅ pass · ❌ fail · ⚠️ partial (answered but wrong tool / missing fact).

### Binding design principle - no over-fitting the LLM

Treat the LLM as a **generalized NLP being**, not a scenario-tuned one. The classifier (`intent_is_record_class`), reformulator, guide protocol, and RAG select must be **general semantic judgments** - never keyword whitelists or per-sentence special cases.

- Every example question in this UAC (and the §2A complaint set) is **illustrative of a general capability, not a literal allowlist**. Passing must come from generalization, not from matching the exact strings.
- Acceptance is by **paraphrase robustness**: ask each scenario several different ways (formal, casual, elliptical, typo'd). If only the canonical phrasing passes, it's over-fit → **fail**, even if the demo sentence works.
- Near-miss negatives must be rejected: questions that contain record-ish words ("approve", "rejected") but are generic/definitional/capability questions must NOT route to the assembler.
- Forbidden fix: making a failing scenario pass by adding a keyword branch or a sentence-specific prompt hack. Fix the general capability or accept general behavior.

---

## Section 1 - Operational MCP enquiries (regression - must stay answerable)

These run with **no `page_snapshot.entity`** (general catalog questions, not viewing a record). Pre-route must NOT engage; the **agent loop** must select the listed MCP tool. This is the core "normal MCP tools still usable" guarantee.

| # | Domain | Ask (example) | Expected tool fired | Pass criteria | Must NOT |
|---|--------|---------------|---------------------|---------------|----------|
| 1.1 | Product | "What products do we have from brand <X>?" / "Show me product <code>" | `crm_master_products_list` (may chain `crm_lookup_resolve` for brand→UUID) | Answer lists matching products with human-readable names; no UUIDs in prose | Not answered by assembler; not a fallback "I can't help" |
| 1.2 | Product attachments | "What attachments / spec sheets exist for product <code>?" | `crm_master_product_attachments_list` (+ `crm_lookup_resolve` for product code) | Lists product attachments (filename/type) for the resolved product | Not silently empty when the product has attachments; not assembler |
| 1.3 | Promotion | "What promotions are active right now?" / "Promotions for product <code>?" | `crm_marketing_promotions_list` (or `crm_marketing_promotion_products_list`) | Returns active-first promotions; if none active, fallback rows flagged (`fallback_used`) | Not assembler; active-first behavior unchanged |
| 1.4 | Promotion attachments | "Any promo flyers / attachments for promotion <name>?" | `crm_marketing_promotion_attachments_list` | Lists promotion attachments | Not assembler |
| 1.5 | Order | "What orders does customer <name> have?" / "Show recent orders" | `crm_order_management_orders_list` (or `_by_product`) | Returns orders, capped at limit=20 for AI principal, sanitized (no billing/shipping address) | Not assembler; cap + sanitization unchanged |
| 1.6 | Incoming stock | "When is product <code> arriving?" / "Incoming shipments?" | `crm_incoming_stock_by_product` / `_shipments` / `_list` | Returns ETA / shipment rows for the product | Not assembler; not empty when shipments exist |
| 1.7 | Marketing form | "What marketing forms / sponsorship forms exist?" | `crm_forms_management_forms_list` | Returns forms list | Not assembler |
| 1.8 | Stock balance | "How much stock of <code> do we have?" | `crm_inventory_stock_balance_list` | Returns balances with warehouse relabel vocabulary (system_location/warehouse) | Numerics answered via tool, not hallucinated |
| 1.9 | Reference resolve | "Find customer <partial name>" | `crm_lookup_resolve` then domain tool | Resolves text→canonical entity before the domain call | - |

**Section 1 gate:** every row that PASSES on `main` must PASS on the branch. The pre-route's `intent_is_record_class` classifier must return **false** for all of these (general catalog, not record-class). If any row routes to the assembler → pre-route is over-firing → block.

---

## Section 2 - User-guide how-to (the plan's new answerable)

Run **with** a relevant `page_snapshot` (viewing the page the question is about), but these are **procedural**, not record-class - must route to `user_guides_read` (Q4b: guide-first for procedural), not the assembler.

| # | Ask (example) | Expected | Pass criteria | Must NOT |
|---|---------------|----------|---------------|----------|
| 2.1 | "How do I upload an attachment to a folder?" | `user_guides_read` called once with the question verbatim; answer quotes real **button labels** with inline markdown deep links preserved | Concrete steps + clickable menu/route links intact (per USER GUIDE PROTOCOL + `_inject_route_links`) | Not "go read this URL" with no steps; links not unwrapped to plain bold |
| 2.2 | Plan-specific: "What's next on this complaint / which button do I click to approve?" (while viewing a complaint) | `user_guides_read` grounded by record facts (Q4b). Assembler MAY supply current-state facts, but the **procedural answer** comes from the guide | Answer names the actual next-step control from the guide, consistent with the record's current state | No invented transition map; no button label not in the real component/guide |
| 2.3 | "How do I use the AI assistant / what can it answer?" | `user_guides_read` (system-usage collection - bubble only) | Answers from the system-usage guide | system-usage guide must NOT be reachable from the external/WhatsApp path (Q7 scope) |
| 2.4 | Guide miss: "How do I configure the quantum flux capacitor?" | `user_guides_read` returns `NO_MATCH` / `OUTLINE_ERROR` | Bubble says no matching guide - honest miss | Does not fabricate steps |

**Section 2 gate:** 2.1 - 2.3 answered from the guide with steps + preserved links. Verify links survived via `documents.info` API, not the Outline UI (UI strips query-bearing links - CLAUDE.md lesson).

---

## Section 2A - Complaint question coverage (MANDATED)

These six questions are the acceptance bar for the complaint tracer. Every one must be answered correctly. They span both surfaces - four are record-fact (assembler), one is pure procedural (guide), one is a **fusion** (guide steps grounded by the record's current state). Run each while **viewing a complaint detail page** (so `page_snapshot.entity = {complaint, id}` is set).

| # | Ask (verbatim variants) | Surface | Source field / section | Pass criteria |
|---|-------------------------|---------|------------------------|---------------|
| A1 | "What is this complaint about?" | assembler | record **subject / description** | Answer states the complaint subject + short description. **GAP** - assembler response shape must add a `subject`/`about` field (not in the §Contracts shape yet). |
| A2 | "Who approved this complaint?" | assembler | `approval.decided_by` (+ `decided_at`) | Names the approver (human-readable) and when. If not yet approved → states current approval status, no fabricated name. |
| A3 | "How long did one person take to approve this complaint?" | assembler | **approval lead-time** = `decided_at − submitted/assigned_at` | Returns elapsed duration to the approval decision. **GAP** - this is *approval* lead-time, distinct from `sla.lead_time` (SLA-tier based). Assembler must expose it separately or the answer conflates the two clocks. |
| A4 | "What's the rejection reason?" | assembler | `current_state.reason` / `approval.comments` (`rejection_reason`) | Quotes the actual rejection reason. If not rejected → says so, doesn't invent one. |
| A5 | "What's the process flow for a complaint?" | **guide** | `user_guides_read` - complaint guide, process-flow section | Lists the complaint lifecycle states + transitions from the guide. record-class = **false** (generic, not this record). Routes to guide even with an entity on screen. |
| A6 | "What should I do now?" (at each state) | **guide + assembler (fusion)** | guide per-state next-action, **grounded by** `current_state.status` | Answer names the next action for **this complaint's current state** specifically - e.g. pending-approval → "approve/reject"; rejected → "revise & resubmit / close". Must be state-correct, from the guide, not invented. |

**Authoring prerequisites (Track B) - A5/A6 cannot pass without these:**
- The complaint guide MUST contain (a) a **process-flow** section enumerating every state and transition, and (b) a **per-state "what do I do now"** section keyed by state, grounded in real FE component controls (actual button labels). Without (b), A6 has no source.

**Design decision required (Phase 2) - A6 routing:**
- Q6 says the record-class branch does "no tool-routing"; Q4b says next-step routes to `user_guides_read` grounded by record facts. A6 needs **both** the assembler facts AND a guide read. Resolve explicitly: either (i) `intent_is_record_class` returns true for next-step AND the record-class branch is allowed one `user_guides_read` call, or (ii) next-step is a third route (assembler-fetch → guide-read → render). Pin the chosen path with a test. Until resolved, A6 is the one scenario that can silently degrade to generic (non-state-aware) advice.

---

## Section 3 - Pre-route discipline (new behavior - the regression firewall)

The assembler is the new thing. It must fire **only** when both conditions hold, and must be JWT-gated.

| # | Condition | Ask | Expected | Pass criteria |
|---|-----------|-----|----------|---------------|
| 3.1 | entity present + record-class | Viewing complaint CMP-…, ask "Why was this rejected? Who approved it? What was the lead time?" | Pre-route fires → `GET /api/v1/assistant/record-context/complaint/{id}` → LLM renders prose from facts; **no MCP tool_calls** | Answer states set_by + reason + SLA `{elapsed,target,breached}` from assembler; `tool_calls` empty (assembler is not an MCP tool) |
| 3.2 | entity present + NOT record-class | Viewing a complaint, ask "What promotions are active?" | Pre-route declines → agent loop → `crm_marketing_promotions_list` | Catalog question still answered by MCP even while an entity is on screen (Section 1 not stolen by presence of entity) |
| 3.3 | entity present + procedural | Viewing a complaint, ask "How do I escalate this?" | `user_guides_read` (Section 2), not assembler-only | Guide answers the how-to; assembler facts may ground it but don't replace it |
| 3.4 | no entity + record-class phrasing | No record on screen, ask "Why was it rejected?" | Agent loop / clarify - assembler needs an id | No assembler call without `page_snapshot.entity`; graceful clarify, not a 500 |
| 3.5 | RBAC denial | User lacking the entity's view permission asks 3.1 | Assembler returns 403; bubble degrades to "you don't have access", does not leak facts | Same view permission as the detail page enforced |
| 3.6 | Scope enforcement | (test) Call `GET /assistant/record-context/...` with `X-API-Key`/EXTERNAL_API_KEY principal | **Denied** | Assembler is JWT-only, never an MCP tool - keeps it out of n8n/WhatsApp reach (Q7) |
| 3.7 | Entity not found | Viewing valid page but assembler id 404s | Bubble says record not found, no crash | No partial/garbage facts |

**Section 3 gate:** assembler fires for 3.1 only; 3.2/3.3 prove it does NOT cannibalize MCP/guide answers; 3.5/3.6 prove scope/RBAC; 3.4/3.7 prove graceful degradation.

---

## Section 4 - Cross-cutting / non-regression invariants

| # | Invariant | Check |
|---|-----------|-------|
| 4.1 | Tool dropdown intact | `GET /ai-assistant/tools` still returns the full 28-tool set after MCP restart; new guide split didn't drop operational tools |
| 4.2 | `enabled_tools` coverage | The bubble's `enabled_tools` config still includes every Section-1 operational tool (Q deferred item: WhatsApp parity) - none removed |
| 4.3 | Sanitization unchanged | Orders/stock/GRN responses still strip internal IDs/UUIDs/addresses (existing sanitizer tests still green) |
| 4.4 | page_snapshot additive | Adding `entity` to `PageSnapshotPayload` is additive - old clients sending no `entity` still work (field optional, defaults null) |
| 4.5 | Anti-drift | Any operational capability added lands in shared MCP/backend layer, inherited by both brains - not bubble-only (except assembler + system-usage guide, which are intentionally bubble-only per Q7) |
| 4.6 | Usage/wishlist logging | Every turn still writes `AIAssistantUsageLog`; unanswered turns still tag wishlist clusters |
| 4.7 | **Session-var isolation** | The bubble path NEVER reads or writes `respond_contacts.session_vars`. That column is n8n-WhatsApp-only (keys `flow`/`last_result_set`/`turns`/`merged`, keyed by `respond_io_id`, written solely by `PUT /external/conversation-variables/{respond_io_id}`). Bubble state lives only in `ai_assistant_*` tables keyed by `(user_id, conversation_id)`. The assembler is read-only - it must not persist anything onto the contact. Mixing the two stores would cross-contaminate WhatsApp and bubble conversation state for the same person. |

---

## Sign-off

| Surface | Result | How verified | Date |
|---------|--------|--------------|------|
| §1 Operational MCP (promo, upload how-to sampled) | ✅ | live service e2e: promotions→`crm_marketing_promotions_list`, upload→`user_guides_read` (no theft with entity on screen) | 2026-06-28 |
| §2A complaint A1 - A6 | ✅ | live service e2e against real complaint CMP-20260522-0007 + live LLM/MCP/Outline. A4 & A6 fixed after first run (classifier retry + enriched fusion guide-query) | 2026-06-28 |
| Fan-out: stock_inquiry / purchase_request / sponsorship_form | ✅ 15/15 | live e2e on real records (SI26-0088, PR26-0322, PSSF26-0325): about, who-decided, lead-time, what-to-do-now, process-flow all grounded + regression. Adapter registry; per-entity RBAC; lifecycle guides pushed to Outline | 2026-06-28 |
| §2 user-guide (process flow / upload) | ✅ | pushed lifecycle guide found & used (A5); upload guide (REG) | 2026-06-28 |
| §3 pre-route discipline (3.1/3.2/3.4/3.5/A6) | ✅ | offline pytest `test_ai_assistant_record_context_preroute.py` (7 routing/isolation tests) | 2026-06-28 |
| §3.6 EXTERNAL_API_KEY denied | ✅ | live 401 + pytest `test_record_context_route.py` | 2026-06-28 |
| §4.7 session-var isolation | ✅ | pytest (tripwire + no-write) | 2026-06-28 |
| classifier generalization (21 paraphrases + near-miss) | ✅ 21/21 | live-LLM eval (`RUN_LLM_EVALS` set) | 2026-06-28 |
| FE entity wiring | ✅ | vitest 6/6, `npm run build` green | 2026-06-28 |
| **Browser UI click-through** | ⏳ owner | creds not available to agent; service-level e2e stands in. Spec `e2e/ai-bubble-record-context.spec.ts` ready (needs `REQUEST_BATCH_E2E_*`) | - |

**Merge gate:** all met above except the browser UI click-through (owner's final check). §1 not regressed; §2A A1 - A6 grounded; §3.1 assembler-only; §3.2 no theft; §3.6 api-key denied.
