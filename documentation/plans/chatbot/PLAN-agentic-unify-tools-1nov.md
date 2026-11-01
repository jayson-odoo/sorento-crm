# PLAN: AGENTIC-UNIFY tools (PR 4 of 4)

Status: fix round built, green locally, re-review running. Run A done, its one-row miss with the owner. Run B held for the owner: no DB with a Jev key yet. Browser pass paused by the owner. 2 Nov 2026. Planned 1 Nov 2026. Full track: permission gates and writes. No migration, no new screen, so no mock. Branch `crew/agentic-unify-tools`, worktree `sorento_crm-agentic-unify-2`, based on #2060. PR opens after #2060 merges, because a stacked PR gets no CI until retargeted.

UAC: `agentic-unify-tools-acceptance-criteria.md`. Behaviour: `CARD-agentic-unify-v2-31oct.md` section 4, owner Q2 (a). `CHAT` = `sorento_crm_backend/app/services/chatbot`.

## Already done, so not in this PR

- Guides: `user_guides_read` is in `REGISTRY` on #2060 (`CHAT/agent/tools.py:86`), Agent 0.96 live. Crew asked only to confirm no other lane expects to own it.
- PR decide and opportunity: `CHAT/agent/writes.py:734, 1531`. Withdraw: `CHAT/agent/actions.py:358`, generic on `after.pending_action_id`.
- All twelve reads have routes on `STAFF_READ_ROUTES`, measured by resolving each catalog entry against `app.routes`. So no backend route work and no identity work.

## Ruling after the security review, 2 Nov: panel only

Security reviewer FAIL at f057a34f25, checked by the lead. On console and WhatsApp turns the route runs as the shared key, so the agent's one slug was the only guard, and it missed per-route rules: a different slug on unfiltered event logs, a buyer's phone following the act-as user, the forecast falling to the default company, order totals skipping the sales reveal. Crew ruled **(a) panel only**: these tools are offered only on a staff-principal turn, where the route runs as the user and its rules hold. One condition instead of about seven gates, and it can never reach WhatsApp.

**Deferred from card Q2: "WhatsApp staff gain them too".** Trigger for later: run these reads as the linked user on non-panel turns, audited tool by tool. Crew tells the owner in the morning summary; the owner may overrule.

The second reviewer added, all checked: capabilities dropped (its route needs a package the deployed image does not hold, and its body is cut to a count); the ticket gated on `tickets.tickets.edit`, since a user without it cannot finish the draft; "the contact will be told" only when there is a contact; an empty find backs a `not_found` claim; the label filter and the tool gate share one predicate; `crm_complaints_list`'s catalog text corrected, because the route's default is oldest first.

This supersedes below: fact 1's `own_permission` condition (no panel check needed), the operator check, fact 9's project brand denial, and the `combine` and brand refusal on the finds, all removed. Fact 2's labels hold on panel turns only. The `left_out` prompt line must not name these tools on other turns, because it would tell a slug holder "outside access".

## ARCHITECTURE

- **Layer.** Reads are rows in `REGISTRY` (`CHAT/agent/tools.py:69`), the one table of MCP reads, dispatched by `_dispatch_inner` (`:961`). Writes are `WriteDef`s in `WRITES` (`CHAT/agent/writes.py:283`), the one write path. No new registry, no new lane, no parser domain, no router text, no MCP tool.
- **Shared mechanism.** Propose, Confirm, re-check, execute through the route's own function, as `_pr_execute` (`writes.py:1477`) does it. `waiting_of` and `withdraw` already handle any parked form action. Identity comes from `_mcp_call` (`lanes/business/services.py:338`): staff principal gets the staff client and blank pair, everything else the shared client and contact pair.
- **Classes fixed, not shapes.** Three classes: a read no chat lane answers (Jev must hear of it), a read whose route has own scope (safe only when the route runs as the user), a write that parks in a grace window.

## Measured facts that shape the design

1. **`.view_own` is safe on a panel turn only.** On a non-panel turn the route runs as the shared key's user (`services.py:343`), and `complaint_own_scope` narrows to that user, not the linked one. An any-of gate there would pass a `.view_own` holder into a read the route does not narrow for them. Hence `ToolDef.own_permission`, honoured only when `staff_principal.current()` is set (AC-2).
2. **Jev is not told about `REGISTRY` reads.** `agent_tool_labels` (`router.py:295`) lists writes and user reads only, "the bot answers those lookups too". The bot does not answer complaints, SLA or projects: they are in `UNDOMAINED_CHATBOT_TOOLS` (`contracts.py:65`). Without a label those questions depend on router text we may not reword. Hence `PORTED_READS`, listed to Jev (AC-8). `crm_find` and capabilities are left out: the first overlaps `crm_products_find` and the bot's lookups; a capability question is not a domain.
3. **No search on two catalog tools, on purpose.** `get_complaints` and `list_projects` take `query`, but `sorento_crm_mcp/tests/test_catalog_compile.py:107` forbids a fuzzy `query` on entity list tools (UUID-first contract), so the catalog stays closed. My first draft added it; the tester found the guard. A number or code still has to find its row, and a write needs the id. `crm_resolve` is not the place: a new default kind could change resolution on every existing turn. So two `UserRead`s, the precedent being `crm_purchase_requests_list` and `crm_contacts_find` (`writes.py:378`): in process, the route function, as the user, own scope right on every turn. PR 4 then has no MCP code change.
8. **Two reads were off the chatbot's allow-list.** `crm_order_analytics` and `crm_find` are not in `CHATBOT_READ_ONLY_TOOLS`, so `_mcp_call` refuses them. Both are plain GETs. They join `UNDOMAINED_CHATBOT_TOOLS` (`contracts.py:65`).
9. **Projects carry no brand.** Rows name no product, so the brand guard cannot narrow `crm_projects_list` or `crm_project_detail`. The forecast is already refused for a scope naming a brand (`contact_brand_scope.py:217`, crew ruling (b)); the project reads join it, same reason, same trigger: per-brand project scoping. No lane calls them, so nothing else moves.
4. **Order rows carry no UUID, by design** (`catalog.py:607`). So `crm_order_cancel` takes `order_number` and its `read_before` finds the row. No new read tool. Complaint rows do carry `id`, so complaint close follows the `_check_ids` rule like PR decide.
5. **Complaint close parks** (`complaints.py:1484`, `dispatch_or_defer`, `cx.finalize`, `tells_contact=True`) and has a revision fence on the route dependency. Copy `_pr_execute`: browser-channel `Request`, `assert_revision_current`, the same `JSONResponse` to parked-dict mapping. Consider one small helper only when the second caller is in hand here, not before.
6. **Order cancel does not park** and its route slug is `orders.view` (`orders.py:1220`). Same gate as the screen today; see question 1.
7. **The ticket route is key-only** (`external/it_support_tickets.py`), so the write calls `TicketIntakeService(db).submit` in process with the user as actor. Title required, so `_draft_via_llm` never runs. `note_in_reply=True` carries `draft_url`, the existing rule for a link the model must not invent. Non-panel turns pass no conversation id.

## Changes

| File | Change |
| --- | --- |
| `CHAT/agent/tools.py` | `ToolDef.own_permission`. Twelve `REGISTRY` rows. `NON_RENDER_TOOLS` gains all but `crm_find`. `PORTED_READS`. Labels. A small `_tool_permitted` used by `user_may_use` and `_dispatch_inner` (slug, or own slug on a panel turn, plus the operator for `PORTED_READS`). Capabilities joins the no-slug branch beside `GUIDES` |
| `CHAT/router.py` | `agent_tool_labels` adds `PORTED_READS` |
| `CHAT/agent/writes.py` | Three `WriteDef`s with `read_before`, `summary`, `execute`, `changes`. Two `UserRead`s, `crm_complaints_find` and `crm_projects_find`, with `combine` |
| `CHAT/contracts.py` | `crm_order_analytics` and `crm_find` in `UNDOMAINED_CHATBOT_TOOLS` |
| `documentation/user-guides/_shared/ai-assistant-side-panel.md` | From #2060. Drop "Not on this path yet"; add the new questions and the three changes. Same PR, per the guide rule |

Merge with #2053: it rewrites `agent_tool_labels(db, user)` and adds `CONTACT_TOOLS`, an allow-list, so ported reads stay off contact principals with no change here. Whichever lands second carries the labels through its per-user filter: a contact with no linked user gets none. Test pinned once both are in.

## Slices

1. **Reads.** Tester red from AC-1 to AC-8 with the compiled MCP cases; coder green.
2. **Writes.** Tester red from AC-9 to AC-14; same coder.
3. **Live and gate.** AC-16, AC-17 on a crew copy; reviewer, security-reviewer, browser pass in parallel; hand test script; `crew-done` with a DoD gate.

## Test list for the tester

- Per AC-1 row: offered with the slug, not offered and refused without, on real role rows, because `check_user_has_permission` passes every admin.
- `.view_own` only: panel offered and route narrows to own rows; console refused. Kill by removing the panel condition.
- Operator lacking the slug on console: refused, for each `PORTED_READS` name.
- MCP compiled tool, one case per tool per shape, with the worktree MCP first on `sys.path` (the venv's editable install points at the primary checkout). All 24 pass on the catalog as it is: they pin it, they do not need a change.
- Finds: a number finds its row and its id joins the turn's ids; `.view_own` gets own rows only, on panel and console; operator combine; a scope naming a brand refuses; unknown number is `empty`.
- A scope naming a brand: each project read refused through `_mcp_call`.
- Raw route shape: `{"data": []}` is `empty`; a big list is capped and counted; analytics buckets with no rows; a dict body with an error.
- `agent_tool_labels` holds the new labels and the stored prompt row is untouched; a guard that every `PORTED_READS` name has a label and is read only.
- Complaint close: every refusal in AC-10; Confirm parks; withdraw leaves status unchanged and sends nothing, with the Respond send patched and asserted not called; a revision bumped after the card is refused; own company only.
- Order cancel: unknown number, already cancelled, another company's order, AutoCount-owned order as the service treats it; Confirm sets the flag through `cancel_order`; complaint re-evaluation still runs.
- Ticket: DRAFT status, raiser is the user not the shared key's user, no LLM call, link in the reply by code.
- Card and steps carry no UUID, for all three writes.

## Jev gate (AC-17)

Baseline A is today's text with today's labels, fixed; B adds the labels. Run each arm as a full-permission user and as a low-permission one: since #2053 merged, `agent_tool_labels(db, user)` sends a low-permission user a short or empty `tools` list, and rounds 6 and 7 of #2060 only measured the full list. Baseline rows are the existing panel and WhatsApp set (68/75 on A). New rows are fresh paraphrases across complaints, SLA, projects, analytics and the three writes, written before any run and never tuned against. **Bar:** no fewer than A on the baseline rows, and at least 80 percent Agent on the new rows. Below the bar, stop and report, no rewording. Runner stops on two busy replies or any 429. Jev only, cheap, and budget asked of crew first: the 1 Nov cap is spent.

## Crew rulings, 1 Nov (ask a29175772)

1. **Order cancel slug: same as the screen.** The agent mirrors the route's `orders.view`; no agent-only slug (owner ruling 30 Oct: agent writes check permissions through the P1 tools, Confirm before write). The PR body says the route is gated on `orders.view` (`orders.py:1220`) and that the route fix belongs with #1754.
2. **Every copy counts as ABLE to send WhatsApp.** The complaint close live step runs only on a test contact with Respond egress blocked (proxy env, verified), or it is covered by a mocked Respond test instead. Never against a real contact. Ask crew to check the copy's Respond creds before that step. The hand test script says the same.
3. **Live budget.** Org key caps stand: USD 2 a day all lanes, USD 0.25 a run, x1. 1 Nov is spent, so AC-16 and AC-17 run under the 2 Nov cap, ledger before and after. Estimate approved for 2 Nov (a29286280): Run A, Jev gate, about 0.009 USD; Run B, 10 live turns, about 0.14 USD with a stop at 0.25; x1. When slices 1 and 2 are green, `crew report --ask` for a copy on this worktree; crew brings it up and checks its Respond creds and egress block before the complaint close step.
4. **Guides stay in #2060.**
5. **#2053 has the owner's merge go and lands first.** PR 4 merges main after it and carries `agent_tool_labels` through its per-user filter (`router.py:295`).
