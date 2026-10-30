# PLAN: Agentic P3 - write actions in the console Agent tab

Status: Phase 2 slice 1 (red tests first). Full track (migration, new write surface, acts as the linked user).
Lane AGENTIC-P2-CARD, PR #1999, branch `claude/agentic-p2-auto-routing-3npqem` (base main; P1 #1982 merged).
Card and owner answers: `CARD-agentic-p2-p3-30oct.md`. Acceptance criteria: `UAC-agentic-p3-writes-30oct.md`.

Process note: crew instructed "start P3 red-first" (30 Oct). The console change is small (a proposal block with
Confirm / Cancel in the existing Agent tab). It is built after the backend slice, against the endpoint contract
below, instead of as a Phase 1 mock first. The PR body names this deviation.

## Owner rulings this plan carries

- One request, one confirmation (P1 R5; card rule 1, up to 20 records per proposal).
- 6a: general, composable tools with server-side permission checks; no hard-coded per-request flows. A write
  tool mirrors one existing screen operation (its route), the model composes reads and writes.
- 7b: the Agent switch alone. No new contact grant. A write needs the switch on, a linked active user, and that
  user's own permission slug for the operation, then the route's own scope rules.
- 9a: in chat the confirmation is read semantically by the model, inside server limits. The console also shows
  Confirm / Cancel buttons.
- 10b: writes first, in the console Agent tab. Routing (P2, Jev) after.
- 8a + both directions: dealer-contact role changes (Business owner <-> Employee) and resign, read semantically.
  W0's permission waits for the owner's reply (crew); W0 is slice 3, not built until then.

## Slices

| Slice | Content |
| --- | --- |
| 1 | The write foundation (proposal, ledger, confirm / cancel, re-check, actor) + W1 customer asks (read + update) |
| 2 | W2 sales opportunities (read, stages, create, update) |
| 3 | W0 dealer-contact role / resign (after the owner's permission reply) |
| 4 | Console proposal UI + browser pass |
| 5 | W3 purchase-request decision through `dispatch_or_defer` (grace window) |

## Design

### 1. A write tool is one existing route, called in process as the linked user

`agent/writes.py` (new). A `WriteDef`:

```python
@dataclass(frozen=True)
class WriteDef:
    name: str                       # model-facing tool name
    user_permission: str            # the route's own slug (checked at exposure, proposal and execution)
    schema: dict                    # model-facing JSON schema (ids must come from this turn's results)
    read_before: Callable[[db, user, args], dict]   # the record as it is now (the precondition + summary input)
    summary: Callable[[dict, dict], str]            # (args, before) -> one plain line, built by code
    execute: Callable[[db, user, args], dict]       # calls the route function; returns {"id", "after"}
    record_key: str                 # the arg naming the record ("ask_id", "opportunity_id"); "" for a create
```

`execute` calls the route function the screen calls (precedent: `lanes/business/services._resolve_entity` calls
`resolve_reference_post` in process), with:
- `current_user` = `dependencies._load_user_dict_from_db(db, ctx.user_id)` (the same dict a session resolves to);
- every route parameter passed explicitly (a FastAPI `Query(...)` default is an object, not a value, when the
  function is called directly);
- the session's company scope set to the USER's scope (`company_scope_resolver._scope_for_user(db, user_id,
  None)`), not the contact scope P1 reads use, and restored after;
- the audit actor stamped: `AuditActor(actor_type="user", user_id=real_user_id=<linked user>,
  auth_method="agent", contact_id=<contact pk>, tool_name=<write name>)` (`app/audit_context.py:47`).

So the route's own scope rules apply unchanged (customer asks: `_patch_scope`, `customer_asks.py:135`;
opportunities: `_load` / `_assert_still_theirs`, `opportunities.py:57,84`). The agent re-checks only the slug
the route's `Depends(require_permission(...))` would have checked, because that dependency does not run on a
direct call. A route `AppException` / `HTTPException` becomes the step's error text (status + message, no
internals). Reads the writes need (W1 list, W2 list / meta) run the same way, as the user, in process.

Slice 1 tools:

| Tool | Effect | Route function | Slug |
| --- | --- | --- | --- |
| `crm_customer_asks_list` | read | `customer_asks_todo` (`api/v1/sales/customer_asks.py:80`), `agent_id` = None or "all" | `sales.customer_asks.view` |
| `crm_customer_ask_update` | write | `customer_asks_update` (`customer_asks.py:196`), body `StockAskUpdate` (`state: open|done`, `note`) | `sales.customer_asks.edit` |

Slice 2 tools: `crm_opportunities_list` (`list_opportunities`, `opportunities.py:133`), `crm_opportunity_meta`
(stages, `get_meta`), `crm_opportunity_create` (`create_opportunity`, `SalesOpportunityCreate`),
`crm_opportunity_update` (`update_opportunity`, `SalesOpportunityUpdate`, `opportunities.py:259`). Slugs
`sales.opportunities.view` / `.add` / `.edit` (`opportunities.py:36-38`).

### 2. A write call does not write: it adds a step to the turn's proposal

In `loop.run_agent_turn`, a write tool call is checked (registry, slug now, args against the schema, ids from
this turn's results, P1 `_check_ids`) and then `read_before` runs. Failure of any check = a normal typed
`denied` / `invalid` / `error` result to the model. Success = a step `{tool, args, before, summary}` added to
the turn's proposal and the tool result `{"status": "proposed", "action_id", "step": n, "summary"}`.

At the end of the turn, if the proposal has steps, one `chatbot.agent_actions` row is stored (status
`proposed`), any older `proposed` row of the same contact is set `expired`, and the reply is the model's answer
text followed by the code-built proposal block:

```
I will make these changes when you confirm:
1. <summary line>
2. <summary line>
Reply yes to go ahead, or tell me what to change.
```

At most 20 steps; a 21st write call gets `invalid` "At most 20 changes per confirmation."

### 3. Confirming and cancelling

Two ways, one server function `actions.confirm(db, ctx, action_id, *, via)` / `actions.cancel(...)`:
- Console: `POST /system/chatbot/agent/actions/{id}/confirm` and `/cancel` (body `{contact_respond_id}`,
  same permission as `/agent/turn`).
- Chat (9a): local tools `confirm_action {action_id}` and `cancel_action {action_id}`, offered to the model only
  when the contact has a `proposed` action. The model decides from the user's message.

Server limits on confirm, all must hold, else nothing is written and the reason is returned:
- the action belongs to this contact and is the newest `proposed` one;
- not expired (`created_at` + 10 minutes; constant `ACTION_TTL_MINUTES`);
- chat only: the confirming turn is a later turn than the proposing one (`turn_id` differs);
- the entry rules still hold (`build_context`: switch on, AI replies on, linked active user, same user as the
  action's `user_id`).

Execution, in step order:
1. Re-check every step BEFORE writing anything: the user still holds each step's slug; `read_before` again and
   compare with the stored `before` on the fields the step changes plus `updated_at` when the record has one.
   Any difference -> the whole action is `rejected` with the step and what changed; nothing written.
2. Claim: `UPDATE ... SET status='executing' WHERE id=:id AND status='proposed'`; zero rows = already handled
   (idempotent; a double click or a second "yes" does nothing).
3. Run each step's `execute`. A step error stops the run: earlier steps stay done (each route commits its own
   write), later steps are `skipped`. Status `executed` (all done) or `partial`, per-step status in `steps`.
4. Reply built by code from the steps (done / failed with reason / skipped).

### 4. The ledger: `chatbot.agent_actions`

One table, one migration (`agp3_0001_agent_actions`, id <= 32 chars, on main's current head):
`id` uuid pk; `conversation_id` uuid; `turn_id` uuid (proposing turn); `confirm_turn_id` uuid null;
`contact_respond_id` String(64) indexed; `user_id` String; `status` String(16) (`proposed | executing | executed
| partial | rejected | cancelled | expired`); `steps` JSONB (list of `{tool, args, before, summary, status,
result_id, error}`); `via` String(16) null (`console | chat`); `created_at`, `decided_at`, `finished_at`
timestamptz. `__audit_skip__` like `ChatbotTurn`; the domain writes are audited by their own listeners.

Undo is not a mechanism: a read tool `crm_agent_actions_recent` (this contact's last 10 actions with
before / after per step) lets the model see what it did, and "undo that" becomes a normal proposal of the
inverse writes, confirmed like any other.

### 5. Responses

- `AgentTurnResponse` gains `pending_action: {id, lines: [str], expires_at} | null`.
- `GET agent/conversation` turns gain the same `pending_action` for the turn that proposed it, with its current
  status.
- `POST agent/actions/{id}/confirm|cancel` -> `{action_id, status, reply_text, steps: [{summary, status,
  error}]}`; refusals -> 409 `{"detail": {"code": "action_refused", "reason": ...}}` with reasons
  `not_found | not_newest | expired | not_proposed | entry_refused | changed`.

### 6. Never a write tool (unchanged from the card)

Only `WriteDef`s in the registry exist. No delete, no order cancel, no prices / costs / stock / finance, no
users / roles / permissions / settings / prompts, nothing on the user's own linked contact, no outbound message
to a customer.

## Test list (tester writes these red, Postgres)

Slice 1 (`tests/chatbot/agent/test_agent_writes.py`, `test_agent_writes_routes.py`):
1. A write tool is exposed only when the linked user holds its slug; `crm_customer_ask_update` is absent for a
   user without `sales.customer_asks.edit`.
2. A write call during a turn writes nothing: the ask's state is unchanged after the turn, one
   `agent_actions` row `proposed` with one step, the reply ends with the proposal block, `pending_action` set.
3. Ids rule: an `ask_id` not seen in this turn's results is `invalid`, no step added.
4. Out of scope ask (another agent's customer, user without view_all): `read_before` 404 -> `denied` result, no
   step.
5. Console confirm executes: ask state `done`, note saved, action `executed`, step `done` with `result_id`,
   audit row actor = linked user with `auth_method="agent"`.
6. Changed since proposal (state flipped on screen before confirm): `rejected` reason `changed`, nothing written.
7. Slug removed between proposal and confirm: `rejected`, nothing written.
8. Expired (created 11 minutes ago): 409 `expired`.
9. Not newest: a second proposal expires the first; confirming the first -> 409 (`not_proposed`).
10. Double confirm: second call 409 `not_proposed`; the write ran once.
11. Cancel: status `cancelled`, nothing written; confirm after cancel -> 409.
12. Switch off between proposal and confirm: 409 `entry_refused`.
13. Chat confirm: in a LATER turn the model calls `confirm_action` -> executed; in the SAME turn as the proposal
    -> `invalid`, nothing written.
14. 21st write call in one turn -> `invalid`.
15. Partial: step 2 fails in the route (ask deleted between re-check and execute is hard to stage; use a
    route error injected through `execute`): step 1 done, step 2 failed, step 3 skipped, status `partial`.
16. Company scope: the write runs under the user's scope, not the contact's (a stub route records
    `get_company_scope(db)`).
17. Route test: confirm / cancel need the console permission (403 without), unknown action 404 / 409 shape.

Slice 2 adds: create + update through the same proposal path; Lost without reason -> the route's error becomes
the step error; a user limited to own opportunities cannot move one onto another agent (route rule).

FE (slice 4, vitest): the proposal block renders lines + Confirm / Cancel; Confirm calls the service and shows
the step results; buttons disabled while pending; expired / refused shows the reason.
