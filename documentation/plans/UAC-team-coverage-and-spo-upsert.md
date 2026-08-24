# User Acceptance Criteria

**Scope:** PLAN-spo-import-upsert + PLAN-team-coverage-and-reassignment
**Status:** PASSED 2026-06-22. All ACs verified - pytest (42) + vitest (26) + live-API on real postgres (32 ACs) + Playwright (FE surfaces via sidebar).

Format: Given / When / Then. Each AC is independently verifiable. "SLA task" = a row in
`conversation_sla_tracking` (conversation or form).

---

## 1. SPO import upsert

### AC-SPO-1 - New allocation created
- **Given** no allocation exists for `(SPO-A, productX, warehouseY)`
- **When** an SPO file with that row is imported
- **Then** a new allocation is created, result shows `allocations_created: 1`, `allocations_updated: 0`,
  and no "skipped duplicate" error.

### AC-SPO-2 - Existing allocation updated (higher qty)
- **Given** an allocation for `(SPO-A, productX, warehouseY)` with `allocated_quantity=10`, `quantity_received=0`
- **When** an SPO file with the same key and qty `15` is imported
- **Then** `allocated_quantity` becomes `15`, result shows `allocations_updated: 1`,
  `allocations_created: 0`, and `receipt_status` / `quantity_received` / `created_by` are unchanged.

### AC-SPO-3 - Existing allocation updated (lower qty, still ≥ received)
- **Given** an allocation with `allocated_quantity=10`, `quantity_received=3`
- **When** the same key is re-imported with qty `5`
- **Then** `allocated_quantity` becomes `5` (5 ≥ 3 is valid), counted as updated.

### AC-SPO-4 - Guard: new qty below already-received
- **Given** an allocation with `allocated_quantity=10`, `quantity_received=8`
- **When** the same key is re-imported with qty `5`
- **Then** the allocation is **NOT** changed, `skipped_rows_count` increments, and `errors[]` contains
  an explicit message naming SPO/product/warehouse, new qty `5`, and received `8`.

### AC-SPO-5 - No-op on identical qty
- **Given** an allocation with `allocated_quantity=10`
- **When** the same key is re-imported with qty `10`
- **Then** nothing is written, and it is **not** counted in `allocations_updated`.

### AC-SPO-6 - Mixed file
- **Given** a file with one new row, one higher-qty update, one identical row, one guarded row
- **When** imported
- **Then** counters read `created:1, updated:1`, the identical row is excluded from updated, the guarded
  row appears in `errors[]` and `skipped_rows_count:1`, and no generic "Skipped duplicate" message appears.

### AC-SPO-7 - Shipment line status refreshed
- **Given** an allocation whose qty is updated by import
- **Then** the owning inbound shipment's line statuses are refreshed (reflect the new allocated qty).

---

## 2. Team hierarchy

### AC-TH-1 - Set parent team
- **Given** I edit team "Marketing - Product"
- **When** I select "Marketing - Manager" as parent and save
- **Then** the team persists `parent_team_id` and the hierarchy shows Product under Manager.

### AC-TH-2 - Cycle prevented
- **Given** "Marketing - Product" is a child of "Marketing - Manager"
- **When** I try to set "Marketing - Product" as the parent of "Marketing - Manager"
- **Then** the save is rejected with a clear "cannot create a cycle" message; a team also cannot be its own parent.

### AC-TH-3 - Recursive descendants
- **Given** Manager → Product → Sub-Product (grandchild)
- **When** descendants of Manager are resolved
- **Then** both Product and Sub-Product members are included (any depth).

---

## 3. My Team Tasks view

### AC-TT-1 - Peers visible
- **Given** I am a member of "Marketing - Product" with teammate Charissa
- **When** I open My Team Tasks
- **Then** I see Charissa's unresolved SLA tasks; I do NOT see my own (those stay in My Pending).

### AC-TT-2 - Manager sees child teams
- **Given** I am a member of "Marketing - Manager" (parent of "Marketing - Product")
- **When** I open My Team Tasks
- **Then** I see tasks of all Marketing - Product members (and any grandchild team).

### AC-TT-3 - Assignee shown
- **Given** Team Tasks lists rows
- **Then** each row clearly shows the human-readable assignee name (no UUIDs).

### AC-TT-4 - Filters
- **Given** Team Tasks with several assignees across multiple child teams
- **When** I filter by an assignee and/or by a team
- **Then** only matching rows show; clearing filters restores the full visible set.

### AC-TT-5 - Home widget toggle
- **Given** the home pending-tasks widget
- **When** I toggle to "My Team"
- **Then** it shows team tasks with assignee + Takeover/Reassign actions, plus a "View all" link to the
  dedicated page.

### AC-TT-6 - Scope isolation
- **Given** a task assigned to a user in a team I am NOT in (and not a descendant of my teams)
- **Then** it never appears in my Team Tasks.

---

## 4. Takeover

### AC-TO-1 - Grab to self
- **Given** a conversation SLA task assigned to Charissa, visible in my Team Tasks under "Marketing - Product"
- **When** I click Takeover
- **Then** `assigned_to_id` becomes me, the task now appears in My Pending, and disappears from my "others'" Team list.

### AC-TO-2 - Team re-derived from queue context
- **Given** I take over a task shown under "Marketing - Product"
- **Then** `team_set_code` / `agent_id` / `current_tier` are set from that team's `agent_teams` link, so a
  subsequent escalation follows that team's chain.

### AC-TO-3 - Clock NOT reset
- **Given** a task with `due_at` of 14:00
- **When** I take it over
- **Then** `due_at`, `due_at_resolution`, and `current_tier_started_at` are unchanged.

### AC-TO-4 - Audit log
- **When** I take over
- **Then** a `conversation_sla_event_log` row is written: `event_type='reassignment'`, `trigger='manual'`,
  `triggered_by_id=me`, `assigned_to_id=me`, reason 'takeover'.

### AC-TO-5 - Respond push (conversation row)
- **Given** I take over a conversation SLA row and I have a `respond_user_id`
- **Then** Respond.io conversation assignee is set to me, and an `integration_log` row is written.

### AC-TO-6 - Respond push best-effort
- **Given** the Respond.io call fails (e.g. wrong creds)
- **When** I take over
- **Then** the takeover still succeeds (no 500), and an `integration_log` records the failure.

### AC-TO-7 - Form row skips push
- **Given** I take over a form SLA row (complaint / stock_inquiry / purchase_request)
- **Then** no Respond.io assignee call is made; CRM reassignment still applies.

### AC-TO-8 - Taker without Respond mapping
- **Given** I have no `respond_user_id`
- **When** I take over a conversation row
- **Then** CRM reassignment applies, the push is skipped, and a warning is logged (not blocked).

### AC-TO-9 - RR cursor advanced
- **When** I take over
- **Then** the target team's round-robin cursor points to me, so the next auto-assign continues after me.

---

## 5. Reassign

### AC-RA-1 - Available on both tabs
- **Given** My Pending and My Team Tasks
- **Then** a Reassign action is present on rows in both (Takeover only on Team Tasks).

### AC-RA-2 - Picker scope
- **When** I open the Reassign picker
- **Then** it lists only users I can see (my teams + visible child teams); users outside that scope are absent.

### AC-RA-3 - Hand off
- **Given** I reassign my task to Tay
- **Then** `assigned_to_id` becomes Tay, the task leaves my My Pending and appears in Tay's.

### AC-RA-4 - Original team/clock kept
- **When** I reassign
- **Then** `team_set_code` / `current_tier` / `agent_id` and `due_at` / `due_at_resolution` /
  `current_tier_started_at` are all unchanged (only assignee changes).

### AC-RA-5 - Respond + audit
- **Then** conversation rows push the new assignee to Respond.io (best-effort + integration_log); a
  `reassignment` event log is written with `triggered_by_id=me`, `assigned_to_id=target`.

---

## 6. Notifications (takeover & reassign)

### AC-NT-1 - New assignee notified
- **When** a task is taken over or reassigned to a user
- **Then** that user receives an in-app notification, plus email/WhatsApp per their own
  assignment-channel toggles.

### AC-NT-2 - Old assignee notified when actor differs
- **Given** a manager reassigns / a peer takes over Charissa's task
- **Then** Charissa is notified her task was moved.

### AC-NT-3 - No self-notify
- **Given** I reassign my own task
- **Then** I (the old assignee and actor) receive no "your task was moved" notification.

---

## 7. Coverage subscriptions

### AC-CS-1 - Subscribe
- **Given** I am covering for Charissa
- **When** I subscribe to her from Team Tasks or the Coverage section
- **Then** an active `notification_subscriptions` row (me → Charissa) exists.

### AC-CS-2 - Assignment fan-out
- **Given** I am subscribed to Charissa
- **When** a new SLA task is assigned (RR or manual) to Charissa
- **Then** I also receive a notification labeled "(covering for Charissa)".

### AC-CS-3 - Escalation fan-out
- **Given** I am subscribed to Charissa
- **When** a task escalates to Charissa
- **Then** I also receive the escalation notification, labeled as covering.

### AC-CS-4 - Subscriber channel gating
- **Given** I am subscribed and my own `notify_email_on_assignment` is off but in-app is on
- **When** Charissa is assigned a task
- **Then** I get the in-app copy but no email; WhatsApp/email follow MY toggles, not Charissa's.

### AC-CS-5 - Scope limited to SLA assignment/escalation
- **Given** I am subscribed to Charissa
- **When** Charissa receives an unrelated account notification (not SLA assignment/escalation)
- **Then** I do NOT receive a copy.

### AC-CS-6 - No double-send
- **Given** I am subscribed to Charissa AND a task gets assigned to me directly
- **Then** I receive exactly one notification (no duplicate from the subscription path).

### AC-CS-7 - Unsubscribe / expiry
- **Given** an active subscription
- **When** I unsubscribe, or `expires_at` passes
- **Then** the subscription becomes inactive and no further copies are sent.

### AC-CS-8 - Self-subscription rejected
- **When** I try to subscribe to myself
- **Then** it is rejected.

### AC-CS-9 - Picker scope
- **When** I add a coverage target
- **Then** only scope-B users (my teams + child teams) are selectable.

---

## 8. Round-robin per-member opt-out

### AC-RR-1 - Default included
- **Given** a member added to a team
- **Then** `include_in_round_robin` defaults to true and they receive auto-assignments.

### AC-RR-2 - Excluded member skipped
- **Given** Agnes has `include_in_round_robin=false` in "Customer Service"
- **When** the team auto-assigns via round-robin
- **Then** Agnes is never auto-selected; rotation covers only checked members.

### AC-RR-3 - Per-team independence
- **Given** a user is in Team A (checked) and Team B (unchecked)
- **Then** they are auto-assignable in A but not in B.

### AC-RR-4 - Manual still allowed
- **Given** Agnes is excluded from RR
- **When** I Takeover-assign or Reassign a task to Agnes
- **Then** it succeeds; the flag governs auto-distribution only, and Agnes still appears in Team Tasks.

### AC-RR-5 - All-excluded edge
- **Given** every member of a team has `include_in_round_robin=false`
- **When** auto-assign runs
- **Then** it fails with the same "no eligible assignee" error as an empty team (no silent misassign).

---

## Cross-cutting

### AC-X-1 - No UUIDs in UI
- Every assignee, team, and target rendered to the user is a human-readable name, never a raw UUID.

### AC-X-2 - Resolved tasks excluded
- Resolved SLA tasks never appear in My Pending or My Team Tasks, and are never fanned out.

### AC-X-3 - Permission = visibility
- A user can Takeover/Reassign exactly the tasks visible in their Team Tasks; no separate RBAC slug
  blocks or grants the action beyond visibility.
