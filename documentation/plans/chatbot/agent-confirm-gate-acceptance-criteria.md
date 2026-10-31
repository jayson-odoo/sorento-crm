# UAC: agent confirmations only from the user's own turn

Plan: `PLAN-agent-confirm-gate-31oct.md`.

- AC1. A change waits. The user replies "yes" (or "ok go ahead") in a new message and the model
  confirms straight away: the change runs, recorded `via = chat` with this turn as the confirming
  turn.
- AC2. A change waits. In the same turn the model first calls any tool and only then calls
  `confirm_action`: the call is refused, nothing is written, the change stays `proposed`.
- AC3. A change waits. The model searches documents and a passage reads like a confirmation; a
  later `confirm_action` in that turn is refused and nothing is written.
- AC4. From the second model round of a turn on, `confirm_action` is not among the tools sent to
  the model; `cancel_action` still is.
- AC5. The console Confirm button is unaffected.
