# AGENT-PROJECT-SCOPE: turns for the frozen live regression set

Crew pass on 6aef629d (11 Nov). Crew runs this on the Mac against the crew test copy of the lane's final head (the
cloud sandbox has no provider key). Expected values are read from the Projects list at test time, never fixed numbers.

## Run order
1. x1: each turn below once, in order. Stop and report if any run is wrong.
2. x3: only if x1 passes, each turn twice more (3 runs per turn in all, 9 turns at most, ledgered: tools called with
   args, reply, any figure left out, model, tokens). Stop at the first degrading run and report it.

## Setup
- Restart the MCP server on the test copy (the project tool descriptions changed).
- S: a salesperson on the agent path who can see every project (on dev the `salesperson` role holds
  `projects.projects.view`). N = how many projects the Projects list shows S owning at test time (0 on dev).
- Reach S by Users & Access > People > Administrative Users > row menu > Impersonate user.

## Turns
| # | Who | Page open when sent | Chat | Message | Expected rule |
|---|-----|---------------------|------|---------|---------------|
| R1 | S | Project Sales > Projects (the list on screen) | new chat | which of my projects have quotations | Only S's own projects (N = 0: S has no projects). Never another owner's rows or count presented as S's. No unrequested totals or breakdowns. The trace starts with crm_projects_list owner "me". |
| R2 | S | Project Sales > Projects | follow-up to R1 | how many projects do I own | N, as the Projects list shows S owning. Never another owner's count. Nothing else. |
| R3 | J | (crew: from the helper trace) | (crew: new chat or follow-up) | (crew: J's totals question, verbatim) | Only the totals asked for. No per-scope totals nobody asked for. |
| R4 | admin | (crew: from the helper trace) | (crew) | (crew: the step-10 "how many projects are there and who owns them" turn, verbatim) | T projects and each owner's count as the Projects list shows. No per-project breakdown nobody asked for. |

R3 and R4 are filled in by crew from the helper traces (the lane worker does not have them).
Pass: every run of every turn follows its rule.
