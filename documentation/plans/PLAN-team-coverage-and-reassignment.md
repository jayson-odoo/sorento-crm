# PLAN - Team tasks, takeover/reassign, coverage subscriptions, team hierarchy & RR toggle

**Status:** Implemented + verified 2026-06-22. Migrations 238/239/240 applied. 35 pytest + 26 vitest + 32 live-API ACs (real postgres) + Playwright on every FE surface. Added `GET /visible-users` (scope-B picker source) beyond original plan.

Covers: "My Team Tasks" view, Takeover, Reassign, notification-subscription (coverage),
team hierarchy (parent teams), and per-member round-robin opt-out.

---

## Background (existing model)

- `conversation_sla_tracking`: `assigned_to_id` (FK users), `assigned_to` (Respond user id str),
  `current_tier`, `team_set_code`, `agent_id` (FK access_agents), `due_at`, `is_resolved`,
  `source_entity_type` (NULL/`conversation` for conversation SLA; in `FORM_SLA_TYPES` for form SLA).
- `conversation_sla_event_log`: has `event_type='reassignment'` already; `trigger`, `triggered_by_id`,
  `assigned_to_id`, `from_tier`, `to_tier`, `reason`.
- Teams: `teams`, `team_members` (user_id, team_id, sort_order; unique per pair),
  `agent_teams` (agent_id, code=team_set, team_id, tier 1/2/3), `agent_team_round_robin_cursors`.
- `AccessAgentService.get_next_assignee(agent_id, team_id)` - round-robin pick.
- `RespondClient.set_conversation_assignee(identifier, assignee_id)` - **exists, never called**;
  POSTs `/v2/contact/{id}/conversation/assignee`, payload `{"assigneeId": ...}`, `""` to unassign.
- `User.respond_user_id` maps CRM user → Respond agent.
- My Pending widget: `MyPendingSLAWidget.tsx` → `GET /sla-management/conversation-sla-tracking/my-pending`
  → `ConversationSLATrackingService.list_my_pending(user_id)` (filters `assigned_to_id == me`,
  `is_resolved == false`; includes form SLA rows). Inline actions today: Escalate, Resolve.

---

## A. Team hierarchy

**Decision:** add self-FK `teams.parent_team_id` (nullable). Configured in team create/edit UI
(a "Parent team" dropdown). Full-recursive descendants (parent → child → grandchild → any depth),
membership-driven - being a member of a parent team IS the manager grant (no separate role).

- Migration: add `parent_team_id` nullable FK `teams.id` (`ondelete SET NULL`), index it.
- Helper: recursive CTE `descendant_team_ids(team_ids)` → all teams at-or-below a set.
- FE: parent-team select in the team form; guard against cycles (can't pick self or a descendant).

## B. "My Team Tasks" view

**Visibility rule:**
```
myTeams      = teams where current_user is a member
visibleTeams = myTeams ∪ descendants(myTeams)   # recursive CTE
teamTasks    = conversation_sla_tracking rows, is_resolved=false,
               assigned_to_id ∈ members(visibleTeams), assigned_to_id != me
```
Includes both conversation and form SLA rows (whole pending workload). Excludes my own (those live
in My Pending).

**Surface (decision C):**
- **Home widget** gets a toggle `[My Pending | My Team]`. Team mode shows **assignee per row** +
  Takeover/Reassign actions for quick work, plus a "View all" link.
- **Dedicated page** under SLA management: full `DataGrid` (per ARCHITECTURE-RULES: fixed layout,
  resizable, explicit sizes, truncate+title), assignee column, **filters = assignee + team**,
  pagination, Takeover/Reassign per row.

**Endpoints (new):**
- `GET /sla-management/conversation-sla-tracking/team-pending?assignee=&team=&page=&limit=` - 
  visible-team tasks, optional assignee/team filter, soonest-due first. Returns assignee name +
  team label per row (resolve UUIDs → human-readable; no UUIDs in UI).
- Service `list_team_pending(user_id, filters)` on `ConversationSLATrackingService`.

## C. Takeover (grab a visible task for myself)

Only on Team Tasks (not My Pending - already mine). **Permission = visibility** (anyone who can see
the task can take it; no RBAC slug).

**Mutation:**
- `assigned_to_id` → me; `assigned_to` → my `respond_user_id`.
- **Re-derive team from the team-queue context (decision B).** Takeover is team-scoped: the row was
  shown under a specific team queue; set `team_set_code` / `agent_id` / `current_tier` from **that
  team's `agent_teams` link** (the team I'm taking it on behalf of). Future escalation then follows
  my team's chain. The FE passes the team context (team_id) with the takeover call.
- **Do NOT reset the clock** - `due_at` / `due_at_resolution` / `current_tier_started_at` unchanged.
  (Customer already waiting; covering shouldn't move the deadline.) → this needs a NEW code path,
  NOT `apply_assignee_team_derivation` (which resets the clock).
- Event log: `event_type='reassignment'`, `trigger='manual'`, `triggered_by_id=me`,
  `assigned_to_id=me`, `reason='takeover'`.
- Advance the target team's RR cursor to me (so auto-assign continues fairly after).

**Endpoint:** `POST /sla-management/conversation-sla-tracking/{id}/takeover` body `{ team_id }`.

## D. Reassign (hand a task to a chosen person) - renamed from "defer"

On **both** My Pending and My Team Tasks.

**Picker scope (B):** choose from users **I can see** (members of visibleTeams).

**Mutation (decision ii - keep original team):**
- `assigned_to_id` → target; `assigned_to` → target.`respond_user_id`.
- **Keep** original `team_set_code` / `current_tier` / `agent_id` (hand the work item to a person,
  don't re-home the queue → avoids multi-team derivation ambiguity).
- **Do NOT reset the clock.**
- Event log `reassignment`, `triggered_by_id=me`, `assigned_to_id=target`, `reason='reassign'`.

**Endpoint:** `POST /sla-management/conversation-sla-tracking/{id}/reassign` body `{ user_id }`.

## E. Respond.io sync (takeover & reassign)

- After CRM reassign, call `RespondClient.for_identifier(db, contact).set_conversation_assignee(
  contact_identifier, new_assignee.respond_user_id)`.
- **Best-effort** (post-commit side-effect rule): try/catch, **write `integration_log` on success
  AND failure**, never 500 the action if the push fails. `integration_log.business_id` = tracking id
  (UUID column).
- **Target has no `respond_user_id`:** proceed with CRM reassign, **skip** the push, log a warning.
  Don't block.
- **Form-SLA rows** (source_entity_type in FORM_SLA_TYPES): takeover/reassign apply, but **skip the
  Respond push** (no Respond conversation to reassign).

## F. Notifications (takeover & reassign)

Reuse `create_with_channel_preferences` + `notify_*_on_assignment` toggles; in-app always.
- **New assignee:** always notify ("You've been assigned…").
- **Old assignee:** notify **only when actor != old assignee** (someone moved your task). Self-reassign
  → no self-notify.

## G. Coverage subscriptions (forward-looking delegation)

Subscribe to a colleague so their FUTURE assignments/escalations also ping me. Separate from takeover
(which grabs an existing task). Loop: RR still assigns to the absent person (no leave flag - not HRMS),
subscription fans the notice to the cover, cover hits Takeover.

**Model - new table `notification_subscriptions`:**
`id, subscriber_id (FK users), target_user_id (FK users), is_active bool, expires_at nullable,
created_at`. Unique active (subscriber, target). One subscriber → many targets; one target → many
subscribers.

**Event scope (A):** only the target's **SLA assignment + escalation** notifications fan out - NOT
the target's unrelated account notifications. Applies to both conversation and form SLA
assignment/escalation.

**Subscriber channels:** in-app always; email/WhatsApp gated by the **subscriber's own**
`notify_email_on_{assignment,escalation}` / `notify_whatsapp_on_{assignment,escalation}` toggles.
Message labeled "(covering for <Name>)".

**Who can subscribe to whom:** scope-B (users in visibleTeams).

**Fan-out hook:** at the central SLA assignment/escalation notify path, after notifying the target,
look up active non-expired subscriptions for that target and emit a copy per subscriber (deduped - if
subscriber == the actual assignee/actor, don't double-send). Guard against self-subscription.

**Management UI:** "Coverage" section in `account/notifications` (the page already open:
`other-notifications.tsx`) - list "users I'm covering for", add via scope-B picker, remove, optional
end-date (`expires_at`). Quick **Subscribe** action from a teammate's row in My Team Tasks.

**Expiry:** optional `expires_at`; manual unsubscribe always available. Daily check deactivates
past-expiry rows.

## H. Round-robin per-member opt-out

**Decision:** add `team_members.include_in_round_robin` bool, default `true` (per-team, NOT on users - 
multi-team member can be RR-eligible in one team, excluded in another).

- `get_next_assignee` filters to members where `include_in_round_robin = true`.
- Governs **auto round-robin only.** Manual Takeover/Reassign can still target an excluded member;
  they still appear in Team Tasks (excluded from auto-distribution ≠ invisible).
- Edge: all members unchecked → no eligible assignee → same error path as empty team.
- UI: toggle column in the Team Members page.

---

## Migrations

1. `teams.parent_team_id` nullable self-FK + index.
2. `team_members.include_in_round_robin` bool default true, server_default true (backfill existing → true).
3. `notification_subscriptions` table.

## Tests

**pytest:**
- Team-pending query: returns peers + child-team tasks recursively; excludes self + resolved;
  assignee/team filters; grandchild depth.
- Takeover: assignee→me, team re-derived from passed team_id, clock unchanged, `reassignment` log,
  RR cursor advanced; conversation row pushes to Respond (mock) + logs integration_log on success &
  failure; form row skips push; taker without respond_user_id skips push + warns.
- Reassign: assignee→target, team/tier/clock unchanged, log written; scope-B picker enforced.
- Notifications: new assignee always; old assignee only when actor≠them; self-reassign no self-notify.
- Subscription fan-out: target's assignment/escalation copies to active subscribers, gated by
  subscriber's own channel toggles; expired/inactive skipped; no double-send when subscriber==assignee;
  self-subscription rejected; form + conversation both covered.
- RR opt-out: get_next_assignee skips unchecked members; all-unchecked → error; manual assign to an
  excluded member still works.

**vitest:** widget My Pending/My Team toggle; assignee column; Takeover/Reassign buttons (loading/
error/success); Reassign picker (scope-B); Team Tasks filters; Coverage section add/remove; RR toggle
in Team Members.

**playwright:** sidebar → Team Tasks page → filter by assignee → Takeover → row moves to My Pending →
network asserts `/takeover` + Respond push. Reassign flow. Subscribe from Team Tasks → coverage row
appears in notification settings.

## Open implementation notes

- Takeover's team-context re-derive is a NEW path (clock-preserving) - do not reuse
  `apply_assignee_team_derivation` (resets clock + bails on multi-team tier-1).
- Cycle guard on `parent_team_id` (no self/descendant as parent).
- Reuse `descendant_team_ids` CTE for both Team Tasks visibility and coverage picker scope.
