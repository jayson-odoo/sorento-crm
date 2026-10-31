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

## R3b: a reply to the agent's own question stays with the agent

No open question blocks this slice. R3a (the bot asked) is added after Q4.

### Journey

1. A staff member writes "I want to submit an idea". The agent replies "What is the idea?".
2. They answer in a few words: "stock list too long on my phone".
3. That answer reaches the agent, even though on its own it reads like nothing in particular to Jev.
4. If instead they ignore the question and ask "SRTWB888 stock", the bot answers it.

### Contract for the tests

- `ANSWER_SCHEMA` (`agent/tools.py`) gains an optional boolean `asked_back`. It is not required.
- `agent/loop.py` stores `"asked_back": true` in the turn's `response` when the final answer sets it, and leaves the key
  out otherwise.
- `router.ASKED_BACK_MINUTES = 60`. New route reason: `agent_asked`.

### ACs

- **AC-R3b-1 [BE]** Given a final `answer` call with `asked_back: true`, when the turn finishes, then
  `turn.response["asked_back"]` is true. Given a final answer without it, a plain-text final, or a forced final at a
  limit, then the key is absent.
- **AC-R3b-2 [BE]** `ANSWER_SCHEMA` declares `asked_back` as a boolean, it is not in `required`, and its description
  says to set it only when the reply asks the user something needed to finish.
- **AC-R3b-3 [BE]** Given the contact's latest done turn is an agent turn with `asked_back` true, created under an hour
  ago, when Jev answers agent at any confidence (including under the floor), then the side is agent with reason
  `agent_asked`, and `score`, `model` and `ms` are recorded.
- **AC-R3b-4 [BE]** Same state, when Jev answers chat UNDER the floor, then the side is agent with reason `agent_asked`.
- **AC-R3b-5 [BE]** Same state, when Jev answers chat at or above the floor, then the side is chat with reason
  `classified`: a new question wins.
- **AC-R3b-6 [BE]** The flag is ignored, and routing is exactly as without it, when: the latest done turn is a bot turn
  newer than the flagged agent turn; the flagged turn is an hour old or older; the latest agent turn has no flag or
  `asked_back` false; the flag belongs to another contact. Under the floor these go to chat with `low_confidence`.
- **AC-R3b-7 [BE]** With the flag set, every earlier rule still wins with no Jev call: ineligible contact, media, a
  pending proposal (still reason `pending_action`), an open question, the daily cap, text length, no key, no prompt.
- **AC-R3b-8 [BE]** With the flag set, a Jev failure (`JevError`) or a malformed choice still goes to chat, with the
  same reasons as today.
- **AC-R3b-9 [BE]** The flag is read whatever `session_vars` the console sends, `{}` included: the console keeps `{}` for
  a contact whose turns have all been on the agent, because an agent turn returns `session_vars: null`
  (`useChatbotConsole.ts:131`, `:242`). So `{}` does not switch this rule off.
- **AC-R3b-10 [T]** Eval: the 4 paraphrased replies and the one new question (rows fu1 to fu5) all land on the right
  side when run through this rule on the Jev answers.

## R2, R3a

Added after Q1 to Q4.
