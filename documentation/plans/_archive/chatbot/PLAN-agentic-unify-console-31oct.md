# PLAN: AGENTIC-UNIFY console, one thread

Status: merged as #2051 (6fa5ef4ef0), 1 Nov 2026. Full pipeline, size M. PR 2 of 4 (crew ruling): #2048 leak fix, this, staff principal + panel, ported tools.
Lane: AGENTIC-UNIFY, branch `crew/agentic-unify-console`, off origin/main, independent of #2048. UAC: `agentic-unify-console-acceptance-criteria.md`.

## Architecture

- **Layer:** the console surface and its turn route. No prompt or parser change.
- **Shared mechanism:** one route for every console turn; one thread read over `chatbot.turns`.
- **Also fixes:** agent turn without a trace link, repeated bubble keys, the agent blind to the bot's replies.
- **Removes:** Agent tab, `ChatbotConsoleTabs`, `AgentConsole`, `useAgentConsole`, `POST /agent/turn`, two reset buttons.

## Backend

`CHAT` = `sorento_crm_backend/app/services/chatbot`.

1. `force_agent` on `ConsoleTurnRequest` (`schemas/chatbot_turn.py:135-148`); `run_console_turn` (`CHAT/console_service.py`) skips `decide_route` and stamps `side=agent, reason=forced`. Media with it: 422.
2. Thread read, under `api/v1/system/chatbot.py`: this contact's console turns for the run plus the current agent conversation's turns, ordered, carrying route (from the `route` trace stage), steps (`CHAT/agent/memory.py:153-199`), actions. Reuses the conversation read's shapes (`schemas/chatbot_turn.py:342-359`).
3. `CHAT/agent`: recent bot replies of the run reach the agent's context. The run id must reach `_run_agent_side` (`console_service.py`, it gets none today).
4. Remove `POST /agent/turn` (`chatbot.py:712-744`) and its tests, moving what they prove to `/console/turn`.

## Frontend

`CON` = `sorento_crm_frontend/app/(protected)/system-management/chatbot-console`.

5. Move `StepsDisclosure`, `ReasoningItem`, `ReplyMeta`, `ProposalActions`, `ActionsBlock`, `WaitingStep`, `ActionOutcome` (`CON/components/AgentConsole.tsx:91-400`) to their own file, bodies unchanged.
6. `useChatbotConsole` carries the thread: run id per contact in localStorage, thread read on load, decisions, one reset. Service layer stays: UI, hook, service, `api-client`.
7. `MessageBubble` renders the moved parts; composer toggle; `RoutePill` reason word; delete tabs and `AgentConsole`.

## Test notes

- FE tests to move with the code: `AgentConsole.{proposal,reasoning,visibility,withdraw}.test.tsx`, `AgentConsole.test.tsx`, `agentConsoleService.test.ts`.
- BE tests calling `/agent/turn`: `tests/chatbot_eval/test_agent_engine.py`, `tests/chatbot/agent/test_agent_{reasoning,writes,round3,round8,}routes.py`.
- Global guards: a new list-shaped read means `tests/test_list_pagination_limit.py`.
- Vitest touched files only, `--maxWorkers=2`. Browser pass at 1280 and 375 on a crew test copy.
