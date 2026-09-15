# Turn replay divergences (AC-1591)

Signed exceptions to `test_turn_replay.py`'s structural comparison. A mismatch between
a recorded case's `expected` and what the current engine actually did is a FAILURE
unless it has a signed line here - an unsigned line (no `(signed ...)`) does not count
and the test still fails, so a placeholder cannot silently excuse a real divergence.

Format, one line per excused field:

```
- <group>/<slug>: <field>: <reason> (signed <initials> <date>)
```

`<group>/<slug>` is the case file's path relative to `tests/chatbot/replay_turns/`
(e.g. `console/owner-15sep-chain-001.json`). `<field>` is one of `branch_kind`,
`action_kinds`, `tools`, `pending`, `canned`, `text`. `<reason>` names the RULE that
changed and why the new behaviour is correct, never just "known issue".

No SIGNED entries yet - none of these are the tester's to sign (a captain/owner
ruling is what a signature records). `pytest tests/chatbot/test_turn_replay.py` on
this corpus (16 Sep 2026, engine head `3d71013ab`): 29 passed, 79 failed, 37s. The
79 failures cluster into three known CAUSES, reported here rather than silently
excused, so the captain can decide per-cluster whether the entry is "sign it" or
"real regression, route to the coder":

1. **`branch_kind` moving to `clarify_menu` / `escalate_offer` on a `prod_sample`
   turn whose recorded verdict has an EMPTY `entities[]`** (about 100+45 of the 79
   failures, mostly `business_query` and `check_promotion` samples). Root cause is
   the harness's own `resolutions` stub (`scripts/chatbot_record_turn.py::
   _derive_resolutions` - see that function's docstring): a real prod turn that
   REUSED a product from a PRIOR turn's focus never re-states it in its own verdict,
   so this harness's positional entity<->uuid pairing has nothing to pair and the
   replayed turn resolves nothing, where the ORIGINAL turn had real carried focus
   state this harness does not reconstruct for a standalone (non-chain)
   `prod_sample` case. **Not an engine defect** - an environment limitation of
   replaying an isolated single turn out of a real multi-turn conversation. The
   `console/` chain cases do not have this problem (state carries for real between
   steps); a future corpus pass should prefer curating `prod_sample` to
   `entity_op: replace_combine` turns (self-contained) the way `contract/line-001`
   was chosen, or record chains instead of single turns.
2. **`branch_kind` moving to `low_signal`** (`escalation_declined`/`check_promotion`
   samples, about 45 failures). Same root cause as (1): several of these prod turns
   were themselves an ANSWER to a prior turn's pending question, which a standalone
   recording does not carry.
3. **`action_kinds` missing a `send_attachments` entry** (business_query samples,
   including `contract/line-001-stock-by-location.json`). This one is NOT explained
   by missing prior-turn state - the recorded tool envelope's `attachments` field is
   stubbed back verbatim and the current engine still does not emit a
   `send_attachments` action from it. **Flagged as a possible real finding**, not
   signed off: needs a coder/captain look at whether `_attachments_src` (or its
   rearch successor) still wires a fetch envelope's `attachments` into an action on
   this path.

The template below is real, not illustrative filler to delete before first use.
