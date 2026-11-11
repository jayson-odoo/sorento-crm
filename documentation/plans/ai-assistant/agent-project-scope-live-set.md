# AGENT-PROJECT-SCOPE: turns for the frozen live regression set

Crew pass on 6aef629d (11 Nov). Three turns, each run live x3 on the crew test copy (the cloud sandbox has no
provider key). Expected values are read from the Projects list at test time, never fixed numbers.

| # | Who | Page open | Message | Expected |
|---|-----|-----------|---------|----------|
| R1 | S, a salesperson who owns N projects (0 on dev), by Impersonate user | Project Sales > Projects (the list on screen), new chat | which of my projects have quotations | S's own projects only (N = 0: "you have no projects"). Never another owner's rows as S's, no unrequested totals or breakdowns. Trace: crm_projects_list owner "me" first. |
| R2 | S, same chat as R1 | Projects | how many projects do I own | N, as the Projects list shows S owning; never another owner's count. |
| R3 | J (the crew pass's J user) | the project page J asked from | J's totals question from the crew pass (verbatim from its trace) | Only the totals asked for; no per-scope totals nobody asked for. |

Pass: 3 of 3 runs right for each turn. Record per run: tools called with args, the reply, and whether a figure was left out.
