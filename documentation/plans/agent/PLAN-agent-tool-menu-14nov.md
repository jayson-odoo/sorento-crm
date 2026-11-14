# PLAN: Agent short tool menu + "find more tools" (AGENT-CONTEXT-BUDGET slice 2)

Status: UAC filed for crew sign-off, 14/11/2026. No code yet. Size M (no migration, no permission change,
no new ingest surface; touches the agent loop). Parent plan: `PLAN-agent-context-budget-14nov.md` (v2,
owner D1 = (c), 14/11/2026 19:27). UAC: `agent-tool-menu-14nov-acceptance-criteria.md`.
Paths: BE = `sorento_crm_backend/app/`. Read from `main` 752a23d5.

## Why

The agent sends its full list of ~54 tools (99,300 chars, ~24,800 tokens, chars/4 estimate) on every step
of every staff question: 92 % of step 1. Measured on 60 stored turns: with a 29-tool list the biggest
step was 13,400 tokens against 30,700 with the full list, and the answer came 2.3 s sooner. The owner
chose (D1): a short core set always, plus a step to load the rest when needed, as Claude Code does.

## What exists today (reuse, do not duplicate)

| Piece | Where | Use |
|---|---|---|
| Round-1 tool list assembly | `services/chatbot/agent/loop.py:2082-2122` (offered, reads, writes, batch, plan, answer) | split into core + directory here; nothing else changes |
| Permission filter for the list | `access.py:244-248` `permitted_tools`, `writes.py:487-512` | reused as is: the directory is built only from what these return |
| Call-time permission check | `tools.py:1489-1521` (`dispatch`), contact guard `loop.py:2316-2323` | unchanged: a call is checked by name against the permitted lists, never against what was sent |
| Narrowing after a query / quotation lines / agent resolve | `loop.py:88-145` `narrow_after_query`, `loop.py:2481` | retired: with a short core set there is nothing to narrow, and a list that only grows keeps the provider cache prefix stable |
| Tool label per name (plain words) | `TOOL_LABELS` (`loop.py`, used at `:1398`) | first source of a directory line when present |
| Dealer flow list | `loop.py:1697` `dealer_schemas` | unchanged |
| Confirm removed from step 2 on | `loop.py:2224-2227` | unchanged (safety rule) |
| Trace per step | `loop.py:1991-2007` (`tools_offered`, `tool_schema_chars`) and `_context_record` `loop.py:1320` | add the loaded tool names; used to check the targets |

## Design (simplest thing that works)

1. **Core set** (staff principal only: panel, console linked user, WhatsApp linked user), each only if the
   user may use it: `plan`, `answer`, `crm_tools_load` (new), `crm_query`, `crm_describe`, `crm_resolve`,
   `crm_knowledge_search`, `user_guides_read`; plus the confirm / cancel tools when a change is waiting
   (as today); plus the tools this conversation's previous agent turn called (question Q1).
2. **`crm_tools_load`**: its description is the directory, one line per other tool the user may use:
   `name: one line` (the tool's label, else the first sentence of its description, at most 100 chars).
   Arguments: `names` (1 to 10). Reply: the names now available; any name that is not one of the user's
   tools gets a plain "not available" line. The model picks by meaning from the directory; there is no
   matching code, no word list (owner standing rule).
3. Loaded schemas are appended after the core set from the next step on, and stay for the rest of the
   turn. The list only grows (confirm still drops from step 2, as today).
4. A call to one of the user's tools that was not loaded yet is run as normal (and the tool is added),
   so a model that already knows the name loses no step.
5. A contact principal (WhatsApp customer, console agent for a contact) and the dealer flow keep today's
   full list: it is small (customer tools are 9, `tools.py:153-166`).
6. One line in the system prompt appended at runtime: other tools are listed in `crm_tools_load`; load
   what the question needs. Slice 1 (lane TARGET-ACHIEVED-PERF) owns the other prompt conflicts.

## Targets (measured on crew's frozen-set run, x1 then x3)

- Step 1 input of a staff panel question, all permissions: under 10,000 tokens (today ~27,000 estimated).
- p90 input tokens per question on the frozen agent set: under 45,000 (today 91,600 on the 60-turn extract).
- Median seconds per question: not higher than baseline.
- Frozen owner-FAIL agent set: no case that passed in the baseline fails.

## Tests (red first, tester writes them from the UAC)

Offline pytest, fake provider, US$0: listed in the UAC (T1-T11). Existing tests that assert narrowing
(`tests/chatbot/agent/test_agent_panel_speed.py`, `test_ai_tools_wave2_round4.py`,
`test_ai_tools_wave2_round9.py`) are superseded where they assert the narrowed list; the tester lists each
changed assertion for the lead's sign-off before the coder starts.

## Assistant coverage

`crm_tools_load` is assistant-internal (no screen). Two eval prompts added to the frozen-set dev split by
crew (a complaint count and a stock question on the panel, each needing a load).

## Work order

1. Tester: red tests T1-T11 (commit `test(red):` alone, red-proof note).
2. Coder: core set + `crm_tools_load` + auto-load on call + retire narrowing + trace field.
3. Kill-proof, reviewer (opus high), `scripts/crew-tests.sh`, crew live x1 capped US$0.50 then x3.
4. Hand test (panel), crew-done.
