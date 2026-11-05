# PLAN: Projects board view pref (PROJECTS-BOARD-VIEW-PREF)

Status: in progress (small fix track: under 300 lines, no migration, no auth/RBAC change)

## Owner request (5 Nov 2026)
Board cards underline the code and title on hover; the list view does not. And remember the
board/list choice per user so Projects opens in list view for the owner.

## Facts
- `/project-sales/projects` redirects to Pipeline (`app/(protected)/project-sales/projects/page.tsx`).
- Pipeline's Board / Grid toggle is inline in `PipelineClient.tsx`, not the shared
  `components/common/ListBoardViewToggle.tsx`, so the memory is Pipeline-only.
- Today the choice is remembered per BROWSER (`localStore`, key `project-sales.pipeline.view`),
  so it does not follow the user to another device, origin or browser.
- A server-side per-user, per-listing store already exists: `user_list_column_configs`
  (`GET|PUT /api/v1/list-query/column-config/{listing_key}`, partial-merge PUT). Pipeline's grid
  already uses listing key `projects.projects.view::pipeline`.
- No URL param names a view on Pipeline today.

## Change
1. BE: add optional `view` (`board` | `grid` | `list`) to `UserListColumnConfigPayload`. JSONB, no migration.
2. FE: Pipeline reads `config.view` from its own row `projects.projects.view::pipeline-view` (not the grid's `::pipeline` row, whose Reset columns DELETEs the whole row), applies it once, writes
   `{ view }` on toggle. Default for a user with nothing stored stays Board. The old localStorage
   value is used only as a fallback when the server has nothing (so nobody loses their pick).
3. Board card code + title: drop `hover:underline`, use the grid's link hover style.
