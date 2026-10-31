# PLAN: AGENTIC-UNIFY, one console thread and one brain for the AI side panel

Status: owner answered card v2 and crew ruled three PRs, 31 Oct 2026. Mock v1 being filed; PR 1 (leak fix only) in build. Full pipeline, size L.
Lane: AGENTIC-UNIFY, branch `crew/agentic-unify`, LEAD pattern.

Behaviour, facts and questions live in the two cards; nothing is stated twice here. UAC
(`agentic-unify-acceptance-criteria.md`) is written from the answers, before any test.

## Architecture

- **Layer:** turn identity and routing. Parser input only for page context, never a post-parser override.
- **Shared mechanism:** one principal object the engine, lanes, router and agent read. One narrow-only staff identity at the API-key
  check. One per-turn lanes override.
- **Also fixes:** panel all-company reads, panel per-person permission on reads, the knowledge tool seeing the staff member, the
  report engine for staff, the console's global switch flip. Agent tools added for the panel also reach WhatsApp staff.
- **Removes:** Agent tab, `/agent/turn`, two Reset buttons, `_lanes_on`. After default: `respond()` and the panel's second write path.

## Slices (assuming the recommended answers)

**PR 1: leak fix only**

1. Staff identity on API-key reads, ungated. UAC: `agentic-unify-pr1-acceptance-criteria.md`. Can only narrow. Security-reviewer scope.
   - **MCP:** one place, `CRMClient.request` (`sorento_crm_mcp/http_client.py:121-126`), reads the live MCP request's headers through the MCP
     library's request context, so hand-written tools with no `ctx` are covered (`server.py:504-1665`, `record_actions.py:89`, `ideation.py:109`).
   - **Identity:** one helper used by `get_current_user_or_api_key` (`dependencies.py:679-692`), `get_external_api_user` (`:622-649`). It returns
     the staff member's dict, so every `current_user["id"]` reader (own scope, field gates, module guards) applies at once, with `key_user_id` kept.
   - **Gates:** AND of both users in `require_permission_with_api_key` (`:547`), `require_any_permission_with_api_key` (`:584-617`), the handler check
     at `sla/sla_tracking.py:87`. A no-op dependency for the slug table in AC-13, except on an identity read.
   - **Company:** `company_scope_resolver.py:358-362`, validating the header itself because it runs before auth.
   - **Record context:** `record_context_service.py:43-48`, plus the own-scope check.

The console switch flip belongs to lane CONSOLE-SWITCH-OVERRIDE; later PRs build on its override API once merged.

**PR 2: console one thread + staff principal + panel (rollout permission `system.ai_assistant_chat.agent`, granted to nobody)**

2. Console backend: `force_agent` on `/console/turn` with a `forced` reason; merged thread read; agent reads recent bot replies;
   remove `/agent/turn`.
3. Console frontend: move step and card components out of `AgentConsole.tsx`; one thread, one New conversation, composer toggle.
4. Principal object at the seams listed in the card; panel envelope built from scratch; `panel-<conversation id>` key; outbound refusal.
5. Permission checks for in-process lane reads (count first).
6. Page context layer: parser, agent prompt, Jev state. Byte-parity test with the layer absent.
7. **Live panel turn (owner Q1):** audit every switch keyed on a live turn for the staff principal (ordering, phone gate, stock asks,
   salesman job, escalation draw, usage, session, frames, profile facts, idea and opportunity saves, file delivery, reminders). Each gets a
   decision and a test. No WhatsApp send. Escalation is delivered to a real team or person, or it does not write; if the target needs a
   product choice, one ask to the owner.
8. Panel backend: route split, confirm, cancel, withdraw routes gated by `ai_assistant_chat.use`; replies stored as panel messages;
   session state on the thread.
9. Panel frontend: render WhatsApp formatting via `WhatsAppText` (owner Q3: no raw `*` or `_`), `TurnAttachments`, write cards; pill and
   steps for trace viewers; 375 and 1280.

**PR 3: ported agent tools (owner Q2: general tools, before the pilot)**

10. Reads: complaints, SLA tracking, projects, order analytics, find, capability. Writes: complaint close, order cancel, IT ticket. Guides
    from AGENTIC-KNOWLEDGE #2036.
11. `crm_report_ask` staff branch (or in PR 2 if the stock and report examples need it first). Its route is off identity today, so the
    invoiced and unpaid gates (`services/sales/invoiced_sales.py:342,360`) ask one user. A staff path must make them ask both, or the header widens.

**Then:** labelled real panel questions run through both paths; pilot; default; retire `respond()`.

## Must check before the pilot

- Rate limit key when the operator is None (`CHAT/agent/loop.py:600-611`).
- Non-streaming panel POST against an agent turn of up to 45 s (proxy and client timeouts).
- Parser budget: TOTAL_CAP 1800 est. tokens (`turn/context.py:32`) against a 6000-char page snapshot.
- Which CI jobs run the parser gates (`test_parser_user_block_parity.py`, `test_prompt_pin.py`).

## Test notes

- Panel tests pinned to `respond()`: about 103. With the rollout permission absent that path is unchanged except for the leak fix, so
  those failing beyond the leak fix is itself a signal.
- `tests/test_mcp_runtime_client_auth.py:88` pins at least five `staff=True` constructions.
- Global guards if a table or list endpoint changes: `tests/test_schema_uuid_id_principle.py`, `tests/test_list_pagination_limit.py`.

## Coordination

AGENTIC-IDEATE (router, ideas to agent), AGENTIC-KNOWLEDGE #2036 (guides tool), NO-OPENAI #2035 (AI settings).
This lane merges main before each ready gate.
