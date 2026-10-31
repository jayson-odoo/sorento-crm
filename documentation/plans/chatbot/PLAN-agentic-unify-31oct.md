# PLAN: AGENTIC-UNIFY, one console thread and one brain for the AI side panel

Status: card v2 filed 31 Oct 2026, waiting on owner Q1-Q3 (`CARD-agentic-unify-v2-31oct.md`) and crew's call on three PRs. Full pipeline, size L.
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

**PR 1: leak fix + console**

1. Staff identity on API-key reads, ungated: `require_permission_with_api_key` (`dependencies.py:524`), `_resolve_api_key_scope`,
   MCP pass-through, `staff_user_id` from every panel call site. Can only narrow. Security-reviewer scope.
2. Per-turn lanes override replacing `_lanes_on` (`console_service.py:257-289`).
3. Console backend: `force_agent` on `/console/turn` with a `forced` reason; merged thread read; agent reads recent bot replies;
   remove `/agent/turn`.
4. Console frontend: move step and card components out of `AgentConsole.tsx`; one thread, one New conversation, composer toggle.

**PR 2: staff principal + panel (rollout permission `system.ai_assistant_chat.agent`, granted to nobody)**

5. Principal object at the seams listed in the card; panel envelope built from scratch; `panel-<conversation id>` key; outbound refusal.
6. Permission checks for in-process lane reads (count first).
7. Page context layer: parser, agent prompt, Jev state. Byte-parity test with the layer absent.
8. Usage on the panel path; honest replies where a test-path lane previews an action.
9. Panel backend: route split, confirm, cancel, withdraw routes gated by `ai_assistant_chat.use`; replies stored as panel messages;
   session state on the thread.
10. Panel frontend: `WhatsAppText`, `TurnAttachments`, write cards; pill and steps for trace viewers; 375 and 1280.

**PR 3: ported agent tools**

11. Reads: complaints, SLA tracking, projects, order analytics, find, capability. Writes: complaint close, order cancel, IT ticket.
12. `crm_report_ask` staff branch (or in PR 2 if the stock and report examples need it first).

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
