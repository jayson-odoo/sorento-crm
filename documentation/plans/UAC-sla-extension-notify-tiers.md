# UAC - Per-tier "notify on extension" for SLA deadline extensions

**Status:** authoring → build → self-verify (FE+BE) → handoff

## Problem
When an SLA deadline is extended, only **tier current+1** (the immediate parent team)
is notified - the grandparent (e.g. project director, tier 3) never is. The tier chain
is the **agent team config** (`AgentTeam` rows: agent_id, tier 1/2/3, team_set_code,
team_id), NOT `teams.parent_team_id`.

## Decision
Per-tier control: add `notify_on_extension` (bool) to `AgentTeam`. On extend, notify
EVERY higher tier (current+1 … 3) whose row has `notify_on_extension = true`. Admin
toggles it per tier in the access-agent admin UI. **Default true** (so the grandparent
is notified out of the box; admins untick to silence a tier).

## Acceptance criteria

**N1 - Column + default.** `agent_teams.notify_on_extension` bool, server_default true.
Existing rows backfill to true (preserve+extend current notify). *BE migration.*

**N2 - Multi-tier fan-up.** Extending a tier-1 form SLA notifies the tier-2 team's
next assignee AND the tier-3 team's next assignee (both flags true). Each is a distinct
"(deadline extended)" notification. *BE.*

**N3 - Per-tier opt-out.** With tier-3 `notify_on_extension=false`, the same extend
notifies tier 2 only, NOT tier 3. *BE.*

**N4 - No mutation.** Notify PEEKS the round-robin cursor (never advances it); tier /
clock / RR state unchanged (same as today). *BE.*

**N5 - Top tier.** Extending at tier 3 notifies nobody above (no tier 4). *BE.*

**N6 - Dedup.** If the same user is the next assignee of two notified tiers, they get
one notification, not two. *BE.*

**N7 - Conversation SLA parity.** Conversation-SLA extend uses the same per-tier flag
loop (not just +1). *BE.*

**N8 - Admin reads the flag.** `GET /access-agents/{id}/teams` returns
`notify_on_extension` per tier-team row. *BE.*

**N9 - Admin sets the flag.** `PUT /access-agents/{id}/teams` persists
`notify_on_extension` per assignment. *BE.*

**N10 - UI toggle (edit).** The access-agent edit form shows a "Notify on extension"
switch on each tier-team row; saving persists it. *FE.*

**N11 - UI shows state (detail).** The access-agent detail view shows the
notify-on-extension state per tier-team row. *FE.*

## Files
- Model: `app/models/access.py` AgentTeam (+ migration).
- Schema: `app/schemas/user.py` AgentTeamAssignment.
- Service: `app/services/user_service.py` `list_agent_teams_with_round_robin_state`,
  `set_agent_teams`, new `get_tier_team_and_notify`; `app/services/sla_service.py`
  `_notify_next_tier_deadline_extended` (loop).
- Route: `app/api/v1/user_management/access_agents.py` PUT payload.
- FE: `access-agents/services/accessAgentService.ts` (type),
  `components/AccessAgentForm.tsx` (toggle), `components/AccessAgentDetail.tsx` (badge).

## Verification log (self-verify complete)

Method: pytest + live browser on the complaint access agent (73955ea1).

| AC | Result | Evidence |
|----|--------|----------|
| N1 | ✅ | migration 249 applied; all existing agent_teams rows backfilled notify_on_extension=true |
| N2 | ✅ | pytest test_notify_fans_up_to_grandparent: tier-1 extend notifies tier 2 + tier 3 |
| N3 | ✅ | pytest test_notify_per_tier_optout (tier3 off → tier2 only); + live: complaint tier3 toggled off persisted |
| N4 | ✅ | pytest: peeks RR cursor, get_next_assignee never called |
| N5 | ✅ | pytest test_notify_skipped_at_top_tier (tier 3 extend → nobody above) |
| N6 | ✅ | pytest test_notify_dedups_shared_member |
| N7 | ✅ | conversation + form rows share the loop; both pytest paths green |
| N8 | ✅ | edit modal shows 4 toggles (tier2+3 of both team-sets), states from DB |
| N9 | ✅ | toggled complaint tier3 off + Update → DB notify_on_extension=false (then restored to true) |
| N10 | ✅ | browser: 4 "Notify on extension" switches render in the edit modal (tier 2/3 only) |
| N11 | ✅ | browser: detail view shows "Notify on extension" badge per tier 2/3 row |
