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

## Fix round after the crew re-pass on 2bf85995 (11 Nov)
Fixes (1) and (2) passed. Four more, each with a test in `tests/chatbot/agent/test_agent_project_counts.py`:
- (a) "my projects" answers appended unrequested company-wide totals: `loop.ANSWER_SCOPE_RULE` ("ANSWER ONLY WHAT
  WAS ASKED", owner standing rule) is appended to the agent prompt at runtime, staff and contact.
- (b) "project pursuits": the four project tool descriptions say "project" (`sorento_crm_mcp/catalog.py` and its
  backend copy `app/services/mcp_catalog_copy.py`, kept identical); the rule above also says to call them projects.
- (c) the trace said 9 rows for 8 projects: a second `_row_count` in `agent/loop.py` shadowed the first and summed
  every list, `count_by_owner` included. One counter now, the longest list (result rows only).
- (d) a project was named by its short name and its long title in turn: `tools.with_project_names` hands the model
  one `name` per project row by the Projects list's rule (short name, else title) and drops `title`, for
  `crm_projects_list` and `crm_project_detail`; `crm_projects_find` returns the same `name`.
Follow-up (out of scope): conversation history shows "8h ago" for a fresh message (timezone).

## Fix round after the crew pass on 6aef629d (11 Nov)
Fail: S (owns 0) asked "my projects" with the Projects page open; the "me" read returned 0, then the model listed all
16 unfiltered and presented another owner's rows and count as S's own (3 of 3 such turns re-listed, 2 of 3 named the
wrong owner; from the Users page 2 of 2 right). Fixed in the data, not by word lists (owner rule):
- the projects route says on every row whether the reader owns it (`owner_is_viewer`, `project_service.serialize_projects`,
  `ProjectResponse`); it survives the MCP slimming;
- a complete unfiltered list carries `your_projects` (rows the reader owns) beside `count_by_owner`, and the tool
  description says a row is the asker's only when `owner_is_viewer` is true;
- an empty "me" read answers `NONE_OF_YOURS` ("The person asking owns none: that is the answer ..."), not the plain
  "no rows" line;
- a read filtered by owner carries no `count_by_owner`: one owner needs no breakdown, and it is a figure nobody asked for;
- the page note's header says a list on screen is what the user can see, not what is theirs (`panel_service.SCREEN_NOT_YOURS`).
Not fixed by data: unrequested breakdowns in other answers (step 10 per-project, J per-scope totals) rest on the
answer-scope rule; the live set measures them. Live set: `agent-project-scope-live-set.md` (crew runs it).
- Crew case A (J, "do any of my projects have quotations?", answered with 8 per-scope totals nobody asked for): the
  list row now carries `quotation_document_count` (one grouped count in `serialize_projects`), so the question is
  answered from the list with no totals read; the tool description says so.
