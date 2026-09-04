# PLAN - Teams hierarchy UI (tree + members popover + drag-drop reparent)

Status: **Done - verified in browser** (2026-06-28). BE enrich + FE tree/popover/drag-drop shipped; pytest (9) + vitest (6) green; reparent PUT 200 confirmed via Playwright MCP.

## Goal

Redesign User Management → Teams list so admins can:
- See parent→child team hierarchy (grandparent → parent → child → grandchild …) as an indented, expand/collapse tree.
- See real members per team (replacing the hand-typed `description` text) via a **member-count badge → popover** that lists member names with a "Manage members" link.
- **Drag-and-drop reparent**: drag a team row onto another to make it a child; drop onto a "root" zone to detach to top level.

## What already exists (no change needed)

- `teams.parent_team_id` self-FK + `ix_teams_parent_team_id` (migration 238).
- `PUT /api/v1/user-management/teams/{id}` accepts `parent_team_id`; service `_guard_parent_team_cycle` rejects self-parent + descendant-as-parent cycles.
- `descendant_team_ids()` recursive CTE/BFS helper.
- Members CRUD endpoints + members page at `/user-management/teams/[id]`.

## Backend (small enrichment)

`list_teams()` returns plain ORM with no member info. Enrich the list payload:

- `app/schemas/user.py`: add `TeamMemberPreview { user_id: str, name: str }`; extend `TeamResponse` with `member_count: int = 0` and `members: list[TeamMemberPreview] = []`.
- `app/services/user_service.py` `list_teams()`: one grouped query (TeamMember JOIN User) → group in Python, return dicts shaped to `TeamResponse`. **No N+1.** Order members by `sort_order` nullslast then name. Resolve user display name (`User.name or User.email`), never expose UUID.
- Route unchanged (`response_model=list[TeamResponse]`).

## Frontend

- `types/team.types.ts`: add `member_count?: number`, `members?: { user_id: string; name: string }[]` to `Team`.
- New `components/team-tree.tsx`: build tree from flat list by `parent_team_id` (roots = null parent OR parent not in set). Indented rows, chevron expand/collapse (default expanded), name, member-count badge, actions (Members link + edit/delete dropdown). Native HTML5 drag-drop:
 - Each row `draggable`; drop on a row → `updateTeam(dragId, { parent_team_id: targetId })`.
 - Root dropzone at top → `parent_team_id: null`.
 - Client-side guard: disable drop on self or own descendant (compute descendant set in FE) for instant feedback; server still authoritative.
 - On success: invalidate `['user-management-teams']` + toast.
- New `components/team-member-popover.tsx`: count badge trigger → Popover listing member names + "Manage members" link to `[id]` page. Empty state ("No members yet") when count 0.
- `components/team-list.tsx`: swap DataGrid table body for `<TeamTree>`, keep Card shell + Create button + search filter (filter keeps matching nodes + ancestors).

## Tests (Phase 2)

- pytest: `list_teams` returns `member_count` + `members` names; no UUID leak.
- vitest: tree builds correct nesting; member popover lists names + empty state; drop disabled on descendant.
- Playwright: expand/collapse, open member popover, drag row to reparent → assert `PUT /teams/{id}` with `parent_team_id`.
