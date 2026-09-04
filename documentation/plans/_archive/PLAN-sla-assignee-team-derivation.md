# PLAN: SLA assignee-driven team/agent derivation

**Status:** Implemented on branch `feat/sla-assignee-team-derivation` - pending review/PR. n8n escalate-flow switch (signal-only) still to do on n8n side.

> **Superseded in part (2026-08-18):** the tier-1 membership invariant described here
> (decision 3: at most ONE tier-1-linked team per user) has been relaxed to at most one
> per TEAM SET, and derivation no longer returns None on multi-team membership - it
> disambiguates via the tracking's `team_set_code` with a logged deterministic fallback.
> See `PLAN-tier1-teamset-invariant.md` for the current contract.
**Date:** 2026-06-05
**Owner:** Jayson

## Problem

`ConversationSLATracking` carries `agent_id` + `team_set_code`, which drive the escalation
chain (`get_escalation_assignee_for_tier()` → `AgentTeam(agent_id, code, tier+1)` → round-robin).
When Respond.io auto-assign misroutes a conversation (e.g. AI classifies as "order" but it's
"general"), a human reassigns the conversation in Respond.io. That reassignment reaches the CRM
via `/external/conversation-assignee` or `/sla/tracking/{id}/sync-assignee`, but those paths
update **only** `assigned_to` / `assigned_to_id`. The stale `agent_id` / `team_set_code` then
cause escalation to fire into the **wrong team's** next tier.

## Solution overview

Derive `agent_id`, `team_set_code`, and `current_tier` from the new assignee's team membership
whenever the assignee changes through the Respond-facing paths. To make derivation unambiguous,
enforce a tier-1 membership uniqueness invariant.

## Decisions (locked during grilling)

| # | Decision |
|---|----------|
| 1 | Cross-agent correction is allowed - reverse-lookup is **global** across all agents' tier-1 teams. Misroutes regularly cross agents (order_enquiries vs general_enquiries). |
| 2 | `policy_id` is **never touched** by derivation. All Sorento agents share one SLA policy today. Multi-policy is an explicit non-goal; revisit if it lands. |
| 3 | **Invariant (TEAM-level, revised after config audit):** a user may belong to at most ONE team that is linked at tier 1 under any agent. The same team linked at tier 1 under MANY agents is legal and common (shared executive pools, e.g. 'Customer Service' under 8 agents) - discovered in prod-like config during implementation; the original `(agent_id, code)`-level invariant would have flagged nearly every exec. Enforced app-level at both mutation points: team-member add and tier-1 `AgentTeam` link create/update. Hard 422 reject. |
| 3a | Team reused at tier 1 in one agent and tier 2/3 elsewhere: **warn, don't block** (does not break derivation - lookup only scans tier=1 links). |
| 3b | Shared-pool ambiguity resolution: among the user's team's tier-1 links, prefer the tracking's **current agent** (agent stays put, only team set flips); else pick the deterministic first link (order by code, then agent_id) - tier-2/3 config is expected to be equivalent across those agents (Jayson's call). |
| 3c | **Scope: conversation trackings only.** Form SLA trackings (`source_entity_type` in `FORM_SLA_TYPES`: stock_inquiry, purchase_request, sponsorship_form, complaint, ticket) own their routing via `FormSLAConfig` stages - assignee changes never flip their agent/team. Guard in `apply_assignee_team_derivation` + backfill filter. |
| 4 | Tier mirrors the assignee's rank in the owning team (3-step algorithm below). Assignment can escalate (tier-1 tracking → tier-2 manager ⇒ tier 2) and de-escalate (tier-3 → tier-2 manager ⇒ tier 2). Multi-tier match picks the **lowest** matched tier. |
| 5 | Derivation fires in `set_assignee_for_tracking()` and `sync_assignee_from_respond()` only. `admin_test_override_tracking()` excluded (explicit operator overrides). Escalation/create/form-SLA flows excluded (forward direction, consistent by construction). Unassign (empty respond_user_id) is a no-op for routing fields. |
| 6 | On team flip, advance `AgentTeamRoundRobinCursor` for the new `(agent_id, team_id)`: `last_assigned_user_id = new assignee` (upsert). Round-robin continues fairly after the manual pick. |
| 7 | Config violations are **auto-amended** by script (system not live yet): keep the user's most recent tier-1-linked team membership (`TeamMember.created_at` latest = latest intent), remove older ones, log every removal. *Keep-rule is cheap to flip if wrong.* Dry run against current config: 2 violating users (both test users), 2 removals. |
| 8 | Open-tracking backfill: re-derive from current `assigned_to_id` via tier-1 lookup; update routing fields only where mismatched (idempotent JOIN-based). No tier reset, no clock restart, no event-log rows in backfill. Tier-2/3 assignees skipped. |
| 9 | Every derivation-caused team or tier change writes a `ConversationSLAEventLog` row, `event_type='reassignment'`, including team-only changes at the same tier (`from_tier = to_tier`). Reason string carries the source path ("via conversation-assignee" / "via sync-assignee") and team change ("team_set: X → Y"). Full human-actor attribution is out of scope. |

## Derivation algorithm

`derive_team_for_assignee(user_id) → (agent_id, team_set_code, tier) | None`

1. **Tier-1 lookup (global, team-level).** User is a member of exactly one tier-1-linked
   team (unique by invariant). Among that team's tier-1 `(agent_id, code)` links: prefer
   the tracking's current agent, else the deterministic first (code, then agent_id) →
   return that `(agent_id, code, 1)`.
2. **Tier-2/3 lookup (scoped).** Not tier-1 anywhere, but member of the tier-2 or tier-3
   team of the tracking's **current** `(agent_id, team_set_code)` → return current agent/team
   with the matched tier (lowest if both).
3. **No match.** Unknown user, or manager of some other team set (ambiguous) → `None`;
   caller updates assignee fields only.

Applied by the caller when result ≠ current state:

- Update `agent_id`, `team_set_code`, `current_tier`.
- If tier **or** team changed: `current_tier_started_at = now`, recalc `due_at` /
  `due_at_resolution` from the (shared) policy's matched-tier hours; write `reassignment`
  event-log row.
- If team flipped: upsert round-robin cursor for new `(agent_id, team_id)` to the assignee.

## Implementation items

### Backend (`sorento_crm_backend/`)

1. `app/services/sla_service.py` - `derive_team_for_assignee()` + apply-derivation helper;
   call from `set_assignee_for_tracking()` and `sync_assignee_from_respond()`.
2. `app/services/user_service.py` (TeamService / AccessAgentService) - invariant validation:
 - add team member → reject if team is tier-1-linked and user already in another
     tier-1-linked `(agent, code)`. Error message names the conflicting team + agent.
 - create/update `AgentTeam` at tier 1 → reject if any member of the linked team would
     violate the invariant.
 - warn-only path for team reused across tiers (log warning, allow).
3. New `event_type` value `reassignment` in `ConversationSLAEventLog` (Text column - no
   migration needed; confirm no enum/check constraint).
4. `scripts/amend_tier1_membership_violations.py` - auto-fix: keep latest membership,
   delete older, print removals. Idempotent. **Retired (deleted) 2026-08-18**: it enforced
   the superseded global per-user invariant and a rerun would have deleted now-legal
   cross-team-set memberships (see `PLAN-tier1-teamset-invariant.md`).
5. `scripts/backfill_tracking_team_from_assignee.py` - open trackings, JOIN-based
   set-where-mismatch, routing fields only. Idempotent.

### Frontend (`sorento_crm_frontend/`)

6. SLA detail event-log: render `reassignment` ("Reassigned - tier 2 → 1, team order →
   general"). One new case.
7. Config screens: no dropdown filtering - invariant violations surface as the standard
   `extractApiError` toast.

### Escalate endpoint - server-owned tier progression

8. `/integration/escalate`: make `current_tier` **optional**. n8n sends a bare escalation
   signal; the server owns tier math. Once reassignment can change tier server-side, any
   tier cached in n8n goes stale - so n8n must not do tier arithmetic at all.
 - `current_tier` omitted → target = `tracking.current_tier + 1`.
 - Already at tier 3 → **no escalation**, return 200 with `escalated: false`,
     `from_tier = to_tier = 3`, message "already at max tier" (n8n branches on the flag,
     e.g. keep reminding).
 - `current_tier` provided → legacy explicit-target behavior unchanged (validation,
     multi-step jumps) for backward compatibility during n8n transition.
 - Response gains `escalated`, `from_tier`, `to_tier` for n8n message templating
     ("Escalated from tier {from} to {to}: {assignee}").

### Integration (n8n / Respond.io)

9. Update n8n escalation flow: drop tier tracking/arithmetic, call escalate with no
   `current_tier`, template messages from `from_tier`/`to_tier`/`escalated` in the response.

## Tests (Phase 2, not deferred)

### pytest

- Derivation matrix: tier-1 flip (same agent / cross agent), tier-2 scoped match,
  tier-3 scoped match, lowest-tier on multi-match, no-match no-op, unassign no-op.
- Side effects: clock restart + due recalcs on tier/team change; no clock change when
  nothing changed; event-log row content (incl. team-only same-tier case); cursor upsert
  on team flip.
- Invariant: member-add rejection, tier-1 link rejection, warn-not-block on cross-tier
  team reuse, error message names conflict.
- Endpoints: `/external/conversation-assignee` and `sync-assignee` happy path + derivation
  + auth denial + validation error.
- Escalate: omitted `current_tier` → +1; at tier 3 → 200 `escalated: false`; explicit
  target unchanged; response carries `escalated`/`from_tier`/`to_tier`.
- Scripts: amend keeps latest membership; backfill idempotent (second run = zero changes).

### vitest

- Event-log component: `reassignment` rendering case.

### Playwright

- None - no new user flow; config error uses existing form surfaces.

## Rollout order (strict)

1. Amend script → run on prod data (auto-fix, logged).
2. Deploy invariant enforcement (config now clean).
3. Deploy derivation + cursor advance + event type + escalate auto-increment (+ FE rendering).
4. Run tracking backfill once.
5. n8n: switch escalate calls to signal-only (no `current_tier`), template messages from
   response `from_tier`/`to_tier`/`escalated`.

## Non-goals

- Multi-policy support in derivation (`policy_id` untouched).
- Human-actor attribution on external reassignments.
- Preemptive FE filtering of user pickers by tier-1 eligibility.
- DB-level constraint for the invariant (cross-table; app-level only).
