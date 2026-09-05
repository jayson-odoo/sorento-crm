# Sample `/api/v1/external/chat/turn` responses

Real bytes, not hand-written: each file is the endpoint's own `response_model=TurnResponse`
output, produced through `TestClient` against the blank Postgres test schema with the LANE's
I/O seams stubbed (`next_assignee`, `sla_create`) and nothing else. The n8n action executor
renders its expressions against these.

Ids: contact `437264483` is the dev contact and is real. Every user id is synthetic
(`100000001`).

## `chat-turn-out_of_scope.dry-run.json`

`is_test: true`. **All four actions, same order, same keys** as the live turn (AC-507). D14 /
H37 still holds underneath: no seam is reached, so no assignee is picked, no cursor moves and
no SLA row is written. What a seam would have returned is stood in for instead, so the
executor can render one set of expressions against both files:

* `assign_conversation.respond_user_id` is `null`, with `preview: true` beside it;
* `add_comment.mention_user_ids` is `[]`, `preview: true`, and the three SLA timestamps in
  its text read `<preview>`;
* both `send_message` texts are REAL - neither depends on a seam (one is fixed, the other
  interpolates the team the ladder resolved before any seam was reached).

`assign_conversation` is always present here even though a live run omits it when the contact
is already assigned: only the seam knows that, so a preview cannot honestly leave it out.
`session_patch` carries what the tail would have written.

## `chat-turn-out_of_scope.assigned.json`

The same turn WITHOUT `is_test`: the lane runs its seams and every value is real. Use this
one to see what the executor actually receives in production.

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
