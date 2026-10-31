# UAC: ideas through the agent, and routing that follows the agent's tools (AGENTIC-IDEATE)

Plan: `documentation/plans/chatbot/PLAN-agentic-ideate-31oct.md`.

All four owner questions are answered and every slice's ACs are below. "Review round" at the end holds what the first review added.

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

Q4 is (a), owner 31 Oct: any bot question.

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
3. The reply shows what will be logged, in full, plus any similar ideas of theirs. Nothing has been created. On the
   console's Agent tab this is the confirm card with a button. On the routed tab it is text, and they confirm by typing.
4. They confirm, by the button or by typing yes. The idea is created, flagged test, and the reply gives its number, its link and the optional fields not
   given. Or they cancel, and nothing is created.
5. Later they write "change that idea's title to Nearest warehouse first". The agent finds it, proposes the edit, they
   confirm, and the title changes. No delete and no undo.

### Contract for the tests

- In `agent/writes.py`: `CREATE_IDEA = "crm_idea_create"`, `UPDATE_IDEA = "crm_idea_update"`, `LIST_IDEAS = "crm_ideas_list"`,
  `IDEA_IS_TEST = True`. Slug for all three: `ideation.board.view`.
- `crm_idea_create` args: `problem` (required), `title`, `desired_outcome`, `use_cases` (list of text), `current_workaround`.
- `crm_idea_update` args: `idea_id` (required), and the same five fields, all optional but at least one required.
- `crm_ideas_list` args: optional `search`.
- Labels in `TOOL_LABELS`: "record a suggestion or wish for what the system should have or do, an idea or a feature request", "change one of your ideas", "your ideas".

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
- **AC-R2-14 [T]** `agent_tool_labels()` snapshot is the 15 labels: the 6 writes, "record a suggestion or wish for what the system should have or do, an idea or a feature request",
  "change one of your ideas", the 6 reads, then "your ideas".
- **AC-R2-15 [BE]** The bot's capture is unchanged: `tests/test_ideation_capture_turn.py` and
  `tests/test_ideation_capture_golden_script.py` stay green, with the payload builder now shared.
- **AC-R2-16 [T]** Eval: the gate bar in the plan, on the final labels. Crew runs the hidden gate.

## Review round (first review, 31 Oct)

- **AC-RV-1 [BE]** Given a waiting idea proposal, when the user types yes and the agent confirms through `confirm_action`, then
  the reply carries the idea's working link with its real id, exactly once, added by code after verification, whatever the
  model wrote. A model that repeats the tool's text word for word leaves no broken link behind: a URL with an id in it is
  dropped whole from model text, not turned into `.../(id)`. A bare id in model text still reads `(id)`.
- **AC-RV-2 [BE]** Only a write that declares it gets its note added on a chat confirm (`WriteDef.note_in_reply`, on
  `crm_idea_create` only). Every other write's reply is unchanged, including a deferred purchase-request decision, whose fixed
  "It applies in N seconds" line can be false by the time the reply goes out.
- **AC-RV-3 [BE]** The proposal shows every given value in full, never cut: on a create the title and each given field, on an
  update each field's new value. A value of over 1000 characters appears whole in the summary.
- **AC-RV-4 [BE]** `crm_ideas_list` reads each of this contact's created test ideas live from ss by id, as the linked user, so
  after an edit it shows the new title, and search matches the live title and problem. A 404 on one idea skips that row. A
  row whose `isMine` is not true is skipped. Other ss failures return the typed `error`. Test ideas come first in the list, so a
  full ss list cannot push them out. Each row says whether it is a test idea.
- **AC-RV-5 [BE]** A turn that stored a proposal never keeps `asked_back`, even if the final answer set it.
- **AC-RV-6 [BE]** `intake_ref` differs between `IDEA_IS_TEST` true and false for the same user and text.
- **AC-RV-7 [BE]** With an operator acting for someone else, `crm_ideas_list` needs the operator to hold `ideation.ideas.manage`,
  else it is `denied`, with no ss call and no list of the linked user's ideas. With it, the rows come back.
- **AC-RV-8 [BE]** `idea_id` must be one valid uuid: a comma-joined or JSON-list value is refused before any ss call.
- **AC-RV-9 [BE]** `use_cases` takes at most 5 items (the shared cleaner keeps 5, so more would be cut silently), each at most
  4000 characters. More is `invalid`, and nothing is sent to ss.
- **AC-RV-10 [BE]** While `IDEA_IS_TEST` is true, `crm_idea_update` on a real idea (`isTest` not true) is refused at the proposal,
  with a plain line pointing to the board, and no PATCH is sent. A test idea of the user's still works. When the flag is false,
  a real idea of the user's works.

## Recheck round (31 Oct)

- **AC-RC-1 [BE]** The model never receives a `note_in_reply` note: `confirm_action`'s tool result carries neither the note nor the
  link, so a word-for-word relay leaves the note in the reply exactly once.
- **AC-RC-2 [BE]** A model failure after the confirm ran still shows the note: status `failed`, and the reply holds the idea's
  number and link, because the idea exists.
- **AC-RC-3 [BE]** A URL with an id is removed from model text BEFORE number verification, so verification and the reply read the
  same text: `Stock is 5000https://x.example/<uuid> units` gets the number flagged as not verified.
- **AC-RC-4 [BE]** Only the URL goes: URL characters are ASCII, so Chinese or Malay text directly after it stays. Trailing punctuation
  stays. `[label](url)` becomes `label`. A good URL next to it stays. 100k characters of `http://` repeats finish in under 1 second.
- **AC-RC-5 [BE]** `crm_ideas_list` reads the 5 newest test ideas (`MAX_TEST_IDEAS`) and reports the rest in `more`. Every row carries a
  short problem (at most 120 characters), so an untitled idea can be named.
- **AC-RC-6 [BE]** In the proposal, a `"` inside a value is escaped, so a crafted value cannot read as another field or a second step.
- **AC-RC-7 [BE]** Format characters (Unicode category Cf: zero-width, bidi overrides, tag characters) are removed from every idea
  value before it is shown or sent, so what the person reads is what is sent.
- **AC-RC-8 [BE]** A list row's `problem` does not back a figure in the agent's answer (`_NOT_FIGURE_KEYS`), as `title` already does not.
- **AC-RC-9 [BE]** An id-bearing URL is recognised whatever the scheme's case: `5000HTTPS://x.example/<uuid> units` gets the number flagged.
  100k characters of `[x](http://` repeats finish in under 1 second, as AC-RC-4 requires of `http://` repeats.
- **AC-RC-10 [BE]** The bot-asked rule holds through the real path, `POST /console/turn` with only the parser, Jev and the ideation tool result faked:
  a bot turn opens the ask, the `session_vars` it returned go back, and the next turn routes chat with `open_question` and no new Jev call. The turn
  reaches the ideation tool as the answer to the ask (`ask_reply` true).
- **AC-RC-11 [BE]** `crm_idea_create` tells the model to use only what the user said, write a short title from their words, leave any other field out, and
  propose as soon as it has the problem. `crm_idea_update` tells it to use only what the user said. Whether the model obeys is checked by a live run.
- **AC-RC-12 [BE]** The `proposed` tool result's message stays as it was, for every write. An attempt to tell the model not to repeat the proposal was reverted
  by review: the model's own text is the only place some write details reach the user, and the only restatement in the user's language.

## Owner hand test round (31 Oct)

Owner's message, used as the test case in every AC here: "I think we need to have sorento agentic ai".

- **AC-HT-1 to AC-HT-4 moved to lane AI-KEY-PER-PROVIDER (crew ruling, 31 Oct):** key resolution per provider and the honest failed-extraction reply, shipped in #2054. Their first red tests were at `git show 5e3e9b9ae4:sorento_crm_backend/tests/test_ideation_owner_message.py`.
- **AC-HT-5 [T]** The label of `crm_idea_create` is "record a suggestion or wish for what the system should have or do, an idea or a feature request". The snapshot in AC-R2-14 changes with it, and `agent_tool_labels()` equals `criteria_try_v1.json`, the list evaluated on the gold and held-out rows.
- **AC-HT-6 [T]** The crew-only gold gains the owner's message, labelled agent. Whether Jev routes it is checked on the copy after the push.

## Failed-save line round (crew, 31 Oct)

Owner rule: no sorry or busy bot replies; honest, plain wording. The live check showed the bot's failed-save line breaks it. The reply resolves through `get_prompt`, which prefers the stored `production` row, and `seed_prompt_registry` never updates a live row, so a code change alone does not reach a seeded install.

- **AC-NS-1 [BE]** The shipped text of `ideation_capture_error` is en "I couldn't save that idea just now. Please send it again.", ms "Saya tidak dapat menyimpan idea itu sekarang. Sila hantar sekali lagi.", zh "我刚才无法保存这个创意，请再发送一次。". None holds "sorry", "maaf" or "抱歉", in any case.
- **AC-NS-2 [BE]** A transient shared-service failure, on the similar lookup and on the create, answers exactly that line, in the language the turn resolved. A permanent 4xx still answers `config_error`, unchanged.
- **AC-NS-3 [BE]** The migration, on a key whose `production` label still points at the old stock text (compared strip-normalised), adds the next immutable version with the new text and moves the label, for each of the three keys (`chatbot_reply_ideation_capture_error`, `.ms`, `.zh`). `get_prompt` then returns the new text. "Next" means above every version of the key, so an unpublished draft above the stock version is neither reused nor moved onto.
- **AC-NS-4 [BE]** A text the owner edited is left alone with a warning: no new version, label unmoved. Each key is judged on its own, so an edited `.ms` does not stop `en` and `.zh`.
- **AC-NS-5 [BE]** A re-run is a no-op: no further version. A key with no `production` label is skipped without error.
- **AC-NS-6 [T]** `alembic heads` is single, and the new revision id is at most 32 characters.
- **AC-NS-7 [BE]** `upgrade()` moves no other prompt's label: with `ai_assistant_configs.system_prompt` set and an owner's newer `agent_system` version on `production`, the label stays on that version after `upgrade()`. The seed is not called, because it re-pins that key (`ai_prompt_seed.py:170`).

