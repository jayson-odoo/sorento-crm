# PLAN — Bubble Record-Context + System Guides

**Status:** Track A (ALL 4 entities: complaint + stock_inquiry + purchase_request + sponsorship_form) + Track B (complaint, stock-inquiry, PR/SF lifecycle guides) IMPLEMENTED & verified end-to-end against the live stack (2026-06-28). Assembler refactored to an adapter registry; per-entity RBAC; classifier routes on the original message (not the reformulation); record facts injected into the agent-loop fallback so classifier noise can't hallucinate. 15/15 e2e (5 question types × 3 fan-out entities) + regression. Pending: owner browser click-through.
**Owner:** Jayson
**Slug:** `bubble-record-context-and-guides`
**Date:** 2026-06-28

## Problem

Two AI surfaces exist and diverge:

- **n8n WhatsApp brain** (Respond incoming) — deterministic pipeline: semantic parse → `references/resolve` (text→UUID) → MCP GET tools → presenter envelope. AI used only for NLP. Trusted.
- **In-system bubble** (`AIAssistantBubble`) — its own FastAPI LLM **agent loop** (reformulate → RAG tool-select → function-calling, 6 iters). Sees only `page_snapshot` = URL + visible page text. **No entity id, no record state, no approval/SLA/audit history.**

The bubble cannot answer:
- Operational questions at parity with n8n (config/coverage gap).
- "How do I use the system / which button do I click" (no system user guide).
- Record-aware questions about what the user is viewing — "why is this complaint in this state, what's next, who approved it, what was the lead time to approve."

**Objective:** the bubble (the *system's* brain) becomes fully answerable — matches n8n's operational answerability, adds the system user guide, and adds record-context grounded in the screen/record the user is viewing. n8n WhatsApp is the **reference bar**, not a rebuild target.

## Decisions (grill Q1–Q10)

| # | Decision |
|---|---|
| **Q1/Q2** | **Two brains (B).** n8n brain → WhatsApp; FastAPI brain → bubble (keep existing agent loop). RBAC is a non-issue for the bubble — it already builds per-user scope via `AIAssistantGovernanceService`. |
| **Anti-drift rule** | Brains *orchestrate*, they don't *own answers*. Both consume the **same deterministic data layer** (MCP tools, `references/resolve`, `user_guides_read`, RAG). Never add an answerable capability to only one brain — add it to the shared backend/MCP layer; both inherit it. |
| **Anti-overfit rule** | Treat the LLM as a **generalized NLP being** — do NOT tune classifiers/prompts/routing to fit a specific sentence or scenario. `intent_is_record_class` and friends must be **semantic/general** (LLM or embedding judgment), never keyword whitelists. Over-nudging to pass one phrasing regresses others. Tests assert paraphrase robustness + near-miss negatives, not literal strings. No per-sentence special cases. (memory: `feedback_no_overfit_llm_nlp`) |
| **Q3** | **(A) FE passes entity explicitly.** A context provider registers `{entity_type, id}` for the current screen (covers detail pages **and** modals — URL-parse alone can't see modals). No LLM guessing identity. `page_snapshot` gains an `entity` field. |
| **Q4a** | **Build a deterministic assembler.** `GET /api/v1/assistant/record-context/{entity_type}/{id}` — JWT + RBAC, joins record + approval + SLA + the audit row that set current state into one structured bundle. Pure SQL assembly, no AI. |
| **Q4b** | **Guide-first for procedural, no state machine.** "Next state / what do I do / which button" routes to `user_guides_read` grounded by current record facts. Do **not** author a declarative transition map (would be a 2nd source of truth that drifts from scattered service-code guards). |
| **Q5** | **Guides authored by grounded doc agent (C) + coverage map.** Agent drafts each guide **grounded in real FE component source** (transcribes actual button labels / fields / wired flow — never invents). Driven by a route coverage map. |
| **Q5 review** | Two gates: **doc agent → review agent → human → Outline push**. No auto-publish; the guide is now the source of truth for answers. |
| **Q6** | **(ii) Deterministic pre-route for record-context.** On entry: if `page_snapshot.entity` present **and** intent is record-class → **mandatory** assembler call → inject facts → LLM only classifies intent (NLP) + renders prose. Agent loop stays as fallback for open-ended data/catalog questions. |
| **Q7** | **Scope per brain.** Record-context assembler + system-usage guide = **bubble-only**. WhatsApp keeps today's flattened operational view + operational FAQ. Enforcement: assembler is a **JWT-only route** (never an `EXTERNAL_API_KEY` MCP tool); Outline guides split into **operational** (both) vs **system-usage** (bubble only) collections/tags. |
| **Q8** | **Tracer-bullet complaint first; design adapter for all 4** (complaint, purchase_request, sponsorship_form, stock_inquiry — all share `conversation_sla_tracking` discriminated by `source_entity_type`). "Lead time" = return **both** `{elapsed, target, breached}`. |
| **Q9** | **Wishlist-driven authoring + unanswered-rate metric.** Coverage map = completeness axis; `/ai-assistant/wishlist` clusters = demand axis. Author highest-demand gap first. Loop: unanswered → wishlist cluster → guide draft → review → publish → cluster shrinks. Success = unanswered-rate drop per cluster. |
| **Q10** | **Two parallel tracks.** A (record-context) and B (guide pipeline) are independent. Complaint tracer first in A. Scope enforcement (Q7) is woven in, not a phase. |

## Contracts

### `page_snapshot.entity` (FE → bubble chat payload, additive)

```ts
interface AIPageSnapshot {
  path: string;
  search: string;
  title: string;
  visible_text: string;          // existing, max 6000 chars
  entity?: {                     // NEW — set by per-screen context provider
    entity_type: 'complaint' | 'purchase_request' | 'sponsorship_form' | 'stock_inquiry';
    id: string;                  // UUID, never rendered in UI
  } | null;
}
```

### Record-context assembler

```
GET /api/v1/assistant/record-context/{entity_type}/{id}
Auth: staff JWT + RBAC (same view permission as the entity's detail page). NOT exposed to EXTERNAL_API_KEY.
```

```jsonc
// Response (shared shape across all 4 entity types; per-type field map fills it)
{
  "entity_type": "complaint",
  "id": "…uuid…",
  "display_ref": "CMP-2026-0142",          // human-readable, no UUID in prose
  "current_state": {
    "status": "rejected",
    "set_by": "Jane Lim",                  // from audit row that set it
    "set_at": "2026-06-20T08:14:00+08:00",
    "reason": "Out of warranty window"     // rejection_reason / approval_comments
  },
  "approval": {                            // null when entity has no approval gate
    "status": "rejected",
    "decided_by": "Jane Lim",
    "decided_at": "2026-06-20T08:14:00+08:00",
    "comments": "Out of warranty window"
  },
  "sla": {                                 // null when no tracker
    "current_tier": 2,
    "assignee": "Support Team — Tier 2",
    "due_at": "2026-06-21T17:00:00+08:00",
    "is_breached": false,
    "lead_time": { "elapsed_hours": 19.7, "target_hours": 24, "breached": false }
  },
  "audit_trail": [                         // recent state transitions, newest first
    { "action": "status: pending → rejected", "by": "Jane Lim", "at": "2026-06-20T08:14:00+08:00" }
  ]
}
```

Sources per the lifecycle exploration: record row (denormalized `approved_by`/`approved_at`/`rejection_reason`/`approval_comments`), `audit_logs` (state-set row, old→new), `conversation_sla_tracking` + `conversation_sla_event_log` (tier/due/elapsed). All timestamps normalized to Asia/Kuala_Lumpur.

### Deterministic pre-route (FastAPI brain, `AIAssistantChatService.respond`)

```
on chat turn:
  if snapshot.entity and intent_is_record_class(message):   # intent = NLP classifier (the only AI judgment here)
      ctx = GET record-context(entity_type, id)              # mandatory, deterministic
      inject ctx into LLM system context
      LLM: classify + render answer (no tool-routing)
  else:
      existing agent loop (RAG tool-select → function calling)   # fallback, unchanged
```

`intent_is_record_class` = cheap classifier over a fixed record-question taxonomy (why-this-state / who-approved / next-step / lead-time / SLA-status). Pure NLP, acceptable under the determinism rule.

## Three-phase breakdown

### Track A — Record-context (complaint tracer, then fan out)

**Phase 1 — FE prototype**
- Per-screen entity-context provider; complaint detail page registers `{entity_type:'complaint', id}`.
- `aiPageSnapshot.ts` includes `entity`.
- Bubble renders record-answer UX against a **mocked** assembler response (golden + empty/no-SLA/no-approval/RBAC-denied states).
- Verify via Playwright MCP through the sidebar.

**Phase 2 — BE wiring + tests**
- `GET /assistant/record-context/{entity_type}/{id}` — complaint adapter; shared field-map abstraction designed for all 4.
- Deterministic pre-route in `AIAssistantChatService` + intent classifier.
- Tests (land here, not deferred):
  - **pytest** — assembler happy path + auth denial (non-staff / wrong RBAC) + entity-not-found; pre-route picks assembler vs agent loop.
  - **vitest** — entity-context provider; bubble record-answer states.
  - **playwright** — complaint detail → ask "why was this rejected / who / lead time" → assert assembler call + grounded answer.
- Re-verify against live stack.

**Phase 3 — Review** — `/code-review`, PR-CHECKLIST, then fan out PR/SF/stock_inquiry by filling field maps (each gets its own pytest + one playwright flow).

### Track B — Guide pipeline (parallel, front-loaded)

1. **Coverage map** — enumerate every FE route/screen; mark has-guide vs gap. Outline collections split: `operational` (both brains) vs `system-usage` (bubble only).
2. **Doc agent** — drafts a guide per gap, grounded in real component source (parse actual button labels / fields / wired flow). Annotate menu paths + deep links per `scripts/annotate_user_guides_routes.py`.
3. **Review agent** — verifies every label/route/flow in the draft against the real component; flags inventions. Then human review.
4. **Publish** — existing `scripts/sync_user_guides_outline.py push`. Verify via `documents.info` API, never the Outline UI (UI strips query-bearing links — see CLAUDE.md lesson).
5. **Order by demand** — author highest `/ai-assistant/wishlist` cluster first. Track unanswered-rate per cluster before/after.

## Enforcement / guardrails

- Assembler = JWT+RBAC route only. Add a test asserting `EXTERNAL_API_KEY` principal is **denied** (keeps it out of n8n's reach).
- `user_guides_read` from the external path must not surface `system-usage` collection docs.
- Anti-drift: any new operational capability lands in the shared MCP/backend layer, not a single brain.

## Open / deferred

- Stock_inquiry, PR, SF adapters — after complaint tracer proves the path.
- Minimal transition-hint table — only if guide prose proves too vague for "possible next states" (deferred; guide-first until evidence).
- WhatsApp operational parity tuning (bubble `enabled_tools` should cover the operational catalog n8n uses) — config check, low effort.

## Mandated complaint Q&A coverage (from UAC §2A — must close before tracer sign-off)

Six questions are the acceptance bar (see `UAC-…md` §2A). Three open gaps surfaced:

1. **Assembler shape missing `subject`/`about`** — "what is this complaint about?" (A1) needs the record subject + description in the response. Add to the shared shape + complaint field map.
2. **Approval lead-time ≠ SLA lead-time** — "how long did one person take to approve?" (A3) is `decided_at − submitted/assigned_at`, a separate clock from `sla.lead_time` (tier-based). Expose `approval.lead_time {elapsed, …}` distinctly so the two aren't conflated.
3. **A6 next-step routing (fusion) undecided** — "what should I do now?" needs assembler facts AND a `user_guides_read` call, but Q6's record-class branch forbids tool-routing while Q4b sends next-step to the guide. Pick: (i) record-class branch may make one guide call for next-step intent, or (ii) next-step is a third route (assembler-fetch → guide-read → render). Decide before A6 can pass.

Guide authoring prereq (Track B): the complaint guide must carry a **process-flow** section (all states + transitions — answers A5) and a **per-state "what do I do now"** section keyed by state, grounded in real FE button labels (answers A6).
