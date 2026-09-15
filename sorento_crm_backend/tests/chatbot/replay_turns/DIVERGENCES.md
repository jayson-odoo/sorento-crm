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
ruling is what a signature records).

## Corpus re-recording, 16 Sep 2026 (tester, this session)

`prod_sample/` re-recorded as CONTIGUOUS CHAINS per contact (a captain ruling, not
the tester's own call - see the handoff/commit history): for each of the 10 real
branch kinds, the newest ~15 distinct contacts (fewer where fewer exist), each
recorded as ONE chain covering the real 2-hour window around their most recent
occurrence of that branch kind (`--contact <id> --since <ts-1h> --until <ts+1h>
--is-test false`). 71 chains, 392 turns total, replacing the 85 isolated
single-turn files the previous pass wrote. The 85 isolated files predicted (in the
paragraph above, now historical) that recording CHAINS would fix cluster 1/2 -
partially true, see the real bug found instead.

**Real bug found and fixed, not a corpus curation issue**: `scripts/
chatbot_record_turn.py::_derive_resolutions` wrote a FLAT resolution record
(`{"token", "uuid", "entity_type", "canonical_code"}`) where the real `resolve-
entity` HTTP response - and `test_turn_replay.py::_install_stubs`'s stub of it,
fed straight through - is `{"resolutions": [{"token", "resolved", "matches":
[{"uuid", "entity_type", "canonical_code"}, ...]}]}`, one `matches` LIST per token,
never a bare match record. `resolve_gate.py:373`'s own `jsc.get(resolutions[0],
"matches")` found nothing on the flat shape, so EVERY recorded resolution replayed
as if nothing had resolved, regardless of whether the original live turn resolved
cleanly on ITS OWN first turn (proven this session: `prod_sample/escalation-
declined-480184379-chain-001`'s step 1 is a standalone first turn with a real
matching UUID already in the ORIGINAL corpus's `resolutions` field, and it still
diverged to `clarify_menu` under the old shape). Fixed in `_derive_resolutions`
(nests the match, sets `resolved: true`/`false`); `prod_sample/` re-recorded again
with the fix. Confirmed a real, measurable improvement on the one probed case (3
divergences -> 1); the aggregate file-level pass count moved less (chains fail
file-wide on ANY step's divergence, so a chain with an unrelated later-step issue
still shows red) - see counts below. `console/` and `contract/` were recorded by
the PRIOR session under the OLD buggy shape and are being re-recorded with the fix
as this session's next two deliverables; expect the same class of improvement
there too (the biggest remaining cluster below, `send_attachments` missing, is
concentrated in `console/` case files not yet re-recorded).

`pytest tests/chatbot/test_turn_replay.py` after the prod_sample re-record + fix
(engine head unchanged, `0d72b643d`): **17 passed, 77 failed**, ~45s. By group:
console 5/20 passed, contract 0/1 passed, prod_sample 12/71 passed (up from a
0-chain baseline; the file-level pass rate looks lower than the OLD 85-isolated-
file corpus's 29/106 only because a chain fails wholesale on ANY step, not because
the fix made things worse - the per-STEP divergence rate is markedly better, see
the probed case above). Remaining clusters, largest first (raw grep counts across
all fields, not deduplicated by file):

1. **`action_kinds` missing `send_attachments`** (~276 occurrences, still
   concentrated in the NOT-YET-RE-RECORDED `console/` files). Carried forward from
   the prior analysis: the recorded tool envelope's `attachments` field is stubbed
   back verbatim and the current engine still does not emit a `send_attachments`
   action from it on at least some paths. **Still flagged as a possible real
   finding**, not signed off - re-check after `console/` is re-recorded with the
   resolutions fix, since some of this may be the SAME resolution-shape cascade.
2. **`branch_kind` moving to `clarify_menu`** (business_query/check_promotion,
   ~150 occurrences remaining even after the fix). Root cause not fully closed:
   likely the ORIGINAL cluster-1 cause (a turn that reused a product from a PRIOR
   turn's own focus, which even a same-contact CHAIN only fixes if the prior turn
   in the SAME file itself resolved and carried focus correctly - a step N failure
   cascades to every step after it in that file). Needs the coder/captain to look
   at whether this is chain-cascade noise (expected, once step 1 of each affected
   chain is confirmed clean) or a second real defect.
3. **`pending` options mismatch** (`expected None, got ['Yes']`, 48 occurrences) -
   NEW this session, not previously clustered (may be a consequence of the
   resolutions-shape fix surfacing a pending/yes-no offer path that previously
   never got far enough to reach). Not investigated further - flagged, not chased.
4. **`branch_kind` moving to `escalate_offer`** (`expected business_query`, 45
   occurrences) - NEW this session, same caveat as (3).
5. **`branch_kind` moving to `low_signal`** (escalation_declined/check_promotion/
   stock_denied/demand_qty/out_of_scope, ~62 occurrences) - carried forward,
   likely the SAME chain-cascade class as (2): an escalation_declined turn is
   itself an ANSWER to a prior pending offer, so if the offer-raising step earlier
   in the same chain diverged, the decline step has nothing real to decline.
6. **`branch_kind`: `stock_denied`/`demand_qty` unreachable in replay at all**
   (~19 occurrences) - **root cause IDENTIFIED, not fixed here**:
   `test_turn_replay.py` never sets `system_settings.chatbot_stock_denial_enabled`
   in the private test DB, so `engine.py::_stock_denial_enabled` reads its
   hard-coded `False` default on every replay run (confirmed by grep - the harness
   file has zero references to this setting) - contract 61/62's two branch kinds
   are STRUCTURALLY unreachable in replay regardless of what the recorded verdict
   says, on every case, not case-by-case noise. This is a harness gap
   (`test_turn_replay.py` itself, S6 deliverable 2), not a corpus curation issue or
   an engine defect - flagged for the coder/captain, not fixed by the tester
   (LESSONS: do not chase further as tester once a root cause is named).

The template below is real, not illustrative filler to delete before first use.
