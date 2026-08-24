# Architecture - Bubble Record-Context + System Guides

**Companion to:** [`PLAN-bubble-record-context-and-guides.md`](./PLAN-bubble-record-context-and-guides.md) · [`UAC-bubble-record-context-and-guides.md`](./UAC-bubble-record-context-and-guides.md)

Diagrams are Mermaid - render in GitHub / any Mermaid viewer. `NEW` = added by this plan.

---

## 1. Two brains, one deterministic data layer

The anti-drift rule: brains **orchestrate**, they don't **own answers**. Both consume the same data layer. The assembler + system-usage guide are the only intentionally bubble-only additions (Q7 scope).

```mermaid
flowchart TB
    subgraph clients[Surfaces]
        WA[WhatsApp / Respond.io incoming]
        BUB[In-system bubble - AIAssistantBubble]
    end

    subgraph brains[Brains - orchestrate only]
        N8N[n8n WhatsApp brain<br/>deterministic pipeline<br/>AI = NLP parse only]
        FAPI[FastAPI brain<br/>AIAssistantChatService.respond<br/>6-iter agent loop]
    end

    subgraph data[Shared deterministic data layer]
        MCP[MCP tools - 28<br/>read-only CRM GETs]
        REF[references / lookup resolve<br/>text to UUID]
        RAG[RAG tool-select<br/>pgvector]
        GUIDE_OPS[user_guides_read<br/>operational collection]
        GUIDE_SYS[user_guides_read<br/>system-usage collection<br/>NEW - bubble only]
        ASM[record-context assembler<br/>NEW - JWT only, bubble only]
    end

    BE[(FastAPI /api/v1/*<br/>RBAC + SQL)]

    WA --> N8N
    BUB --> FAPI

    N8N --> MCP
    N8N --> REF
    N8N --> GUIDE_OPS

    FAPI --> MCP
    FAPI --> REF
    FAPI --> RAG
    FAPI --> GUIDE_OPS
    FAPI -.NEW.-> GUIDE_SYS
    FAPI -.NEW.-> ASM

    MCP --> BE
    REF --> BE
    ASM --> BE
    GUIDE_OPS --> OUT[(Outline)]
    GUIDE_SYS --> OUT

    classDef new fill:#1f6f43,stroke:#0d3,color:#fff
    class GUIDE_SYS,ASM new
```

**Scope firewall (Q7):** `ASM` and `GUIDE_SYS` have no path from `N8N`. The assembler is a JWT-only route - never an `EXTERNAL_API_KEY` MCP tool - so n8n/WhatsApp physically cannot reach it. UAC §3.6 asserts the EXTERNAL_API_KEY principal is denied.

**Conversation-state isolation (UAC §4.7):** the two brains keep per-conversation state in **separate stores** - they must never share a column.

```mermaid
flowchart LR
    subgraph wa[n8n WhatsApp]
        N[respond_contacts.session_vars - JSONB<br/>keys: flow / last_result_set / turns / merged<br/>keyed by respond_io_id<br/>writer: PUT /external/conversation-variables/:respond_io_id]
    end
    subgraph bb[Bubble]
        A[ai_assistant_conversations<br/>+ ai_assistant_messages.metadata_json<br/>keyed by user_id, conversation_id]
    end
    N -. NO BRIDGE .- A
```

`AIAssistantChatService` has zero reads/writes of `session_vars` (grep-clean). The assembler is read-only - it must not persist anything onto the contact. Mixing them would cross-contaminate the same person's WhatsApp and bubble state. Pinned by `test_bubble_path_never_writes_contact_session_vars`.

---

## 2. Bubble chat turn - the pre-route decision (the regression firewall)

Today every turn goes through the agent loop. The plan inserts one deterministic fork **before** the loop. The fork is the entire regression risk: it must divert **only** `entity + record-class` turns.

```mermaid
flowchart TD
    START([chat turn: message + page_snapshot]) --> RL[rate limit + store user msg]
    RL --> REF[resolve_references<br/>text to UUID]
    REF --> FORK{page_snapshot.entity present?<br/>NEW}

    FORK -- no --> LOOP
    FORK -- yes --> CLS{intent_is_record_class message?<br/>NEW - pure NLP}

    CLS -- no --> LOOP[Agent loop<br/>RAG select to function-call<br/>6 iters, 3 tool calls]
    CLS -- yes --> ASM[GET /assistant/record-context/:type/:id<br/>NEW - deterministic SQL]

    ASM --> RBAC{RBAC + found?}
    RBAC -- 403 --> DENY[degrade: no access]
    RBAC -- 404 --> NF[degrade: not found]
    RBAC -- ok --> INJ[inject facts into LLM context<br/>LLM classifies + renders prose<br/>NO tool calls]

    LOOP --> TOOLS[MCP tools / user_guides_read]
    TOOLS --> POST
    INJ --> POST[inject route links<br/>usage log + wishlist tag]
    DENY --> POST
    NF --> POST
    POST --> DONE([assistant reply])

    classDef new fill:#1f6f43,stroke:#0d3,color:#fff
    class FORK,CLS,ASM,INJ new
```

**Mapped to UAC §3:**

| Path through the fork | UAC row | Must hold |
|-----------------------|---------|-----------|
| entity ✓ + record-class ✓ → `ASM` | §3.1 | assembler answers, `tool_calls` empty |
| entity ✓ + record-class ✗ → `LOOP` | §3.2 | catalog question still hits MCP - **no theft** |
| entity ✓ + procedural → `LOOP` → `user_guides_read` | §3.3 | guide answers how-to |
| entity ✗ → `LOOP` | §3.4 | no assembler without an id |
| `ASM` → 403 / 404 | §3.5 / §3.7 | graceful degrade |

The two load-bearing edges are `FORK -- no` and `CLS -- no`: both route back to the **unchanged** agent loop. Sections 1 & 2 of the UAC live on those edges.

---

## 3. Record-context assembler - data sources (Q4a)

Pure SQL assembly, no AI. One shared response shape across all 4 entity types; a per-type field map fills it. Complaint is the tracer.

```mermaid
flowchart LR
    REQ[GET record-context<br/>:entity_type / :id<br/>JWT + RBAC] --> MAP[per-type field map<br/>complaint first]

    MAP --> ROW[(entity row<br/>approved_by / approved_at<br/>rejection_reason / approval_comments)]
    MAP --> AUD[(audit_logs<br/>state-set row<br/>old to new)]
    MAP --> SLA[(conversation_sla_tracking<br/>+ event_log<br/>tier / due / elapsed)]

    ROW --> BUNDLE
    AUD --> BUNDLE
    SLA --> BUNDLE[bundle<br/>current_state + approval<br/>+ sla lead_time + audit_trail<br/>all TZ = Asia/Kuala_Lumpur]

    BUNDLE --> RESP([structured JSON<br/>display_ref, no UUID in prose])
```

- `approval` is null when the entity has no approval gate; `sla` is null when no tracker.
- `lead_time` always returns `{elapsed, target, breached}` (Q8).
- All 4 entities (complaint, purchase_request, sponsorship_form, stock_inquiry) share `conversation_sla_tracking` discriminated by `source_entity_type` - the field map abstracts the per-type column names.

---

## 4. Guide pipeline (Track B - parallel)

```mermaid
flowchart LR
    COV[coverage map<br/>every FE route<br/>has-guide vs gap] --> DEMAND{order by demand<br/>wishlist clusters}
    DEMAND --> DOC[doc agent<br/>grounded in real<br/>component source]
    DOC --> REVA[review agent<br/>verify every label/route<br/>flag inventions]
    REVA --> HUMAN[human review]
    HUMAN --> PUSH[sync_user_guides_outline push]
    PUSH --> VERIFY[verify via documents.info API<br/>NOT Outline UI]
    VERIFY --> COLL{collection split}
    COLL --> OPS[operational<br/>both brains]
    COLL --> SYS[system-usage<br/>bubble only]
```

Two gates, no auto-publish (Q5 review): doc agent → review agent → human → Outline. Verify links via API, never the Outline UI (it strips query-bearing links - CLAUDE.md lesson).

---

## Deliverable map

| Artifact | File |
|----------|------|
| Design + decisions | `PLAN-bubble-record-context-and-guides.md` |
| Acceptance criteria | `UAC-bubble-record-context-and-guides.md` |
| This architecture | `ARCH-bubble-record-context-and-guides.md` |
| Pre-route regression guard (dormant test-first) | `sorento_crm_backend/tests/test_ai_assistant_record_context_preroute.py` |
