# UAC: ideas through the agent, and routing that follows the agent's tools (AGENTIC-IDEATE)

Plan: `documentation/plans/chatbot/PLAN-agentic-ideate-31oct.md`.

R1 is written now, because no open question blocks it. R2 and R3 ACs are added here once the owner answers Q1 to Q4.

## Journey

1. A developer adds a tool the agent can use: one `WRITES` or `USER_READS` entry and one plain label in `TOOL_LABELS`.
2. They publish nothing. The owner's `chatbot_router` label stays as it is.
3. A staff member sends a console message asking for what the new tool does.
4. The router asks Jev as today, and Jev now also reads what the agent can do, so the message reaches the agent.
5. The PR that added the tool shows the list changing, in one test's expected value, and runs the router gate.

The people chatting decide nothing here. No screen changes, so Phase 1 (frontend mock) does not apply.

## R1: routing reads the tool list

### Contract for the tests

- `app.services.chatbot.router.agent_tool_labels() -> list[str]`: the labels, `WRITES` entries first and then
  `USER_READS` entries, each in registry order. An entry with no label is left out rather than raising, because a
  live turn must not fail on this (AC-R1-5 is what catches it).
- `decide_route` passes Jev the label's own `instructions` and `criteria`, with one key added: `criteria["agent"]["tools"]`.

### ACs

- **AC-R1-1 [BE]** Given a production label whose `criteria.agent` is an object, when `decide_route` reaches Jev,
  then `criteria["agent"]` holds every key of the label's own agent object unchanged, plus `tools` equal to
  `agent_tool_labels()`. `instructions`, the model and `criteria["chat"]` equal the label's exactly.
- **AC-R1-2 [BE]** Given a route that reached Jev, then the stored prompt is untouched: `ai_prompt_versions.template`
  and the `chatbot_router` production label row read the same before and after, and a second route still sends the
  same `tools` once (no growth, no duplicates).
- **AC-R1-3 [BE]** Given a new `WRITES` entry and its `TOOL_LABELS` label (monkeypatched), when the next route reaches
  Jev, then `tools` includes that label, with no prompt row changed. The same holds for a new `USER_READS` entry.
- **AC-R1-4 [T]** A snapshot test pins `agent_tool_labels()` to the exact 12 labels of today in order, so a PR adding
  a tool has to change this expected value. Its failure message says that the PR must run the router gate.
- **AC-R1-5 [T]** A guard test fails, naming the tool, for any `WRITES` or `USER_READS` entry without a non-empty
  `TOOL_LABELS` label, and for a label that shows a tool name (contains `crm_`) rather than plain words.
- **AC-R1-6 [BE]** The labels of `tools.REGISTRY` entries (for example "stock on hand", "incoming stock") are not in
  `agent_tool_labels()`.
- **AC-R1-7 [BE]** Two users with different permissions get the same `tools`: the list is not filtered per user. Tool
  exposure and the dispatch guards are unchanged (`permitted_writes`, `propose_step`).
- **AC-R1-8 [BE]** Label shapes: `criteria.agent` as a plain string reaches Jev as `{"what": <that string>, "tools": [...]}`;
  a label with no `agent` key reaches Jev unchanged and gets no `agent` key invented; a `tools` key already in the
  published label is replaced by the generated list.
- **AC-R1-9 [BE]** A route that ends before Jev (ineligible contact, media, pending proposal, open question, daily cap,
  text length, no key, no prompt) behaves exactly as before and makes no Jev call. Every Jev failure still goes to chat.
- **AC-R1-10 [T]** Eval: the generated list, run on the crew-only gold, meets the bar in the plan's Eval section. Crew
  runs the hidden gate.

## R2, R3

Added after Q1 to Q4.
