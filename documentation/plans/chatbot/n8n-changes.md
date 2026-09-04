# n8n changes, per slice - Chatbot Turn Engine

Plan: `documentation/plans/chatbot/PLAN-chatbot-turn-engine.md`
UAC: `documentation/plans/chatbot/chatbot-turn-engine-acceptance-criteria.md`

**This file is the n8n half of the cut, written by whoever ships the CRM half, executed by
the owner.** Every slice moves logic out of n8n; the CRM change lands first and is inert,
then the n8n edit below switches the traffic over. Nothing here is automated: the prod n8n
instance is edited by hand, so each section is written at NODE level - which node, what it
becomes, and what proves it worked - rather than as prose.

Two rules that apply to every section:

- **The CRM ships first and OFF.** A slice's CRM code is behind a flag or an unread
  response field until the n8n edit is made, so the two can be deployed in either order and
  a bad slice is reverted by turning the flag off, not by re-editing n8n under pressure.
- **A cutover has a named precondition.** It is written in the section. "It looks right" is
  not one.


---

## S2 - `sub-output` moves into the CRM

**CRM side (shipped, inert until n8n calls it).** `POST /api/v1/external/chat/turn/{turn_id}/complete`
runs the whole tail: `build-outcome`, `escalate-catalog`, the CS member offer (roster read
included, in process), `compile-current-state` and `crossdomain-compose`. It writes the
session itself and closes the turn. Nothing calls it until step 2 below, so the CRM half
can deploy days before the n8n half and change nothing.

**After this slice the CRM is the ONLY writer of `respond_contacts.session_vars` on the
turn path (D2).** That is the point of S2 and the thing AC-207's grep proves.

### The request body IS the `sub-output` trigger contract

`sub-output`'s `When Executed by Another Workflow` declares thirteen inputs. The HTTP node
sends twelve of them under the same names, plus `ctx` (optional - the CRM already stored it
on the turn row at `/turn`, and sending it anyway means the expressions below are copied
from the existing caller unchanged):

| field | expression, copied VERBATIM from `Call 'sub-output'` |
| --- | --- |
| `item` | `={{ $json }}` |
| `ctx` | `={{ $('build-ctx').first().json.ctx }}` |
| `result` | `={{ $('build-result').isExecuted ? $('build-result').first().json : null }}` |
| `resolved` | `={{ $('resolve-entity').isExecuted ? $('resolve-entity').first().json : null }}` |
| `gate` | `={{ $('disallowed-entity-gate').isExecuted ? $('disallowed-entity-gate').first().json : null }}` |
| `offer_hold` | `={{ $('offer-hold-reply').isExecuted ? $('offer-hold-reply').first().json : null }}` |
| `suggest_offer` | `={{ $('build-suggest-offer').isExecuted ? $('build-suggest-offer').first().json : null }}` |
| `not_found` | `={{ $('not-found-error-message').isExecuted ? $('not-found-error-message').first().json : null }}` |
| `incoming_picker` | `={{ $('annotate-incoming-picker').isExecuted ? $('annotate-incoming-picker').first().json : null }}` |
| `access_choice` | `={{ $('access-level-choice-message').isExecuted ? $('access-level-choice-message').first().json : null }}` |
| `crossdomain_render` | `={{ $('crossdomain-render').isExecuted ? $('crossdomain-render').first().json : null }}` |
| `answer` | `={{ $("Call 'sub-answer'").isExecuted ? $("Call 'sub-answer'").first().json : null }}` |
| `clarify` | `={{ $('clarify-company-reply').isExecuted ? $('clarify-company-reply').first().json : null }}` |

The body is `extra = "forbid"`: a field the tail does not read is a 422 naming it, not a
silent drop, so a caller whose expectations have drifted says so on the first turn.

**The producers that live in `sub-main-processing` ride on `item.outcome_fragment`.**
`build-outcome`'s RS-6.1c mechanism already exists for exactly this and needs no new field:
a key PRESENT in `item.outcome_fragment` is taken verbatim and the producer is never asked
for. The keys that must be there are the ones `sub-output`'s graph does not contain:
`central-exchange`, `validator`, `promo-picker`, `crossdomain-zeroset`,
`build-miss-member-offer`, `dym-annotate-partial`, `dym-annotate`, `build-ideate-reply`.
If `sub-main-processing` already stamps them (it does on the lanes that moved), nothing
changes; if a lane does not, its key is absent and the CRM computes null for it, which is
the same value `_one` returns today.

### The response

```
200 {
  turn_id,
  reply: { text, quick_replies, result_set, attachments_src },
  actions: [],           // S2 still delegates every lane; the caller only sends
  session_patch          // ONLY on a dry run (is_test / test_run_id), else null
}
```

`reply` carries four FIELDS rather than the sealed patch, because that is what turns each
downstream expression into one read (see step 3).

### Step 1 - the HTTP node, inside `sub-output` (`qa4LWvPrhUnAPgjC`)

The cut is made INSIDE the sub rather than at its caller, so `sub-main-processing` and the
spine are untouched and the rollback is one workflow.

1. Add an `httpRequest` node `crm-complete-turn` after `When Executed by Another Workflow`:
   - method `POST`, credential `crm-n8n-auth` (the same header auth every other CRM call
     uses), URL
     `=https://fe-sorento.foundryx.my/api/v1/external/chat/turn/{{ $json.turn_id }}/complete`,
   - body `specifyBody: json`, `jsonBody` = the thirteen fields above,
   - `retryOnFail: false`. **Deliberate:** the tail WRITES the session, and a retry after a
     partial failure would re-run a turn the CRM may already have completed. The CRM's own
     idempotency covers a genuine duplicate (a second `/complete` replays the first answer
     and writes nothing), but an n8n-level retry is the wrong place to decide that.
2. `turn_id` must reach the sub. `sub-output`'s trigger gains a fourteenth input
   `turn_id` (`type: string`), and every `Call 'sub-output'*` caller sets it to the
   `turn_id` the S1 `httpRequest` node returned (AC-110 - the node that replaced
   `get-session-vars` through `route-turn` on the spine). The spine already carries that
   value; nothing new is computed for it.

### Step 2 - re-emit, so nothing downstream moves

3. Replace `crossdomain-compose`'s body with a one-line re-emitter, keeping the NAME:

   ```js
   // RS-5: the tail moved into the CRM. This node exists only so the two by-name readers
   // below resolve, exactly as the S1 cut kept `build-ctx` and `route-turn` as names.
   return [{ json: { reply: $('crm-complete-turn').first().json.reply } }];
   ```

4. DELETE, in this order (each is now dead): `item-restore`, `entry-gate`,
   `escalate-catalog`, `cs-offer-gate`, `cs-roster-plan`, `get-cs-members`,
   `build-cs-member-offer`, `build-outcome`, `compile-current-state`, `build-ctx`, and
   ten of the eleven `g-*` gates with their carrier stubs: `g-result`/`build-result`,
   `g-resolved`/`resolve-entity`, `g-gate`/`disallowed-entity-gate`,
   `g-offer_hold`/`offer-hold-reply`, `g-suggest_offer`/`build-suggest-offer`,
   `g-not_found`/`not-found-error-message`,
   `g-incoming_picker`/`annotate-incoming-picker`,
   `g-access_choice`/`access-level-choice-message`, `g-answer`/`Call 'sub-answer'`,
   `g-clarify`/`clarify-company-reply`.

   **`g-crossdomain_render` and `crossdomain-render` are the ONE pair that stays**, and
   the gate stays WITH the carrier rather than being simplified away: `send-attachments`'
   `xd` input reads `$('crossdomain-render').isExecuted ? ... : null`, so the gate is what
   keeps `isExecuted` false on the turns where the real node did not run. Delete the gate
   and the carrier runs on every turn; delete the carrier and the expression throws on the
   NAME rather than returning null. After the deletions the wiring is
   `trigger -> crm-complete-turn -> g-crossdomain_render -> (true) crossdomain-render ->
   crossdomain-compose`, with the gate's FALSE arm going straight to `crossdomain-compose`.

5. DELETE `save-session-vars`. This is the line AC-207 is about: after it goes, no
   workflow on the turn path writes `respond_contacts.session_vars`.

### Step 3 - the two senders read one field each

6. `sorento-sub-respond-sendmsg-respond2`'s inputs change from three expressions that dig
   into the sealed patch to three that read the response:

   | input | from | to |
   | --- | --- | --- |
   | `message` | `$('crossdomain-compose').first().json.reply.text ?? null` | `={{ $('crm-complete-turn').first().json.reply.text ?? null }}` |
   | `quick_reply` | `$('crossdomain-compose').first().json.reply.quick_replies` | `={{ $('crm-complete-turn').first().json.reply.quick_replies }}` |
   | `result_set` | `$('crossdomain-compose').first().json.reply.session_patch.variables.last_result_set` | `={{ $('crm-complete-turn').first().json.reply.result_set }}` |

   The third is the one that matters: `session_patch` is no longer on the wire, so a
   reader that digs into it would get `undefined` and send an empty list silently.

7. `send-attachments`' inputs:

   | input | from | to |
   | --- | --- | --- |
   | `reply` | `$('crossdomain-compose').first().json.reply` | `={{ $('crm-complete-turn').first().json.reply }}` |
   | `attachments_src` | `$("Call 'sub-answer'").isExecuted ? ($("Call 'sub-answer'").first().json.outcome_fragment \|\| {})['central-exchange'] : null` | `={{ $('crm-complete-turn').first().json.reply.attachments_src }}` |
   | | (this is why `Call 'sub-answer'` can be deleted in step 2: the CRM computes the same value from the `answer` field it was sent) | |
   | `xd` | `$('crossdomain-render').isExecuted ? $('crossdomain-render').first().json : null` | unchanged |
   | `ctx` | `$('build-ctx').first().json.ctx` | `={{ $('When Executed by Another Workflow').first().json.ctx }}` |

   `xd` keeps its `crossdomain-render` read, which is why that carrier survives step 2.

### AC-207's proof, and it is a grep, not a judgement

From the n8n repo, after re-exporting:

```bash
python scripts/export-workflows.py --verify
grep -rn "conversation-variables" n8n-workflows-init/export/*/workflow.json
```

**Exit condition: every hit is a GET.** A `"method": "PUT"` within the same node object as
a `conversation-variables` URL, in ANY exported workflow, means a session writer survived
and S2 is not done. The GETs are `get-session-vars` on the spine (which the CRM's S1 cut
already replaced on the live spine, and which other workflows still use legitimately).

Second grep, for the deleted bodies:

```bash
grep -rln "compile-current-state\|escalate-catalog\|build-cs-member-offer" n8n-workflows-init/export/
```

Only `clone-*` and `*-live` archived exports may match. A hit in `sub-output-live` means
step 2 was not completed.

### Precondition for the promote

- `pytest tests/chatbot -q` green in the CRM, including the 166-world replay.
- The clone smoke set (15 turns) run against the S2 build: same lane and same reply text
  as the pre-S2 baseline, zero egress (AC-208 asserts the persisted `session_vars` too).
- Gate 0 not blocked (`tests/chatbot/COVERAGE.md`; the blocking set is pinned EMPTY in
  `tests/chatbot/test_coverage_fresh.py::EXPECTED_BLOCKING`). Cleared on 5 Sep by the
  `sub-output-live` capture batch: 305 real captures off the shipping body, from a pool
  scanned end to end (760 of 760 on version `c32698c1`), which is what earns `exhausted`
  for the arms that still read zero.
- The captures themselves merged from the n8n capture worktree into the sibling checkout,
  or `test_coverage_fresh.py` skips its comparison with a message saying so.

### Rollback

Steps 2 and 3 are destructive, so the rollback artefact is **the `sub-output` workflow JSON
exported immediately before step 2**. Re-import it and the sub answers from its own nodes
again; the CRM's `/complete` endpoint stays deployed and unreferenced, which is harmless -
it writes nothing unless it is called.

**The one thing a rollback does NOT undo:** turns already completed by the CRM wrote their
session through `/complete`. Those sessions are the same shape n8n wrote (the patch is
persisted verbatim, `variables` plus `user_response` plus `quick_reply`), with one addition
- the R3 `pending` marker. The S1 head reads BOTH forms (AC-106), so a rolled-back n8n
reads those sessions correctly and simply ignores the extra key.

### Not covered by this slice

- `sub-sendmsg` and `sub-send-attachments` themselves stay in n8n (D9: n8n sends).
- The `actions[]` vocabulary is returned but empty at S2 except the `update_contact_fields`
  clear the head raises (AC-108). The assign / comment actions arrive with S5.
- `chatbot_reply_access_denied` and `chatbot_reply_offer_hold`, two of the seven keys
  AC-302 names, are NOT registered here. `access_denied` has no `escalate-catalog` case at
  all (it falls through the switch to an empty response) and `offer_hold`'s text is
  computed upstream by `offer-hold-reply` rather than canned. Inventing copy for either
  would be inventing behaviour; they land with their lanes at S3 and S5.
