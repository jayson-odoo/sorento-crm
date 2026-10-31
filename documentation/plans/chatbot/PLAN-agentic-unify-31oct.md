# PLAN: AGENTIC-UNIFY, one console thread and shared routing for the AI side panel

Status: card v1 filed 31 Oct 2026, waiting on owner answers (Q1-Q5 in `CARD-agentic-unify-31oct.md`). Full pipeline, size L.
Lane: AGENTIC-UNIFY, branch `crew/agentic-unify`, LEAD pattern.

This plan is deliberately short until the card is answered: the card holds the behaviour, the file:line facts and the
questions, so nothing is stated twice. UAC (`agentic-unify-acceptance-criteria.md`) and the slices below are firmed up
from the answers.

## Slices (one branch, one PR, assuming the recommended answers)

1. **Console, backend:** `force_agent` on `POST /system/chatbot/console/turn` with a `forced` route reason; merged thread
   read; agent memory reads recent bot replies; remove `POST /agent/turn`.
2. **Console, frontend:** move the agent step and write-card components out of `AgentConsole.tsx`; one thread, one New
   conversation, the composer toggle; remove `ChatbotConsoleTabs` and the Agent tab.
3. **Staff principal:** `staff:<user_id>` key through `decide_route`, `run_agent_turn`, `build_context`, audit actor;
   contact gates off for that principal; panel history fed to the router; per-turn page context and active company.
4. **Narrow-only staff identity on API-key reads** (`require_permission_with_api_key`, `_resolve_api_key_scope`, MCP
   header pass-through, `report_ask` staff branch). Security-reviewer scope.
5. **Panel, backend:** route split in the chat endpoint behind `system.ai_assistant_chat.agent`; panel routes for confirm,
   cancel, withdraw; agent replies stored as panel messages; agent conversation mapped to panel thread (one nullable
   column); separate usage feature names.
6. **Panel, frontend:** render the write cards; pill and steps for trace viewers; 375 and 1280.

## Must check before the pilot

- Panel MCP list against the agent's 23 tools.
- Labelled panel message set (crew labels, run against Jev, same bars as P2).
- Rate limit key when the operator is None (`CHAT/agent/loop.py:600-611`).
- Non-streaming panel POST against an agent turn of up to 45 s (proxy and client timeouts).

## Test notes

- Panel pipeline tests with direct coupling: about 103 (`tests/test_ai_write_confirm.py` and friends). With the rollout
  permission absent the path is unchanged, so they must stay green untouched; that is itself a test of the switch.
- `tests/test_mcp_runtime_client_auth.py:88` pins at least five `staff=True` constructions.
- Global guards on the new column: `tests/test_schema_uuid_id_principle.py`, `tests/test_list_pagination_limit.py`.

## Coordination

AGENTIC-IDEATE (router criteria from the registry), AGENTIC-KNOWLEDGE #2036 (new tool), NO-OPENAI #2035 (AI settings).
Merge order decided at PR time; this lane merges main before its ready gate.
