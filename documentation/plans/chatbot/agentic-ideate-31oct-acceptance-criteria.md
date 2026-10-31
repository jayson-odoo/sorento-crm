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

## R3a: a reply to the bot's own question stays on the bot

Built as Q4 (a), any bot question. Pending the owner's final word.

- **AC-R3a-1 [BE]** Given the sent `session_vars` carry `focus.required_ask` (any lane's), when the contact writes, then the
  side is chat, reason `open_question`, with no Jev call. No key or prompt is needed to get there.
- **AC-R3a-2 [BE]** Given a fresh, well-formed held list (`ideation.status == similar_offered`), with `is_test` true or
  false on the pointer, then the side is chat, reason `open_question`, with no Jev call.
- **AC-R3a-3 [BE]** A held list 24 hours old or older, or a malformed one, is not held (the same reading as
  `_held_pointer`): the message routes normally.
- **AC-R3a-4 [BE]** `session_vars={}` holds nothing. `session_vars=None` reads the contact's stored row. The legacy shape
  under `variables` is read too, as `five_keys` does.
- **AC-R3a-5 [BE]** Earlier rules still win: ineligible contact, media, and a pending proposal (reason `pending_action`).

## R2: three idea tools on the agent

### Journey

1. A staff member with the Agent switch on, in the console, writes "I have an idea: the stock list is too long on my phone".
2. Jev routes it to the agent. The agent fills in the fields and proposes the idea.
3. The console shows the confirm card with the title, plus any similar ideas of theirs. Nothing has been created.
4. They confirm. The idea is created, flagged test, and the reply gives its number, its link and the optional fields not
   given. Or they cancel, and nothing is created.
5. Later they write "change that idea's title to Nearest warehouse first". The agent finds it, proposes the edit, they
   confirm, and the title changes. No delete and no undo.

### Contract for the tests

- In `agent/writes.py`: `CREATE_IDEA = "crm_idea_create"`, `UPDATE_IDEA = "crm_idea_update"`, `LIST_IDEAS = "crm_ideas_list"`,
  `IDEA_IS_TEST = True`. Slug for all three: `ideation.board.view`.
- `crm_idea_create` args: `problem` (required), `title`, `desired_outcome`, `use_cases` (list of text), `current_workaround`.
- `crm_idea_update` args: `idea_id` (required), and the same five fields, all optional but at least one required.
- `crm_ideas_list` args: optional `search`.
- Labels in `TOOL_LABELS`: "submit a new idea or feature request", "change one of your ideas", "your ideas".

### ACs

- **AC-R2-1 [BE]** A user holding `ideation.board.view` is offered all three tools. A user without it is offered none, and
  `propose_step` and `run_user_read` refuse them. A contact with no linked user never reaches them.
- **AC-R2-2 [BE]** `propose_step` for `crm_idea_create` returns `proposed` and sends no create to the shared service. A missing
  `problem` or an unknown argument is `invalid`. `is_test`, the submitter and the product are not model arguments: passing
  one is `invalid`.
- **AC-R2-3 [BE]** Given similar ideas in ss, the proposal's summary names up to 3 by number and title. The lookup sends the
  LINKED user as submitter and `is_test: true`.
- **AC-R2-4 [BE]** Given ss not configured, or the similar lookup failing, the proposal still returns `proposed` with no
  similar line and no error.
- **AC-R2-5 [BE]** On confirm, exactly one create reaches ss with the given fields, `submitter_crm_user_id` of the LINKED user
  (also when an operator acts), the contact's phone, the configured product, `is_test: true`, and `intake_ref` a valid uuid
  that is equal for the same user and text and different for different text. Two ideas in one proposal make two creates.
- **AC-R2-6 [BE]** After confirm, the reply names the idea number, the link, the optional fields not given, and that it is a
  test idea. The step is `done` with `result_id` the idea id.
- **AC-R2-7 [BE]** Given ss down or not configured at confirm, the step is `failed`, the reply says plainly the idea was not
  created, and the text carries no URL, key or id.
- **AC-R2-8 [BE]** Cancelling a proposal sends no create.
- **AC-R2-9 [BE]** `crm_ideas_list` returns the linked user's ss list (`mine=true`) plus the ideas from this contact's executed
  `crm_idea_create` steps, one row per idea id, and those ids join the turn's seen ids. Steps that failed or were cancelled,
  and another contact's steps, are not included. An ss failure returns a typed `error` with no URL or key.
- **AC-R2-10 [BE]** `crm_idea_update`: `idea_id` must come from this turn's results. With no field given it is `invalid`. An idea
  the linked user does not own is refused at the proposal ("You can only edit your own ideas."), even when that user holds
  `ideation.ideas.manage`. The summary names the fields changing.
- **AC-R2-11 [BE]** With an operator acting for someone else: an update needs the operator to hold `ideation.ideas.manage`, else
  it is refused, no PATCH reaches ss and no ss session is opened as the operator (the linked user's ownership read comes
  first, as in `read_before_all`, and is harmless); with it, the proposal works and the PATCH runs as the linked user. A create needs
  `ideation.board.view` on both.
- **AC-R2-12 [BE]** On confirm of an update, one PATCH reaches ss `/embed/ideas/{id}` carrying only the changed fields in ss's
  names (`desiredOutcome`, `useCases`, `currentWorkaround`). If the idea changed since the proposal, the step is refused and
  no PATCH is sent. The change lines read before and after in words.
- **AC-R2-13 [E2E]** Through `run_agent_turn` with a scripted provider and `tests/_ideation_ss_fake.py`: propose, confirm, list
  (the new test idea is found though ss's list omits it), propose the update, confirm. The fake sees one create and one PATCH.
- **AC-R2-14 [T]** `agent_tool_labels()` snapshot is the 15 labels: the 6 writes, "submit a new idea or feature request",
  "change one of your ideas", the 6 reads, then "your ideas".
- **AC-R2-15 [BE]** The bot's capture is unchanged: `tests/test_ideation_capture_turn.py` and
  `tests/test_ideation_capture_golden_script.py` stay green, with the payload builder now shared.
- **AC-R2-16 [T]** Eval: the gate bar in the plan, on the final labels. Crew runs the hidden gate.
