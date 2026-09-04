# Sample `/api/v1/external/chat/turn` responses

Real bytes, not hand-written: each file is the endpoint's own `response_model=TurnResponse`
output, produced through `TestClient` against the blank Postgres test schema with the LANE's
I/O seams stubbed (`next_assignee`, `sla_create`) and nothing else. The n8n action executor
renders its expressions against these.

Ids: contact `437264483` is the dev contact and is real. Every user id is synthetic
(`100000001`).

## `chat-turn-out_of_scope.dry-run.json`

`is_test: true`. **One action**, and that is the point: D14 / H37 means a dry run reaches no
seam at all - no assignee is picked, no cursor moves, no SLA row is written - so the only
thing it can produce is the acknowledgement message. `session_patch` carries what the tail
WOULD have written.

## `chat-turn-out_of_scope.assigned.json`

The same turn WITHOUT `is_test`, so the lane runs its seams and the executor can see the
whole action list. **This is the file to render against**, because the four-action shape
cannot come from a dry run.

Two things to read carefully:

* **`reply.text` is null.** The customer copy for this lane lives in the ACTIONS, not in
  `reply`: `escalate-catalog` composes the out-of-scope acknowledgement with
  `includeResponse: false`, so it is session bookkeeping rather than a message to send. An
  executor that sends `reply.text` when it is set, and the `send_message` actions always,
  is correct for every lane.
* **`send_message` carries `quick_replies` and `result_set`**, filled from the sealed reply
  after the tail runs. They are `[]` here because this lane offers no choices and returns no
  rows; both keys are always present, so the executor never has to test for a missing one.
  When the tail produces an `attachments_src`, a fifth action (`send_attachments`) is
  appended after both messages.
