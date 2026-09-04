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

## S1 - the spine head moves into the CRM

**Written by the n8n owner session (help-crm), 5 Sep, and pasted here verbatim** so the
three slices' n8n halves live in one file in slice order. The CRM half shipped with S0+S1.

Spine head `get-session-vars -> Call 'sub-query-reformulator' -> check-access -> build-ctx -> route-turn` is replaced by `chat-turn` (httpRequest v4.3, POST https://fe-sorento.foundryx.my/api/v1/external/chat/turn, cred crm-n8n-auth, body `{envelope: {...<queue item>, media}}`, timeout 60 s, continueErrorOutput -> sub-error-logger) -> `head-arm` (Switch v3.4: `duplicate` [$json.duplicate true -> no successor], `finished` [$json.delegate ?? 'NONE' == 'NONE' -> send-crm-reply = sendmsg with reply.text], fallback `delegate` -> build-ctx) -> `build-ctx` (one line: re-emits {ctx: response.ctx}) -> `route-turn` (one line: re-emits response.item) -> existing `route` Switch. Old five nodes renamed `(pre-S1)`, disabled, edge-less, deleted at S8 (AC-802). Clone adds `is_test: true` inside envelope (G11) and retires the session-injection / mock-parser / chat-stateful session guards (G6/G8/G9) because those inputs now ride inside the envelope. Built as stage `s1` in the n8n repo's spine-next pipeline (branch feat/s1-chat-turn-head); active node count unchanged, +12 total until S8.

Precondition: the endpoint answers on fe-sorento (401/422 on an empty POST). Dry run writes exactly one `chatbot.turns` row (is_test true) and nothing else (D14); proof tests listed in the plan.

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

---

## S6a - `sub-resolve-and-gate` moves into the CRM

**CRM side (shipped, inert by default).** `POST /api/v1/external/chat/turn` now returns
`delegate_payload`: exactly the item `sub-resolve-and-gate` returns today - the four
`resolve-exit-*` arms' `_exit_kind` plus `resolved`, `gate`, `ctx_resolved`, `aggregate`,
`tier_gate`, `annotate_incoming` and that arm's own item. It is `null` unless
`CHATBOT_BUSINESS_LANE_ENABLED=true`, and null on every branch kind except the three that
reach the sub.

### Which turns this covers

`sorento-consume-main`'s `route` Switch has three outputs that reach the sub, and the CRM
lane covers exactly those three:

| `route` output | node it feeds | `entry` stamped | CRM `branch_kind` |
| --- | --- | --- | --- |
| 8 `check_promotion` | `tag-entry-access-check` | `access_check` | `check_promotion` |
| 11 `stock_denied` | the SPINE's `Edit Fields2` -> `tag-entry-resolve` | `resolve` | `stock_denied` |
| fallback `business_query` | `tag-entry-resolve` | `resolve` | `business_query` |

**There are TWO nodes called `Edit Fields2`**, one in the spine (row 11 above, which sets
`not_allowed_check_stock` before the tag) and one inside `sub-main-processing` (fed by
`ef2-gate`, which re-sets it from the trigger). Everything below is about
**`sub-main-processing`'s**. It stamps `not_allowed_check_stock: true` and it **STAYS**. `validator` reads it by
name and by node, not off the flowing item:

```js
if ($('Edit Fields2').isExecuted && $('Edit Fields2').first().json.not_allowed_check_stock) {
```

`$('Edit Fields2')` on a node that does not exist THROWS, so deleting it takes the whole
`stock_denied` answer path down. The CRM therefore does NOT stamp the field: nothing
downstream of the sub reads the item for it, and a CRM-side copy would be a second writer
of a value n8n still owns.

### Step 1 - shadow window (no wiring change)

1. Set `CHATBOT_BUSINESS_LANE_ENABLED=true` on the CRM. Nothing in n8n changes: it still
   calls `sub-resolve-and-gate` itself and still answers from it.
2. For a week of live traffic, compare each turn's `delegate_payload` with what
   `Call 'sub-resolve-and-gate'` returned on the same turn. The CRM writes the payload to
   `chatbot.turns.trace` under the `looked_up` record, so this is a query, not an
   instrumentation project.

**Precondition for step 2, and it is not negotiable:** zero `looked_up` records with
`status = failed`, and zero payload mismatches outside the two keys
`tests/chatbot/_corpus.py::CAPTURE_BODY_ADDITIONS` names. The shadow costs one extra
resolver call per business turn - that is the price of the window and the reason it is a
window and not the permanent state.

### Step 2 - the wiring change, in `sub-main-processing` (`53RxDSON8P3QSN22`)

The sub keeps its shape; only its FRONT changes. Today:

```
When Executed by Another Workflow -> build-ctx -> ef2-gate -> Edit Fields2 / item-restore
item-restore -> Call 'sub-resolve-and-gate' -> resolve-gate -> ... -> resolve-item -> resolve-arm
```

After:

1. **Add** a trigger input `resolve_payload` (type object) to
   `When Executed by Another Workflow`, beside the existing `ctx`, `item`,
   `not_allowed_check_stock`, `is_test`.
2. **Replace the body of `resolve-item`** (Code node, already the chain's item carrier)
   with a read of the trigger instead of the call:

   ```js
   return [{ json: $('When Executed by Another Workflow').first().json.resolve_payload }];
   ```

3. **Repoint the four presence gates and the five name-preserving stand-ins** from
   `$("Call 'sub-resolve-and-gate'").first().json.<key>` to
   `$('When Executed by Another Workflow').first().json.resolve_payload.<key>`. They are:

   | node | key it reads |
   | --- | --- |
   | `resolve-gate` (If) | `resolved` |
   | `aggregate-gate` (If) | `aggregate` |
   | `annotate-incoming-gate` (If) | `annotate_incoming` |
   | `resolve-entity` (Code stand-in) | `resolved` |
   | `disallowed-entity-gate` (Code stand-in) | `gate` |
   | `build-ctx-resolved` (Code stand-in) | `ctx_resolved` |
   | `Aggregate` (Code stand-in) | `aggregate` |
   | `tier-gate` (Code stand-in) | `tier_gate` |
   | `annotate-incoming-picker` (Code stand-in) | `annotate_incoming` |

   Rewiring alone does NOT redirect these - they are by-name reads (`TOPOLOGY.md`, "Read BY
   NAME"). The expression has to be edited too. This is the one step where a missed node
   fails silently: a stand-in that never executes makes every downstream
   `$('<name>').first()` throw, and the turn dies with a node-not-executed error rather
   than a wrong answer.

4. **Delete ONLY** `Call 'sub-resolve-and-gate'` (executeWorkflow) and `item-restore`
   (Code). Wire `Edit Fields2[0] -> resolve-gate` and `ef2-gate[1] -> resolve-gate`, so the
   stand-in chain still runs and still dominates its readers (LESSONS 91: a sibling has no
   ordering relation, so the chain cannot become a branch).

   **`ef2-gate` and `Edit Fields2` STAY.** `validator` reads `$('Edit Fields2').isExecuted`
   and `$('Edit Fields2').first().json.not_allowed_check_stock`, and `$('<name>')` on a
   node that does not exist throws - deleting the Set node takes the `stock_denied` answer
   path down with it, several nodes away from the edit, which is the worst shape a mistake
   here can have. `ef2-gate` is what decides whether it runs, so it stays for the same
   reason. Both are deleted at S6c with the rest of the lane (AC-610), when `validator`
   goes too.

### Step 3 - the caller, in `sorento-consume-main` (`S4N1LiisAqA4hpMC`)

5. On both `Call 'sub-main-processing'` call sites, add the input
   `resolve_payload: {{ $json.delegate_payload }}` (the CRM `/chat/turn` response the two
   re-emitters already read `ctx` and `item` from).
6. `tag-entry-resolve` / `tag-entry-access-check` stay for now: `entry` is inert once the
   CRM decides it, and leaving them costs nothing and keeps step 2 revertible. They are
   deleted at S6c with the rest of the lane (AC-610).

### Step 4 - unpublish

7. `sub-resolve-and-gate` (`tKeQUkZK5cFK9BFa`) is unpublished ONLY after a week with no
   rollback. Until then it stays published and unreferenced, which is what makes the
   rollback a one-field edit (`resolve_payload` back to the call's output).

### Rollback

Turn `CHATBOT_BUSINESS_LANE_ENABLED` off. The CRM returns `delegate_payload: null`, so
`resolve-gate` / `aggregate-gate` / `annotate-incoming-gate` all take their FALSE arms and
`resolve-arm` receives an item with no `_exit_kind`. **That is a dead turn, not a fallback**
- so if step 2 has already landed, the rollback is to re-add the
`Call 'sub-resolve-and-gate'` node and repoint the nine expressions back. Keep a copy of
the workflow JSON from before step 2; that is the actual rollback artefact.

### Not covered by this slice

- `probe-incoming` and `probe-customer-orders` still run in n8n's `sub-get-results` when
  the CRM lane is off. With it ON, the CRM's own probe seam raises (it needs S6b's
  `entity-ids-transformer` and `output-structurer`), which both annotators render as their
  documented UNPROBED arm: the customer picker ships bare with
  `customer_probe_skip_reason: 'probe_unavailable'`, and the incoming picker ships today's
  "None of these have incoming stock right now." **This is a real behaviour difference on
  picker turns and it is why step 1's shadow window must include picker traffic**; if it
  matters to the owner before S6b, S6a stays in shadow until S6b lands.
- The `resolve-exit-access-ask` arm has zero captured executions, in any slug (see
  `tests/chatbot/COVERAGE.md`). It is covered by unit tests, not by replay.
- **For S6b, one detail that will look like a port bug and is not:** `probe-incoming`'s
  `contact_id` parameter is `={{ $('build-ctx').first().json.ctx.contact.id }} ` with a
  TRAILING SPACE, and `probe-customer-orders`' is not. Whatever S6b builds the tool
  arguments with has to decide whether to reproduce that or normalise it, and say which;
  today it reaches `sub-get-results` as a string with a space on the end.
- **`resolve-entity` carries `retryOnFail` in n8n and the port has no retry.** A transient
  resolver failure that n8n survived is a shadow-lane failure here. Named in the plan's S6a
  section; the shadow window is what says whether it matters.
