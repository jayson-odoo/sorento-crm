# PLAN: AI agent project tools scoped to what the asker can see (AGENT-PROJECT-SCOPE)

Status: in progress (small fix track: expected diff under 300 lines, no migration, no new permission, no new ingest surface).

## Trigger
Crew browser pass on PR #2337 (11 Nov): viewing as a non-admin salesperson, the AI agent said there are
16 projects in the system and named their owners. Owner ruling (11 Nov): the AI answers only about projects
(and project data) the person can already see in the app.

## Approach
Find every project-returning agent tool, compare with the access filter the Projects list API applies
(`app/api/v1/projects/projects.py` `_visible_to` / `own_scope.project_clause`), and route the leaking ones
through that same filter. No new access rules; admin and `projects.projects.view` holders unchanged.

## Findings
(filled in as the lane proceeds)

## Test list
- salesperson (view_own only) asks count / list / owners: only projects visible in the app.
- a project of another owner: not found.
- admin: unchanged.
- kill test: removing the filter turns a test red.
