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
- W0 permission (owner 30 Oct ~11:15, "agree with your catch on 7b"): a new slug `user_management.contacts.edit_own`
  (seeded granted to no role, like `pp2_0001_view_own_perms`, and registered in `app/rbac/permission_registry.py`).
  The holder may change role / resign only for contacts linked (`respond_contact_customers`) to customers whose
  `sales_agent_id` is one of the user's own active sales agents (`sales/portal_agent.agents_for_contact` on the
  user's `respond_contact_id`). Holding the general `user_management.contacts.edit` also allows it, for any
  contact, as the access sheet does today.

## Slices

| Slice | Content |
| --- | --- |
| 1 | The write foundation (proposal, ledger, confirm / cancel, re-check, actor) + W1 customer asks (read + update) |
| 2 | W2 sales opportunities (read, stages, create, update) |
| 3 | W0 dealer-contact role (both ways) / resign, under `user_management.contacts.edit_own` |
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
- `GET agent/conversation` gains a top-level `pending_action` (`{id, lines, expires_at, turn_id}` or null): the
  contact's current proposal, so a reloaded console still shows Confirm / Cancel under the proposing turn.
  `pending_action` on `/agent/turn` carries `turn_id` too.
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

## Build contract, slice 1 (tester and coder both read this; tests import these names)

`app/models/chatbot_agent.py`: model `AgentAction`, table `chatbot.agent_actions`, columns as section 4
(`steps` JSONB not null default `[]`). Migration `agp3_0001_agent_actions` (down_revision = main's current head).

`app/services/chatbot/agent/writes.py`:

```python
@dataclass(frozen=True)
class WriteDef: name, user_permission, schema, read_before, summary, execute, record_key   # section 1

WRITES: dict[str, WriteDef]          # slice 1: exactly {"crm_customer_ask_update"}
USER_READS: dict[str, ...]           # in-process reads as the user: "crm_customer_asks_list", "crm_agent_actions_recent"
def permitted_writes(db, ctx) -> list[WriteDef]          # WRITES the linked user holds the slug for
def run_as_user(db, ctx, fn: Callable[[dict], Any], *, tool_name: str | None = None) -> Any
    # loads the user dict, sets the USER's company scope (company_scope_resolver._scope_for_user) and the
    # audit actor (actor_type "user", auth_method "agent", contact_id ctx.contact_pk, tool_name), calls
    # fn(user_dict), restores the previous scope and actor even on error
def propose_step(db, ctx, name: str, args: Any, *, seen_ids: set[str]) -> tuple["ToolResult", dict | None]
    # checks in order: name in WRITES else denied; slug now else denied; args dict and keys within
    # schema properties else invalid; ids rule (P1 `_check_ids`) else invalid; read_before under run_as_user
    # (route 404/403 -> denied with the route's message, other errors -> error). Success -> (ToolResult with
    # status "proposed", data {"summary"}), step {"tool", "args", "before", "summary", "status": "proposed"}
```

Tester's resolved points (31 Oct red round): ids in `USER_READS` results join the turn's seen ids;
`confirm_action` / `cancel_action` are exempt from the ids rule (the action id is checked by `confirm`); a confirm
in the proposing turn is `invalid` (the row is stored at turn end); an unknown action id is 409 `not_found`; a
route `AppException` message appears verbatim in the step error; the changed-record error names the field.

`app/services/chatbot/agent/actions.py`:

```python
ACTION_TTL_MINUTES = 10
MAX_STEPS = 20
class ActionRefused(Exception):
    reason: str   # not_found | not_newest | expired | not_proposed | entry_refused | changed | same_turn
@dataclass
class ActionOutcome:
    action_id: str
    status: str            # executed | partial | rejected | cancelled
    reply_text: str
    steps: list[dict]      # [{"summary", "status": done|failed|skipped|proposed, "error"}]
def store_proposal(db, ctx, *, conversation_id: str, turn_id: str, steps: list[dict]) -> AgentAction
    # expires any older `proposed` action of the contact; returns the new row (status proposed)
def pending_action(db, contact_respond_id: str) -> AgentAction | None   # newest proposed, not expired
def proposal_lines(action) -> list[str]
def confirm(db, contact_respond_id: str, action_id: str, *, via: str, turn_id: str | None = None,
            now: datetime | None = None) -> ActionOutcome
    # raises ActionRefused for not_found / not_proposed / not_newest / expired / entry_refused / same_turn
    # (via == "chat" and turn_id == action.turn_id). A changed record or a lost slug is NOT raised: it
    # returns ActionOutcome(status="rejected") with the step's error naming what changed, nothing written.
def cancel(db, contact_respond_id: str, action_id: str) -> ActionOutcome   # proposed -> cancelled
```

Loop (`agent/loop.py`): write tools from `permitted_writes` and the `USER_READS` join the turn's schemas;
`confirm_action` / `cancel_action` (`{action_id: str}`) join only when `pending_action(...)` is not None. A write
call goes through `propose_step`; steps collect per turn; at most `MAX_STEPS` (the next gets `invalid`). After the
answer, steps -> `store_proposal` and the reply gets the proposal block (section 2).
`AgentTurnResult` gains `pending_action: dict | None` (`{"id", "lines", "expires_at"}`).

Routes (`api/v1/system/chatbot.py`, same permission as `/agent/turn`):
`POST /api/v1/system/chatbot/agent/actions/{action_id}/confirm` and `/cancel`, body `{contact_respond_id}`
-> 200 `{action_id, status, reply_text, steps}`; `ActionRefused` -> 409
`{"detail": {"code": "action_refused", "reason": ...}}`.

## Build contract, slices 2 and 3

Slice 1 landed at c7382e7d (`agent/writes.py`, `agent/actions.py`). Slices 2 and 3 add entries to `WRITES` and
`USER_READS`; nothing else in the proposal / confirm path changes.

### Slice 2: sales opportunities (W2)

| Tool | Kind | Route function (in process, as the user) | Slug |
| --- | --- | --- | --- |
| `crm_opportunities_list` | user read | `list_opportunities` (`api/v1/sales/opportunities.py:133`); args `query`, `status_ids`, `customer_ids`, `close_from`, `close_to`, `outcome`, `limit` (<= 50) | `sales.opportunities.view` or `.view_own` (the route's `READ`) |
| `crm_opportunity_meta` | user read | `get_meta` (stages with ids, lost reasons if any) | same |
| `crm_opportunity_create` | write | `create_opportunity`, body `SalesOpportunityCreate` (`app/schemas/sales.py:165`) | `sales.opportunities.add` |
| `crm_opportunity_update` | write | `update_opportunity` (`opportunities.py:259`), body `SalesOpportunityUpdate` (`:191`) | `sales.opportunities.edit` |

- `record_key`: `opportunity_id` for update, "" for create. A create's `read_before` is `{}` and its re-check
  only re-checks the slug.
- Summaries (code-built, no UUIDs): create `Create opportunity "<title>" for <customer code or prospect>, close
  <date>`; update `Opportunity "<title>": <field> <old> -> <new>` for each changed field, stage by its name.
- The route's own rules stay authoritative: Lost needs a reason, Won links a same-customer live sales order,
  `_assert_still_theirs` for own-scope users. Their error text becomes the step error.

### Slice 3: dealer-contact access (W0)

New slug `user_management.contacts.edit_own` ("Edit Own Dealer Contacts' Access": change role or end access only
for contacts linked to customers of your own sales agents). Migration `agp3_0002_contacts_edit_own` (insert-only,
guarded, granted to no role; pattern `pp2_0001_view_own_perms.py`) and a `permission_registry.py` entry.

**Scope rule** (`writes.contact_in_scope(db, user_id, contact_pk) -> bool`): true when the user holds
`user_management.contacts.edit`; else true when the contact has a `respond_contact_customers` link to a customer
whose `sales_agent_id` is one of the user's own active sales agents (`sales/portal_agent.agents_for_contact`
on `users.respond_contact_id`). Never true for the user's own linked contact (no self-escalation).
A tool is exposed when the user holds `.edit_own` or `.edit`.

| Tool | Kind | Behaviour |
| --- | --- | --- |
| `crm_contacts_find` | user read | `{phones: [str] 1..20}`. Each phone through `contact_setup_engine.normalise_phone` + `_find_contacts`. Per phone: `invalid_phone`, `not_found`, `ambiguous`, `not_yours` (exists, out of scope: no name, no id, nothing else), or `found` with `{contact_id, name, phone, companies: [code], role: owner|employee|none, chatbot_allowed, accounts: [{customer_id, code, name}]}`. Role: holds an owner type of one of its companies (`contact_access_sheet_service.TEMPLATE["owner_types"]`) = owner; holds `end_user` only = employee; none = none. `accounts` lists only links to the user's own agents' customers (all links for `.edit` holders). |
| `crm_contact_access_update` | write | `{contact_id, role?: owner|employee, chatbot_allowed?: bool, link_customer_ids?: [id], unlink_customer_ids?: [id]}`, at least one field. One general tool: "resign" is the model composing `chatbot_allowed=false` + `unlink_customer_ids` = the contact's accounts; "undo" is the inverse args. |

`crm_contact_access_update` rules, checked in `read_before` and again at confirm:
- `contact_in_scope` must hold, except for a re-link: a `link_customer_ids` entry is allowed for an out-of-scope
  contact only when this user's executed `agent_actions` show a step that unlinked this contact from that customer
  (the undo of a resign). Every linked / unlinked customer must be one of the user's own agents' customers
  (any customer for `.edit` holders).
- `role=owner`: insert the owner types of every company the contact holds, plus `end_user` if missing (the
  sheet's `_template_sets`, owner branch). `role=employee`: delete the owner types of every company, keep or
  add `end_user`. A contact with no company -> invalid "This contact has no company, so its role cannot be set."
- `chatbot_allowed`: the column on `respond_contacts`. Links: `contact_customer_service.link_customer` /
  `unlink_customer` (`:70`, `:132`).
- Execute in one transaction; audit event `contact.access_agent` with before / after per facet (pattern
  `contact_access_sheet_service` `audit_service` calls), actor = the user (`run_as_user`).
- Summary: `<phone> <name>: Employee -> Business owner (Sorento)`, `AI replies on -> off`, `unlinked from
  <customer code>`; a step whose args change nothing is `invalid` "Nothing to change for <phone>.".
- Before-state for the re-check: role, chatbot_allowed, the linked customer ids.

Card change (simplest thing): resign does NOT end the per-agent enquiry windows (`contact_agent_access`). With AI
replies off they have no effect, and leaving them keeps the undo exact.

### Tests, slices 2 and 3 (tester adds `test_agent_writes_opportunity.py`, `test_agent_writes_contacts.py`)

Slice 2: create via proposal + confirm (row exists, sales agent stamped, audit actor = user); update stage by
name in the summary; Lost without reason -> step failed with the route's message, nothing changed; own-scope user
moving an opportunity onto another agent's customer -> failed with the route's message; changed since proposal
-> rejected; list read under own scope shows only own rows.

Slice 3, using the owner's example shape (4 phones to Business owner, 1 resign; masked seed data):
1. find: found / not_found / ambiguous / not_yours / invalid_phone each; not_yours carries no name or id.
2. a proposal with 4 role steps + 1 resign step writes nothing; summaries show old -> new role and the resign.
3. confirm: owner types added per company, end_user kept; resign contact has chatbot_allowed false and no link
   to the user's customer; audit rows `contact.access_agent` actor = user.
4. downgrade owner -> employee removes owner types only.
5. scope: `.edit_own` holder on another salesperson's dealer contact -> denied; `.edit` holder -> allowed; own
   linked contact -> denied for both.
6. no slug (switch on, neither `.edit_own` nor `.edit`): tools not exposed.
7. undo of resign: a re-link of the contact to the same customer by the same user is allowed although the contact
   is now out of scope; a re-link by another `.edit_own` user, or to a customer it was never unlinked from, is
   denied.
8. a contact with no company -> invalid on role; nothing-to-change -> invalid.
9. migration seeds the slug once (re-run safe); registry lists it.

## Review round 1 (30 Oct): fixes, tester-first

Reviewer NOT READY (B1, B2), security reviewer NOT SECURE (blocker: console operator acts as another user).

R1. **Who may write from the console** (crew-ask filed; building the recommended (a) meanwhile): write tools are
    offered, and `confirm` / `cancel` accepted from the console, only when the operator (the console caller) IS
    the contact's linked user. Any other operator gets read tools only; a console confirm / cancel by another
    operator -> 409 reason `not_your_contact`. `agent_actions` gains `decided_by_user_id` (the operator, or the
    linked user for a chat confirm). `run_agent_turn` takes `operator_user_id` (None = chat, the sender is the
    user).
R2. **Chat confirm works across turns** (B1): while a proposal is pending, the system prompt carries one line
    naming it (`A change is waiting for the user's decision (action <id>): <lines joined by "; ">`), and the
    `confirm_action` / `cancel_action` schemas restrict `action_id` to that id (`enum`). The loop's same-turn
    `if steps:` guard is removed: confirming the previous turn's proposal in a turn that also proposes is fine
    (`store_proposal` expires nothing that is already executed).
R3. **Undo is buildable in a later turn** (B2): `crm_agent_actions_recent` returns, per step, `tool`, `args`,
    `result_id`, `before`, `after`, `status`, and only this linked user's actions (`user_id` filter); every id in
    it joins the turn's seen ids. The pending proposal on `GET agent/conversation` is filtered the same way.
R4. **Undo of a resign is exact** (security 2, reviewer 6): a step stores `unlinked_customer_ids` = the links it
    actually removed. A re-link of an out-of-scope contact is allowed only when (i) this user's executed step
    unlinked exactly that customer from that contact, and (ii) that unlink is still the latest change to the link
    (no later executed agent step re-linked it). Out of scope, only `link_customer_ids` (from (i)) and
    `chatbot_allowed: true` are accepted.
R5. **`edit_own` links only for the undo** (security 4; owner ruling is role / resign only): an `.edit_own`
    holder's `link_customer_ids` is accepted only under R4. `.edit` holders keep linking.
R6. **Company scope** (security 5): customer lookups and link checks run under the user's company scope (no
    `company_scope(db, None)`); an unlink that removed nothing fails the step ("<code> was not linked").
R7. **Summaries cannot be forged** (security 3): every value placed in a summary has whitespace (newlines, tabs)
    collapsed to single spaces; a note is shown in full when <= 200 characters, else its first 200 and
    "(N characters)"; case kept as written (reviewer 1: no `.capitalize()`).
R8. **Role per company** (reviewer nit): `role=owner` adds the missing owner types per company; it is "nothing to
    change" only when every company already has them.

Tests to add red first: two `run_agent_turn` calls where turn 2's model sees only history + system prompt and
confirms (R2); resign in turn 1, undo in turn 2 without hand-seeded ids (R3/R4); claim race: the row flipped to
`executing` from a second session between re-check and claim -> written once (reviewer 2); re-link refused for a
`.edit` holder who did not do the unlink (binding only, reviewer 4); re-link refused after a later re-link and
unlink by someone else (R4 ii); R1 console write tools absent and confirm 409 for another operator; R5, R6, R7, R8
one each.
