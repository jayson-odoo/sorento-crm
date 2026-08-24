# UAC - CS team market-segment routing (retail / project)

Acceptance criteria for `PLAN-cs-team-market-segment-routing.md`. Every line must pass (BE + FE)
with an automated test or a scripted check before manual eyeball. Regression lines are hard blockers.

Legend: ☐ pending · ☑ passed (fill in as verified).

## A. Catalog / schema

- A1 ☑ Migration creates `market_segments`, `respond_contact_market_segments`,
  `team_member_market_segments`, and adds `segment_key VARCHAR(120) NOT NULL DEFAULT ''` to
  `agent_team_round_robin_cursors` (unique index widened to `(agent_id, team_id, segment_key)`,
  old 2-col unique dropped). `''` = the legacy / no-segment cursor. Idempotent (re-run = no-op).
- A2 ☑ Migration seeds `market_segments` with `retail` (Retail) + `project` (Project), active.
- A3 ☑ Migration downgrade drops the three tables + restores the 2-col cursor unique index cleanly.
- A4 ☑ Existing `agent_team_round_robin_cursors` rows survive with `segment_key = ''` (position kept).

## B. Contact segment (backend + UI)

- B1 ☑ Internal endpoint returns a contact's assigned segments; empty list when none.
- B2 ☑ Internal endpoint sets a contact's segments (retail / project / both / none), idempotent.
- B3 ☑ Contact Details page renders a **Market Segment** section always (empty state when none).
- B4 ☑ Editing a contact's segments persists and re-renders badges. Delete/unassign uses a confirm
  per the destructive-action rule.

## C. Member segment (backend + UI)

- C1 ☑ Internal endpoint returns a team-member's segments; empty list when none.
- C2 ☑ Internal endpoint sets a team-member's segments (per `(user, team)` membership), idempotent.
- C3 ☑ Access Agent Detail team roster renders a per-member segment multiselect; both = both selected.
- C4 ☑ Setting a member's segments persists and re-renders.

## D. `team-members` endpoint filtering (external)

- D1 ☑ `?contact_id={respond_io_id}` where contact = retail → returns only members serving retail
  (plus untagged members). Response shape unchanged (`user_id,name,respond_user_id,email,sort_order`).
- D2 ☑ contact = project → only project (+ untagged) members.
- D3 ☑ contact = both → union of retail and project (+ untagged) members.
- D4 ☑ contact has NO segment → ALL active members (minimum-config guarantee).
- D5 ☑ `contact_id` omitted → ALL active members, **byte-identical to today** (no regression).
- D6 ☑ unknown / other-workspace `contact_id` → ALL active members, HTTP 200, logged (never 404).
- D7 ☑ segment filter ANDs with tier: only the `tier=1` team's members considered.
- D8 ☑ retail contact but ZERO retail (and zero untagged) members → **fall back to ALL** (never empty).

## E. `next-assignee` endpoint (regression + opt-in)

- E1 ☑ **REGRESSION (hard):** POST with NO `contact_id` → round-robin sequence over the full team is
  byte-identical to current behaviour, for a CS team AND a non-CS team. Cursor row used = `segment_key=''` (empty).
- E2 ☑ `preferred_assignee_id` path unchanged: returns that member directly, cursor not advanced.
- E3 ☑ POST WITH `contact_id` (retail contact) → RR pool restricted to retail (+ untagged) members;
  cursor scoped to `segment_key="retail"`; rotates within the pool.
- E4 ☑ WITH `contact_id`, both-contact → `segment_key="project|retail"` (sorted, `|`-joined), rotates
  over the union pool.
- E5 ☑ WITH `contact_id`, empty segment pool → fall back to full team + '' (empty) cursor (never 404 for pool).
- E6 ☑ contact untagged (has no segment) passed as `contact_id` → treated as all → '' (empty) cursor,
  identical to E1 rotation (no separate cursor spawned).

## F. Catalog admin UI + CRUD

- F1 ☑ `GET` catalog lists segments (code, name, is_active, sort_order).
- F2 ☑ `POST` creates a segment; duplicate code rejected (validation).
- F3 ☑ `PUT` renames / toggles active / reorders.
- F4 ☑ `DELETE` hard-deletes; blocked or cascade-warned when the segment is assigned to any
  contact/member (destructive-action confirm dialog on the FE).
- F5 ☑ Settings → Market Segments screen renders DataGrid + Add toolbar; create/edit modal;
  delete AlertDialog with standard copy. States: loading/empty/error/data.
- F6 ☑ CRUD endpoints enforce auth (401/403 without a valid principal).

## G. Match semantics (unit-level)

- G1 ☑ Untagged member matches every contact segment (serves all).
- G2 ☑ Untagged contact matches every member (all).
- G3 ☑ Intersection non-empty = match; disjoint = no match.
- G4 ☑ Empty filtered pool → fall back to all (both endpoints).

## H. No-regression suite

- H1 ☑ Existing `tests/` suite green (at minimum the team/assignee/SLA-touching tests + the two
  files added earlier: `test_chat_history_result_set`, `test_order_outstanding_filter`).
- H2 ☑ `team-members` and `next-assignee` existing behaviour unchanged when the new params are absent
  (covered by D5 + E1, called out separately as the release gate).
- H3 ☑ `alembic upgrade head` and `downgrade -1` both succeed on the new migration.
- H4 ☑ FE `npm run build` succeeds; new components pass vitest; no console errors on the touched pages.
