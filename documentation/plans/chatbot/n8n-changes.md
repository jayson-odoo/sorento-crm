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

## S4 - the `low_signal` lane moves into the CRM

**CRM side (shipped, and NOT inert - read this first).** Unlike S6a there is no flag. S4
takes `low_signal` out of `DELEGATED_BRANCH_KINDS`, so from the moment the CRM deploys,
`POST /api/v1/external/chat/turn` answers a low-signal turn itself: `delegate` is `null`,
`reply.text` carries the clarifier's answer, and `actions` carries one `send_message`.

That means **the CRM and n8n edits are NOT independent for this slice**, and the order is
fixed: **n8n first, CRM second.** Until the spine stops calling `sub-casual-llm`, a
low-signal turn gets a `delegate: null` it does not act on, and n8n answers it the old way
- correct, but the clarifier has now run TWICE (once in the CRM, once in n8n) and the
customer waits for both. Nothing is sent twice and nothing is corrupted; it is latency and
one wasted model call per low-signal turn, for as long as the two deploys are apart.

### Which turns this covers

One `route` output. `route[11]` is the `low_signal` arm and it is the only path to
`Call 'sub-casual-llm'`.

| `route` output | node it feeds today | CRM `branch_kind` |
| --- | --- | --- |
| 11 `low_signal` | `Call 'sub-casual-llm'` | `low_signal` |

### Step 1 - shadow window (no wiring change)

Deploy the CRM and change nothing in n8n. Every low-signal turn now runs the clarifier in
both places and n8n's answer is the one the customer sees.

**Precondition to proceed:** over at least 20 low-signal turns, `chatbot.turns` rows with
`branch_kind = 'low_signal'` show `status = 'done'` and a non-empty `response -> reply ->
text`, and **zero** rows with `stage = 'casual_llm' AND status = 'failed'`. The query:

```sql
SELECT status, stage, count(*)
FROM chatbot.turns
WHERE branch_kind = 'low_signal' AND created_at > now() - interval '7 days'
GROUP BY 1, 2;
```

A `failed` / `casual_llm` row is the lane saying it could not reach the clarifier, and its
`error` column says why. Do not proceed with any.

### Step 2 - the wiring change, in `sorento-consume-main` (`S4N1LiisAqA4hpMC`)

Three nodes go, one arrives.

| node | today | after |
| --- | --- | --- |
| `Call 'sub-casual-llm'` | executeWorkflow -> `sub-casual-llm` (`4dPJ8ykop8VIpddY`) | **DELETE** |
| `casual-gate` | IF on `$json._casual_error === true`; true arm terminal, false arm -> `Call 'sub-answer'1` | **DELETE** |
| `Call 'sub-answer'1` | executeWorkflow -> `sub-answer` (`oIzFAzi3bGgn5mTH`) | **REPLACE with a one-line Code node of the SAME NAME** |

The replacement keeps the name on purpose. `Call 'sub-output'6` maps its `answer` input as
`{{ $("Call 'sub-answer'1").isExecuted ? $("Call 'sub-answer'1").first().json : null }}`,
and that expression is shared with the arms this slice does not touch. Keeping the name
means **no edit to `sub-output`'s mapping at all** - the same trick AC-110 uses for
`build-ctx` and `route-turn`.

New `Call 'sub-answer'1` body (Code node, run once for all items):

```js
// S4: the CRM already answered. `sub-answer` used to parse the clarifier's JSON here
// (`central-exchange`); the CRM does that now and hands back the finished text.
return [{ json: { response: $('route-turn').first().json.reply.text } }];
```

`route-turn` is S1's re-emitter of the `/chat/turn` response. If the reply is exposed under
a different name when S1 is wired, use that name - the point is `response.reply.text` from
the one HTTP call, not this specific node.

Rewire: `route[11]` -> the new `Call 'sub-answer'1` -> `Call 'sub-output'6`. Both edges
already exist for the second hop; only the first changes, from
`route[11] -> Call 'sub-casual-llm'`.

**What happens to the error arm.** `casual-gate` exists to catch `_casual_error`, which
`mark-casual-error` sets when `sub-error-logger2` has ALREADY sent the error text from
inside the sub. That whole path goes: the CRM's failed lane returns the same
`sub-error-logger` text as `reply.text` plus a `send_message` action, so the error is sent
by the same outbound as any other reply and there is nothing to gate on. This is the
behaviour change to watch in step 1, and it is why the precondition counts failed rows.

### Step 3 - unpublish

`sub-casual-llm` (`4dPJ8ykop8VIpddY`) has no other caller once step 2 lands. Deactivate it;
do not delete it, so the rollback below is a re-activation rather than a rebuild.

`sub-answer` (`oIzFAzi3bGgn5mTH`) **STAYS ACTIVE.** `Call 'sub-answer'1` was one of several
callers; the business lane still uses the others, and its `central-exchange` node is still
what parses those answers. Only this caller goes.

### Rollback

Re-activate `sub-casual-llm`, restore the three deleted nodes and point `route[11]` back at
`Call 'sub-casual-llm'`. The CRM needs no revert to make that safe: with n8n answering
again the CRM's own reply is simply unused, which is exactly the step-1 shadow state.

If a revert has to be instant and n8n cannot be edited, the CRM-side equivalent is to put
`"low_signal"` back into `CRM_COMPLETED_BRANCH_KINDS`'s complement - i.e. remove it from
that frozenset in `contracts.py` - which restores `delegate: "low_signal"` and makes the
spine's old path authoritative again. That is a deploy, not a toggle; the n8n rollback is
faster and is the one to reach for.

### Not covered by this slice

- **The session write.** `Call 'sub-output'6` still runs and still persists the turn's
  session vars. S4 does not touch it; S2's `/complete` is what replaces it, and until then
  a low-signal turn's memory is written by n8n exactly as today. The CRM marks the one call
  site for it with `TODO(S2-merge)` in `engine._run_casual_lane` rather than writing a
  partial session, because a half-written session is read by the NEXT turn.
- **The other `casual`-ish arms.** `clarify_menu`, `out_of_scope` and `not_supported` are
  canned-reply arms and belong to S3; they still go to `Call 'sub-output'6` untouched.

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
