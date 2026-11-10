# PLAN: AGENT-QUOTE-COMPARE - the agent compares a project's quotations

Status: planning (size M, behaviour card pending crew relay). Track: M (agent behaviour on an existing screen).

## Why

Owner, 10 Nov 2026 ~16:10 MYT, prod, AI agent panel on project PPF2611004 (PARAGON VIEW SDN BHD, proposals
such as PRJQ-2026-0008-A): "compare the two quotation for this project". The turn ran 8 rounds, 152,593 tokens
in, 2,650 out, and ended "The agent could not answer: the model provider failed."

Trace:
1. crm_project_quotations_list refused "Unknown id in `project_id`; get ids from crm_resolve first."
2. crm_projects_find (PPF2611004): 1 row
3. crm_project_detail: 5 rows
4. "listing the CRM records you can read": 14 rows
5. (thinking)
6. crm_resolve refused "Unknown argument(s): term."
7. crm_resolve refused "Unknown argument(s): kind, text."
8. crm_project_quotations_list error, then provider failure.

## Causes (file:line)

Filled from the investigation; see sections a-e below.

## Changes

TBD after the behaviour card is answered.

## Tests (red first)

TBD.

## Live evidence

The owner's real question, live, x3 on the dev stack (rounds, tokens, answer), recorded in crew-done.
