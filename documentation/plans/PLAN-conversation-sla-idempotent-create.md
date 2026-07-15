# PLAN — Conversation SLA: idempotent create + conversation-row scoping

**Status:** Merged to main 2026-06-06 (PR #4, commit efe20ad). Pending: n8n-side node removal (see n8n section). (Grill session 2026-06-06; supersedes the abandoned multi-active/source-entity-key design.)

## Context / problem

n8n's routing sub-workflow (`conversation-sla-tracking-create` node) hit:

```json
{ "message": "An active (unresolved) SLA tracking already exists for this contact (tracking id: c6ed7939-...). Resolve it before creating a new one.", "code": "CONFLICT" }
```

Initial hypothesis was that one contact now needs multiple active conversation trackings
(complaint + stock inquiry + purchase request + sponsorship form). Grilling against the
codebase and the real n8n flow killed that: those per-entity SLAs are **form SLA** rows
(`form_sla_service`, `FORM_SLA_TYPES`), already multi-active. Conversation SLA is a
different layer and its singleton-per-contact invariant is **correct**.

## The model (now explicit, binding)

| Layer | Created by | Cardinality | Lifecycle |
|---|---|---|---|
| Conversation SLA | n8n only | max **1 open per contact** | mirrors Respond.io: unresolved = conversation open, resolved = conversation closed |
| Form SLA | system only (`emit_form_event`) | always created, never merged; N active per contact fine | per-entity stage chains (`FormSLAConfig`) |

- n8n events (create / respond / resolve / escalate) touch conversation SLA **only**.
- CRM-side chat windows (complaint, stock inquiry, purchase request, sponsorship form)
  do not trigger n8n and must never respond/resolve conversation SLA.
- Conversation rows have `source_entity_type IS NULL OR NOT IN FORM_SLA_TYPES`;
  form rows have `source_entity_type IN FORM_SLA_TYPES`. (Same predicate as the
  listing filter at `sla_service.py:445-452`.)

## Decisions (from grill)

1. **No multi-active conversation trackings. No `conversation_key`. No `tracking_kind`
   column. No source-entity tagging of conversation rows.** All rejected.
2. Active conversation row exists at create → **idempotent 200**, return existing
   tracking (same response shape n8n already consumes: `id`, `initiated_at`, `due_at`,
   `due_at_resolution`, `assigned_to`), plus `already_active: true`.
3. On idempotent hit: refresh `message_id` to the new inbound message (feeds inbox
   deep-links in escalation comments). Agent/team/assignee/tier clocks untouched.
4. Resolved row exists at create → **overwrite-in-place stays** (current behavior).
   History = event logs, which survive overwrite (FK by tracking id, only scalar
   fields reset).
5. Existence check (and every contact-keyed read) must scope to conversation rows —
   today an active **form** row falsely 409s n8n's create and can leak a form row's
   assignee to thread-level endpoints.

## Backend changes (`sorento_crm_backend`)

1. **Shared predicate helper** in `sla_service.py` (used everywhere below):
   `source_entity_type IS NULL OR source_entity_type NOT IN FORM_SLA_TYPES`.
   Refactor the inline copy at `:445-452` (and `:2410`) onto it.
2. **`create_tracking` (`sla_service.py:1669`)**
   - Scope `existing` query with the helper.
   - Active hit → set `message_id` from payload (if sent), commit, return existing
     with `already_active` marker (no 409). **No event log written.**
   - Resolved hit → overwrite-in-place (unchanged) + write `assign` event log.
   - No hit → insert (unchanged) + write `assign` event log.
   - **Backend now owns the `assign` event log** (was n8n's
     `conversation-sla-event-tracking-create` POST): `event_type="assign"`,
     `from_tier=1`, `to_tier=1`, `assigned_to` from the new tracking, reason
     `"New Assignee <name>"` resolved from the assignee user. Written only when a
     conversation actually starts (insert / overwrite), never on idempotent hit —
     that is what kills the duplicate-log problem at the source.
3. **Route `POST /conversation-sla-tracking/integration` (`sla_tracking.py:572`)**
   - `is_update` pre-check: same scoping.
   - Response: include `already_active: true|false`; keep 200/201 semantics n8n
     tolerates. Integration log channel: `sla_tracking_idempotent_hit` on hit.
4. **Scope contact-keyed reads** with the helper:
   - `get_tracking_by_contact_phone` (`sla_service.py:~1110`) → used by
     `external/next_assignee.py:297`, `external/conversation_assignee.py:58`
   - `get_tracking_by_contact` (`sla_service.py:~803`) → used by
     `external/conversation_sla_tracking.py:25`
   - `get_tracking_by_contact_and_policy` (`sla_service.py:~915`) → used by
     escalate (`sla_tracking.py:401`) and `sla_service.py:1031`
5. No migration. No FE change required (listing filter already excludes form rows;
   event-log table unchanged).

## n8n-side change (manual, after deploy)

In the routing sub-workflow:

1. **Remove the `conversation-sla-event-tracking-create` node** — backend writes the
   `assign` event log itself on create/overwrite (and skips it on idempotent hit).
2. **Repoint `Code in JavaScript1`**: it reads
   `$('conversation-sla-event-tracking-create').first().json.assigned_to` — change to
   `$('conversation-sla-tracking-create').first().json.assigned_to` (same field on the
   create response).
3. SLA comment node keeps using the returned (existing) deadlines — no change.

## Tests (pytest, same PR)

- create with active conversation row → 200, same tracking id, `already_active`,
  `message_id` refreshed, clocks/assignee untouched, no new row, **no new event log**
- create with active **form** row only → creates new conversation row (no false 409)
- create with resolved conversation row → overwrite-in-place, prior event logs
  preserved + new `assign` log appended
- create with no rows → insert + `assign` event log written (from_tier=to_tier=1,
  assignee fields populated)
- `get_tracking_by_contact_phone` ignores form rows (assignee endpoints)
- escalate by contact+policy ignores form rows

## Out of scope

- Form SLA behavior (untouched)
- Respond.io close ↔ resolve sync direction (already handled by existing n8n flows)
- Multi-active conversation SLA (explicitly rejected)
