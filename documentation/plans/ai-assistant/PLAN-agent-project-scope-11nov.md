# PLAN: AI agent project tools scoped to what the asker can see (AGENT-PROJECT-SCOPE)

Status: in review (small fix track: expected diff under 300 lines, no migration, no new permission, no new ingest surface).

## Trigger
Crew browser pass on PR #2337 (11 Nov): viewing as a non-admin salesperson, the AI agent said there are
16 projects in the system and named their owners. Owner ruling (11 Nov): the AI answers only about projects
(and project data) the person can already see in the app.

## Approach
Find every project-returning agent tool, compare with the access filter the Projects list API applies
(`app/api/v1/projects/projects.py` `_visible_to` / `own_scope.project_clause`), and route the leaking ones
through that same filter. No new access rules; admin and `projects.projects.view` holders unchanged.

## Findings (11 Nov, sandbox, fake data)
No leaking path found on main. Every project read the agent can reach applies the Projects list's own filter:
- `crm_projects_list` (MCP, API key + `X-Staff-User`) and `crm_projects_find` (in process) -> `list_projects`
  `visible_to=_visible_to(...)` (`app/api/v1/projects/projects.py:251`, `:358`).
- `crm_project_detail`, `crm_project_quotations_list` -> router guard `app/api/v1/projects/_own_scope.py` `check()` (404).
- `crm_project_quotation_lines` -> the same `check()` (`app/services/chatbot/agent/tools.py:1214`).
- `crm_project_forecast` -> `projects.projects.view` only, no own slug (`agent/tools.py:144`); route 403 for view_own.
- resolver project probe filters (`app/services/entity_resolver.py:5002-5012`); `crm_query` has no project entity;
  `crm_resolve` has no project kind.
Verified over the real MCP server + backend as a view_own user (own project only) and as admin (all).
`own_scope` treats a user holding BOTH `view` and `view_own` as unlimited (`app/services/own_scope.py:3-5`).
Crew evidence (dev DB, trace 282dec26): role `salesperson` there holds `projects.projects.view` AND `.view_own`
(both added 9 Nov), so the user is not limited and the app shows them all 16: no scoping leak. Crew ruling: ship the
pinning tests, and fix the real bug: "which of my projects ..." sent `owner_user_ids: "<name>"`, was refused
(ids come from crm_resolve), crm_resolve was not offered, so the agent listed every project.

## Fix (AC-5)
`crm_projects_list` takes `owner_user_ids: "me"` at the agent seam: `_swap_self` in
`app/services/chatbot/agent/tools.py` replaces it with the asker's own user id before the id check, and the
schema the model sees says so. Any other value keeps the id check. Who should hold `projects.projects.view` is
a role setting for the owner (crew asks separately).

## Tests
`sorento_crm_backend/tests/chatbot/agent/test_agent_project_scope.py`: 13 scoping tests green on main, plus 11 AC-5 tests (red on main; with the `_swap_self` call removed 4 go red, with the hint removed 2, and the follow-up-id test pins that the turn's seen set survives a "me" call); with the list filter
and the router guard removed, 8 go red (kill test).

## Test list
- salesperson (view_own only) asks count / list / owners: only projects visible in the app.
- a project of another owner: not found.
- admin: unchanged.
- kill test: removing the filter turns a test red.

## Fix round after the crew browser pass on b9852915 (11 Nov)
Scoping passed. Two answers misled:
1. A salesperson with 0 projects read "... ((not verified) projects found)": an EMPTY result did not back 0, and the
   repair wrote "(not verified)" into the sentence. Now an empty result backs 0 (`loop.verify_answer`), and the
   repair (`loop._redact_written`) leaves out each sentence or line holding an unbacked figure and adds one closing
   note (`LEFT_OUT_NOTE`; `ALL_LEFT_OUT_NOTE` when nothing is left). Crew ruling: a repair never writes into a
   sentence. The ~30 older tests pinned to the in-sentence placeholder were updated to this rule.
2. "Who owns them" answered 16 right but 10 / 6 against 8 / 8: 16 full rows are larger than the result cap
   (`tools.cap_result`), so the model counted the rows left. `tools.with_owner_counts` adds `count_by_owner` from
   every row before the cap (a note asking for `limit=<total>` when the page does not hold every match), the tool
   description tells the model to quote it, and `loop._group_count_misses` holds a figure written after an
   owner's name to that owner's count.
Tests: `tests/chatbot/agent/test_agent_project_counts.py`.
