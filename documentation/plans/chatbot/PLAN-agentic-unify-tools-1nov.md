# PLAN: AGENTIC-UNIFY tools (PR 4 of 4)

Status: Plan, 1 Nov 2026. Full track: permission gates and writes. No migration, no new screen, so no mock. Branch `crew/agentic-unify-tools`, worktree `sorento_crm-agentic-unify-2`, based on #2060. PR opens after #2060 merges, because a stacked PR gets no CI until retargeted.

UAC: `agentic-unify-tools-acceptance-criteria.md`. Behaviour: `CARD-agentic-unify-v2-31oct.md` section 4, owner Q2 (a). `CHAT` = `sorento_crm_backend/app/services/chatbot`.

## Already done, so not in this PR

- Guides: `user_guides_read` is in `REGISTRY` on #2060 (`CHAT/agent/tools.py:86`), Agent 0.96 live. Crew asked only to confirm no other lane expects to own it.
- PR decide and opportunity: `CHAT/agent/writes.py:734, 1531`. Withdraw: `CHAT/agent/actions.py:358`, generic on `after.pending_action_id`.
- All twelve reads have routes on `STAFF_READ_ROUTES`, measured by resolving each catalog entry against `app.routes`. So no backend route work and no identity work.

## ARCHITECTURE

- **Layer.** Reads are rows in `REGISTRY` (`CHAT/agent/tools.py:69`), the one table of MCP reads, dispatched by `_dispatch_inner` (`:961`). Writes are `WriteDef`s in `WRITES` (`CHAT/agent/writes.py:283`), the one write path. No new registry, no new lane, no parser domain, no router text, no MCP tool.
- **Shared mechanism.** Propose, Confirm, re-check, execute through the route's own function, as `_pr_execute` (`writes.py:1477`) does it. `waiting_of` and `withdraw` already handle any parked form action. Identity comes from `_mcp_call` (`lanes/business/services.py:338`): staff principal gets the staff client and blank pair, everything else the shared client and contact pair.
- **Classes fixed, not shapes.** Three classes: a read no chat lane answers (Jev must hear of it), a read whose route has own scope (safe only when the route runs as the user), a write that parks in a grace window.

## Measured facts that shape the design

1. **`.view_own` is safe on a panel turn only.** On a non-panel turn the route runs as the shared key's user (`services.py:343`), and `complaint_own_scope` narrows to that user, not the linked one. An any-of gate there would pass a `.view_own` holder into a read the route does not narrow for them. Hence `ToolDef.own_permission`, honoured only when `staff_principal.current()` is set (AC-2).
2. **Jev is not told about `REGISTRY` reads.** `agent_tool_labels` (`router.py:295`) lists writes and user reads only, "the bot answers those lookups too". The bot does not answer complaints, SLA or projects: they are in `UNDOMAINED_CHATBOT_TOOLS` (`contracts.py:65`). Without a label those questions depend on router text we may not reword. Hence `PORTED_READS`, listed to Jev (AC-8). `crm_find` and capabilities are left out: the first overlaps `crm_products_find` and the bot's lookups; a capability question is not a domain.
3. **No search on two catalog tools.** `get_complaints` and `list_projects` take `query`; the catalog does not expose it (`catalog.py:1291, 1659`). A number or code cannot find its row, and a write needs the id from a result. Add the one param to each.
4. **Order rows carry no UUID, by design** (`catalog.py:607`). So `crm_order_cancel` takes `order_number` and its `read_before` finds the row. No new read tool. Complaint rows do carry `id`, so complaint close follows the `_check_ids` rule like PR decide.
5. **Complaint close parks** (`complaints.py:1484`, `dispatch_or_defer`, `cx.finalize`, `tells_contact=True`) and has a revision fence on the route dependency. Copy `_pr_execute`: browser-channel `Request`, `assert_revision_current`, the same `JSONResponse` to parked-dict mapping. Consider one small helper only when the second caller is in hand here, not before.
6. **Order cancel does not park** and its route slug is `orders.view` (`orders.py:1220`). Same gate as the screen today; see question 1.
7. **The ticket route is key-only** (`external/it_support_tickets.py`), so the write calls `TicketIntakeService(db).submit` in process with the user as actor. Title required, so `_draft_via_llm` never runs. `note_in_reply=True` carries `draft_url`, the existing rule for a link the model must not invent. Non-panel turns pass no conversation id.

## Changes

| File | Change |
| --- | --- |
| `CHAT/agent/tools.py` | `ToolDef.own_permission`. Twelve `REGISTRY` rows. `NON_RENDER_TOOLS` gains all but `crm_find`. `PORTED_READS`. Labels. A small `_tool_permitted` used by `user_may_use` and `_dispatch_inner` (slug, or own slug on a panel turn, plus the operator for `PORTED_READS`). Capabilities joins the no-slug branch beside `GUIDES` |
| `CHAT/router.py` | `agent_tool_labels` adds `PORTED_READS` |
| `CHAT/agent/writes.py` | Three `WriteDef`s with `read_before`, `summary`, `execute`, `changes` |
| `sorento_crm_mcp/sorento_crm_mcp/catalog.py` | `query` on `crm_complaints_list` and `crm_projects_list`, with its line in each description |

Merge with #2053: it rewrites `agent_tool_labels(db, user)` and adds `CONTACT_TOOLS`, an allow-list, so ported reads stay off contact principals with no change here. Whichever lands second carries the labels through its per-user filter: a contact with no linked user gets none. Test pinned once both are in.

## Slices

1. **Reads.** Tester red from AC-1 to AC-8 with the compiled MCP cases; coder green.
2. **Writes.** Tester red from AC-9 to AC-14; same coder.
3. **Live and gate.** AC-16, AC-17 on a crew copy; reviewer, security-reviewer, browser pass in parallel; hand test script; `crew-done` with a DoD gate.

## Test list for the tester

- Per AC-1 row: offered with the slug, not offered and refused without, on real role rows, because `check_user_has_permission` passes every admin.
- `.view_own` only: panel offered and route narrows to own rows; console refused. Kill by removing the panel condition.
- Operator lacking the slug on console: refused, for each `PORTED_READS` name.
- MCP compiled tool, one case per tool per shape, with the worktree MCP first on `sys.path` (the venv's editable install points at the primary checkout).
- Raw route shape: `{"data": []}` is `empty`; a big list is capped and counted; analytics buckets with no rows; a dict body with an error.
- `agent_tool_labels` holds the new labels and the stored prompt row is untouched; a guard that every `PORTED_READS` name has a label and is read only.
- Complaint close: every refusal in AC-10; Confirm parks; withdraw leaves status unchanged and sends nothing, with the Respond send patched and asserted not called; a revision bumped after the card is refused; own company only.
- Order cancel: unknown number, already cancelled, another company's order, AutoCount-owned order as the service treats it; Confirm sets the flag through `cancel_order`; complaint re-evaluation still runs.
- Ticket: DRAFT status, raiser is the user not the shared key's user, no LLM call, link in the reply by code.
- Card and steps carry no UUID, for all three writes.

## Jev gate (AC-17)

Baseline A is today's text with today's labels, fixed; B adds the labels. Baseline rows are the existing panel and WhatsApp set (68/75 on A). New rows are fresh paraphrases across complaints, SLA, projects, analytics and the three writes, written before any run and never tuned against. **Bar:** no fewer than A on the baseline rows, and at least 80 percent Agent on the new rows. Below the bar, stop and report, no rewording. Runner stops on two busy replies or any 429. Jev only, cheap, and budget asked of crew first: the 1 Nov cap is spent.

## Questions for crew, none blocking the build

1. **Order cancel slug.** Route gate is `orders.view`, so anyone who can view an order can cancel it, on the screen and on the panel today. (a) Same as the screen, with the Confirm as the gate. (b) Require an edit slug on the agent only. **Recommend (a):** chat stricter than the screen helps little while the route stays open. The route's gate belongs with #1754. Security-reviewer sees this line.
2. **Copy and WhatsApp.** A complaint close tells the contact through Respond. Can a copy send it? Unanswered for email too. The hand test needs a test contact or a confirmed block. Blocks only that live step.
3. **Live budget** for AC-16 and AC-17.
