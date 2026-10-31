# PLAN: agent confirmations only from the user's own turn

Status: in review, PR open; reviewer READY, security review ready (small fix track: one coder writing tests + fix, one reviewer, plus a security
review because the change gates an agent write; no migration, no RBAC change, no UI change).

UAC: `agent-confirm-gate-acceptance-criteria.md` (alongside).

## Problem

A change the Console agent proposed waits for a decision. In a later turn the model may call
`confirm_action`, and `actions.confirm` runs the change. The yes is read semantically by the model
from the user's latest message (owner ruling 30 Oct, P3-Q4, kept). Code checked only that the
confirming turn is not the proposing turn (`agent/actions.py` `same_turn`); it did not check WHEN
in the turn the model asked to confirm. Inside one turn the model also reads tool results and
document passages (`crm_knowledge_search`), which are not the user's words.

## Fix (option a)

`confirm_action` is offered and accepted only in the turn's FIRST model round, before any tool
output of this turn has reached the model. From the second round on:

- the `confirm_action` schema is no longer sent to the model, and
- a `confirm_action` call is refused in code (`ToolResult("denied")`), nothing runs.

`cancel_action` is unchanged (dropping a change is always safe). The console Confirm button
(`POST /agent/actions/{id}/confirm`, `via="console"`) is unchanged.

Files: `sorento_crm_backend/app/services/chatbot/agent/loop.py` only (the round loop and
`_decide`). PR 2051 (AGENTIC-UNIFY) edits the message build above the round loop; this lane stays
inside the loop to avoid overlapping edits.

## Tests

`sorento_crm_backend/tests/chatbot/agent/test_agent_confirm_gate.py`:

1. Scripted model reads a tool result, then confirms in round 2: nothing runs, action stays
   `proposed`.
2. User's own "yes" / "ok go ahead" in a new turn, confirm in round 1: the change runs.
3. A document passage (knowledge search) with confirmation-like text, then confirm: nothing runs.
4. From round 2 on the `confirm_action` schema is not offered; `cancel_action` still is.

Kill test: revert the gate, tests 1, 3, 4 go red.

## Trigger for more

If a later lane lets the model confirm after a clarifying sub-step (for example a first round
that only plans), revisit with a per-message provenance check instead of the round index.
