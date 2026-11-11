# AGENT-PROJECT-SCOPE: turns for the frozen live regression set

Crew pass on 6aef629d (11 Nov). Crew runs this on the Mac against the crew test copy of the lane's final head (the
cloud sandbox has no provider key). Expected values are read from the Projects list at test time, never fixed numbers.

## Run order
1. x1: each turn below once, in order. Stop and report if any run is wrong.
2. x3: only if x1 passes, the turns named under Size twice more each (ledgered: tools called with args, reply, any
   figure left out, model, tokens). Stop at the first degrading run and report it.

## Setup
- Restart the MCP server on the test copy (the project tool descriptions changed).
- S: a salesperson on the agent path who can see every project (on dev the `salesperson` role holds
  `projects.projects.view`). N = how many projects the Projects list shows S owning at test time (0 on dev).
- J: a salesperson who owns 1 project (crew's J).
- Reach S and J by Users & Access > People > Administrative Users > row menu > Impersonate user.

## Turns (4 cases, 6 turns)
| # | Who | Page open when sent | Chat | Message | Expected rule |
|---|-----|---------------------|------|---------|---------------|
| C1.1 | S | Projects list (/project-sales/pipeline, the list on screen) | new chat | which of my projects have quotations | Only S's own projects (N = 0: S has no projects). Never another owner's rows or count presented as S's. No unrequested totals or breakdowns. The trace starts with crm_projects_list owner "me". |
| C1.2 | S | Projects list | follow-up to C1.1 | how many projects do I own | N, as the Projects list shows S owning. Never another owner's count. Nothing else. |
| C2.1 | J, a salesperson who owns 1 project | Administrative Users (/user-management/users, J's no-access view) | new chat | do any of my projects have quotations? | Which of J's projects have quotations, and how many. No per-scope totals, no list of document headers. (Bad shape seen: 6 document headers and 8 "- Scope: ... - Total: n.nn" lines.) |
| C2.2 | J | Administrative Users | follow-up to C2.1 | how many of them are won? | Clean on 6aef629d: kept as a multi-turn check. Only the won count of the projects from C2.1. |
| C3.1 | admin, not impersonating | Projects list (/project-sales/pipeline, grid view) | new chat | which of my projects have quotations | Only the admin's own projects (as many as the Projects list shows the admin owning). |
| C3.2 | admin | Projects list (grid view) | follow-up to C3.1 | how many projects are there and who owns them | T projects and each owner's count, as the Projects list shows. No per-project list or "Project Ownership Breakdown" nobody asked for. (S got exactly the right shape for the same prompt.) |

## Size
x1 is 6 turns. Recommended x3: only the 4 turns that failed on 6aef629d (C1.1, C1.2, C2.1, C3.2), twice more each,
so 6 + 8 = 14 turns at most instead of 24. C2.2 and C3.1 passed and are setup for their follow-ups.
Pass: every run of every turn follows its rule.
