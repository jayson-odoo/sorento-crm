# PLAN: Scheduled SLA escalation — backend-owned logging + no raw SQL in n8n

Status: Implemented (2026-06-06) — backend + tests done; n8n JSON at
`docs/n8n/sla-scheduled-escalation.workflow.json`, awaiting manual import.

## Problem

The n8n "scheduled policy checker" workflow escalates breached conversation SLA rows every
minute, but it is fragile:

1. **Six raw `postgres` nodes** query `conversation_sla_tracking`, `sla_policies`,
   `sla_policy_tiers`, `respond_contacts` directly. Schema drift silently breaks them; they
   also bypass `conversation_tracking_scope()` (the breach queries only survive because they
   filter `current_tier = 1|2`, not because they understand the form-SLA discriminator).
2. **Two event-log POST nodes** (`/event-logs`) duplicate what the backend already writes:
   `escalate_tracking` creates the `escalation` event log itself → every escalation currently
   produces **two** escalation logs.
3. **Two parallel branches** (tier 1→2, tier 2→3) duplicate the whole pipeline because n8n
   owns the tier math. The escalate API already supports signal-only mode (omit
   `current_tier`) where the server owns tier math.

## Decisions

- Backend is the **sole owner** of escalation event logs. n8n never POSTs `/event-logs`.
- n8n never runs SQL. New integration endpoint returns the breach work-list with everything
  downstream nodes need (`phone_number`, `respond_io_id`, `policy_id`, ...).
- One n8n branch, signal-only escalation. Comment wording ("executive" vs "manager") is
  templated from `from_tier` in the escalate response.
- Tier-3 breached rows are **excluded** from the work-list (nothing to escalate to; reminder
  flows are a separate concern).

## Backend changes (`sorento_crm_backend`)

1. **New** `GET /api/v1/sla-management/conversation-sla-tracking/integration/due-escalations`
   - Filter: `conversation_tracking_scope()` AND `is_resolved = false` AND
     `current_tier IN (1, 2)` AND **split-clock breach** (the response clock stops on
     response, so escalation must not fire on a stopped clock — the old SQL escalated
     responded rows at the response deadline):
     - not responded → `due_at < now`
     - responded → `due_at_resolution < now` (never before, even if `due_at` passed)
   - Response: `{ status, count, items: [...] }`, each item:
     `tracking_id`, `respond_contact_id` (internal), `policy_id`, `current_tier`,
     `breach_type` ("response" | "resolution"), `is_responded`, `due_at`,
     `due_at_resolution` (ISO UTC), `message_id`, `phone_number`, `respond_io_id`,
     `assigned_to_id`, `assigned_to_respond_user_id`, `source_entity_type`, `team_set_code`.
2. **`escalation_reason` optional** on `ConversationSLAEscalateRequest`. When omitted the
   service defaults to `"Auto-escalation: tier {from_tier} response due time breached"` —
   n8n in signal-only mode doesn't know the tier before the call.
3. **`escalated_at` added to escalate response** (ISO UTC). Replaces the n8n comment node's
   reference to the now-deleted event-log node's `created_at`.
4. **Event-log assignee fix**: the escalation event log was written inside
   `escalate_tracking` *before* the route assigned the new tier assignee, so it recorded the
   OLD assignee. Route now passes the resolved assignee into `escalate_tracking`, which sets
   it pre-flush — the log records the NEW assignee, and the route's post-hoc
   `setattr` + second commit is gone.

## n8n changes (manual import by user; n8n is not in the repo)

Single branch: Schedule (1 min) → `GET due-escalations` → Split Out `items` →
`POST integration/escalate` (signal-only: no `current_tier`, no `escalation_reason`) →
findcontact sub-workflow (input: `phone_number` from work-list item) → If assignee changed →
Respond.io assign + comment. Comment timestamps from `escalated_at` / `due_at` /
`due_at_resolution`; role wording via `from_tier === 1 ? 'executive' : 'manager'`.

Removed nodes: 6× postgres SQL, 2× event-log POST, duplicate tier branch.

## Phases

- Phase 1 (FE prototype): N/A — integration API only, no UI.
- Phase 2: backend endpoint + fixes + pytest. n8n JSON delivered in chat for manual import.
- Phase 3: /code-review before PR.
