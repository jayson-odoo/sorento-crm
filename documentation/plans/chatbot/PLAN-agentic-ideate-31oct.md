# PLAN: ideas through the agent, and routing that follows the agent's tools (AGENTIC-IDEATE)

**Status:** code complete on PR #2038. Owner's first hand test led to a label rewording, the last change here. Reviewer on that delta, crew's hidden gate on the new label
and the owner's retest are still to come. Track: size M, lead pattern.
UAC: `agentic-ideate-31oct-acceptance-criteria.md`. No screen changes, so Phase 1 (frontend mock) does not apply.

Slices: **S1** = R1 routing. **S2** = R3 multi-turn. **S3** = R2 idea tools. They land as commits on this one lane branch.

## The owner's question, answered

"How does Jev know it should go to the chatbot or the agent? Is it automatic when the tool is agentic?"

**Today it is a static prompt, and it is not automatic.** Jev reads hand-written text (`criteria.chat`,
`criteria.agent`) from the DB prompt label `chatbot_router` (`router.py:32`, `:173-193`, seed
`ai_prompt_registry.py` `_chatbot_router_fallback`). It never sees the tool list (`_state`, `router.py:196-225`).
Adding a tool changes nothing in routing.

**Ideas already go to the wrong place.** The prompt never mentions ideas, but `criteria.agent.also` says "any
request to change, update, approve or record something". In the run below 9 of 13 idea messages clear the floor to
the agent, which has no idea tool (`tools.py:61-75`, `writes.py:273` and the `WRITES[...]` lines). The other 4 fall
to the bot, which has an idea lane (not run in this check). This only affects console turns: the router's one caller is `console_service.py:502`, and
WhatsApp never reaches the agent (`run_agent_turn` callers: `console_service.py:597`, `system/chatbot.py:723`).

**After this lane:** a new agent-only tool plus its plain label is enough, with no prompt edit. WhatsApp ideas stay
on the bot lane until the agent itself goes live on WhatsApp, which is a separate lane.

## Rules

### R1. Routing reads the tool list

`decide_route` adds `criteria.agent.tools` at run time: the plain label (`TOOL_LABELS`, `tools.py:123-149`) of every
entry in `writes.WRITES` and `writes.USER_READS`.

- Stays owner-published: the `chatbot_router` label (instructions, chat and agent text, model) and the min score.
  No publish and no migration is needed for this lane or for a later tool.
- A registry entry with no label fails a guard test. A snapshot test shows the list changing in any PR that adds a
  tool, and that PR runs the router gate.
- Left out on purpose: `tools.REGISTRY` (stock, ETA, cost). The bot answers those too, and the static `not_for` text
  already covers them. Listing them made the tune split slightly worse (arm D). Trigger to revisit: the first
  `REGISTRY` tool that no bot domain answers.
- Not filtered per user. Arm C shows hiding the idea lines still leaves 9 of 13 on the agent, because of the static
  `also` text, so a filter would add permission queries for no gain. A user without the slug gets the agent's plain
  refusal (the tool is hidden from the model and `propose_step` refuses, `writes.py:472-479`).

### R2. Three idea tools on the agent

Gate on all three: `ideation.board.view`, the same slug as the bot lane (`ideation_capture_service.py:58`).

| Tool | Kind | Does |
| --- | --- | --- |
| `crm_idea_create` | write | Proposes one idea: title, problem (required), desired outcome, use cases, current workaround. |
| `crm_ideas_list` | read | The user's own ideas, with the id the update needs. |
| `crm_idea_update` | write | Edits one of the user's OWN ideas, same `isMine` check as the board (`api/v1/ideation/ideas.py:191-205`). |

- Same shared-service call and payload as today (`call_create_idea`, `ideation_capture_service.py:113`). The payload
  builder moves out of `handle_capture_turn` so both paths share it. `intake_ref` is derived (see the decisions below), so a
  retried confirm lands on the same idea.
- The agent fills the fields itself, so `extract_ideate_turn` is not called on this path.
- Similar ideas: the proposal reads ss `similar-own` and names up to 3 of the user's similar ideas by number and title.
  The user confirms to log a new one or cancels. No held numbered list on this path.
- The reply after confirm names the idea number and link, and the optional fields not given, same facts as today.
- Status, merge, vote and editing other people's ideas stay on the board.
- Why not `crm_ideation_turn`: it writes at once with no proposal, and its state lives in `session_vars.ideation`.

### R3. Multi-turn: a question stays with the side that asked it

Measured gap: `router.py:76` does NOT keep a bot capture on chat. `pending_of` reads only `open_question`
(`session_state.py:244-246`), while the bot's idea ask lives on `focus.required_ask` (`engine.py:9455`) and its held
similar list on `ideation` (`ideation_capture_service.py:375`).

- **a. The bot asked:** `focus.required_ask` set, or `ideation.status == similar_offered`, routes to chat (see Q4).
- **b. The agent asked:** the `answer` tool gets a new `asked_back` flag, stored on the turn. On the next message Jev
  still runs, but only a confident chat answer (at or above the floor) takes it to the bot; anything else stays on the
  agent. So a new question still wins, as it does on the bot's own ask (`required_fields.py:47-48`). In the check, all
  3 replies to "what is the idea?" sit under the floor and stay on the agent, and "SRTWB888 stock" asked at that point
  scores chat 0.98 and goes to the bot. A pure state rule would send that one to the agent, which has no forms or files.
  The flag lasts one turn and one hour, so a reply days later routes normally. Every Jev failure still goes to chat. It
  also fixes every other clarifying question the agent asks today.
- **c. A proposal is waiting:** already goes to the agent (`router.py:70`), before the daily cap (`:80`).

### R4. What does not change

WhatsApp, media (`router.py:68`), ineligible contacts, the Agent switch, over-cap turns and every Jev failure stay on
the bot. `lanes/ideate.py` is not edited. Over the cap, an idea is still captured by the bot lane.

## Examples

These are paraphrases: the repo is public, so real messages stay in the crew-only gold (see Eval).

| Message | Today | After |
| --- | --- | --- |
| "I have an idea: when I check stock the list is too long on my phone..." | Below floor (0.64), bot captures it | Agent (0.92), proposes the idea, user confirms |
| "Cadangan: skrin stok patut tunjuk gambar produk sekali" | Below floor (0.60), bot | Agent (0.84) |
| "建议系统增加一个功能，报价单过期前自动提醒业务员" | Agent (0.94), which has no idea tool | Agent (1.00), proposes the idea |
| "I want to submit an idea" | Below floor (0.24), bot asks | Agent (0.96), asks what the idea is; the reply stays on the agent (R3b) |
| "any idea when SRTWB888 will arrive?" | Chat (1.00) | Chat (1.00) |

## Edge cases

- Shared service not configured or down: nothing is proposed, one honest line. No idea is half written.
- One message with two ideas: two steps in one proposal, confirmed together (`MAX_STEPS`, `actions.py:34`).
- A photo mid-capture goes to the bot (`router.py:68`). Today's missing-fields line names photos (`_PHOTOS`,
  `ideation_capture_service.py`) and the idea link is where they get added; the agent's reply keeps that line.
- Reply language: the agent's wording follows the message, but the code-built "Done. I made these changes:" line is
  English (`actions.py:167-184`), as on every agent write. Today's capture replies are fully localised
  (`render_reply`), so Malay and Chinese users lose that on the final line.
- A new question during R3b's one turn goes to the agent, which has the same lookup tools, so it still gets answered.

## Eval

Run 31 Oct on the local Jev key: 204 calls, USD 0.0074. Paraphrases I wrote, tune split only. **This is a direction
check, not the gate.**

| Arm | Idea rows reaching the agent (13) | Chat-labelled rows sent to the agent (9) | Tune split, n=53 (agree, missed, wasted) |
| --- | --- | --- | --- |
| A: today's prompt | 9 | 3 | 96%, 2/9, 0/44 |
| C: tool list, no idea tools | 9 | 2 | not run |
| B: tool list with idea tools (this plan) | 13 | 2 | 96%, 2/9, 0/44 |
| D: as B plus shared lookups | 13 | 2 | 94%, 3/9, 0/44 |

Replies to the agent's "what is the idea?": 3 of 3 under the floor on both A and B (at most 0.48), which is why R3b
exists. A "yes new one" reply to a similar-idea question clears it (0.88, 0.94).

**Real rows (crew export, 28 Oct backup, 34 Jev calls, USD 0.0011).** 17 masked rows, all English; 11 of them come
from one contact that may be a tester, so this is a small and skewed set. Message text stays under `crew/state`.

| Group | Rows | Right, today's prompt | Right, tool list (arm B) |
| --- | --- | --- | --- |
| First messages that are ideas | 7 | 3 | 6 |
| Follow-ups to an idea (synthetic context, see below) | 5 | 5 | 5 |
| Wrong routes, should stay on chat | 5 | 3 | 4 |

The one idea arm B misses scores 0.68, just under the floor. The one wrong route it still sends to the agent asks for
new product variants and is the same message as gold row t033, so that miss is not new. The export has no context and
those follow-ups answered the retired draft flow, so each carries a synthetic exchange: the row it follows plus one
fixed agent question.

**Final labels (the exact 15 from AC-R2-14, 42 Jev calls, USD 0.0015).** Measures the wording before the code exists, so
the gate step checks `agent_tool_labels()` still equals this list (`criteria_final_15.json`).

| Group | Right | Bar |
| --- | --- | --- |
| Paraphrased ideas (en 7/7, ms 3/3, zh 3/3) | 13/13 | at least 12 of 13: met |
| Real first ideas | 6/7 | at least 6 of 7: met |
| Real wrong routes | 3/5 (2 sent to the agent) | at most 2 of 5 sent: met, exactly at the bar |
| Paraphrased decoys | 6/7 | reported |
| Real follow-ups (synthetic context) | 5/5 | reported |
| Paraphrased follow-ups, Jev alone | 2/5 | reported |
| Paraphrased follow-ups, with the R3b rule | 5/5 | AC-R3b-10: met |

The two wrong routes also go to the agent on today's prompt, so this adds none. One sits close to the floor (0.72), so a
rerun could land it either side. The real idea it misses scores 0.66 and is captured by the bot lane. I did not reword a
label to chase that one row.

**Held-out, final labels against frozen v2 (172 rows, USD 0.0063, cap raised by crew for this one run):**

| | Frozen v2 | Final labels |
| --- | --- | --- |
| Agreement | 90% | 91% |
| Missed-agent | 10/45 | 11/45 (**one worse, so the bar below is missed by one row**) |
| Wasted-agent | 7/127 | 5/127 |
| Without borderline rows and t020: missed, wasted | 9/41, 4/123 | 10/41, 4/123 |

Three rows changed side. t020 and t046 moved to the right side. t043 (Chinese, dealer) moved to the wrong side, from 0.72
to 0.68 across the 0.70 floor, so it falls to the bot.

**Rerun, crew ruling on ask a29856494 (same labels, 172 more calls):** t043 came back at 0.74, so that one miss was noise,
and crew's condition for the bar is met. The total did not improve, though, and the result should be read with that:

| | Frozen v2 (one run) | Final labels, run 1 | Final labels, run 2 |
| --- | --- | --- | --- |
| Missed-agent | 10/45 | 11/45 | 12/45 |
| Wasted-agent | 7/127 | 5/127 | 5/127 |
| Agreement | 90% | 91% | 90% |

- Jev moves between identical runs: 55 of 172 rows changed score, and 3 crossed the floor (t023, t031, t043).
- t023 and t031 sit under v2 on both runs (0.78 to 0.70 to 0.66, and 0.80 to 0.70 to 0.62). Across the 45 agent rows the
  mean lean to the agent falls about 0.02 (20 rows lower, 5 higher, 20 equal). So the tool list probably does lower
  agent-row confidence a little, on top of the noise. That reading rests on a single v2 run.
- These rows fall to the bot, which is today's path, so the cost is a weaker answer rather than a wrong action. Idea rows
  are not among them. Accepted per crew; no label was reworded on this set.

**Gate:**
- The brief says re-label the idea rows, but there are none: 0 of the 218 rows in `gold.jsonl` + `gold_topup.jsonl`
  carry parser domain ideate. Two rows are idea-shaped (t020, t033), both labelled chat. Decision: t020 goes
  borderline and is reported apart, t033 stays chat (it asks for new product codes, not an idea).
- Crew-only gold at `crew/state/eval/agentic-ideate/gold.jsonl`, built by `build_gold.py` beside it (never committed):
  the 17 real rows, plus 25 paraphrases scored apart, which are the only Malay and Chinese coverage.
- Bar: at least 6 of 7 real first ideas and at least 12 of 13 paraphrased ideas reach the agent; real wrong routes no
  worse than today's prompt (at most 2 of 5 sent to the agent); held-out missed-agent and wasted-agent no worse than
  the frozen v2 run. Crew runs the hidden gate.

## Risks

- **Cost:** more console turns reach the agent. An idea takes one agent turn to propose, plus one more when confirmed by
  message rather than the console button, against one bot turn. Cost per idea is UNVERIFIED and gets measured in the console pass. Idea volume is UNVERIFIED (see "For
  crew"). WhatsApp cost does not change, since the agent is not on WhatsApp.
- **Daily cap:** 50 agent turns per contact (`router.py:37`, `agp2_0001_router.py:59`). A confirm is not blocked
  (`router.py:70` runs first), but it still counts toward the total. Over the cap the bot captures the idea.
- **A tool can change routing with no owner publish.** That is the point of goal 2. The guard is the snapshot test
  plus the router gate on the PR. Each label is 2 to 6 words, so a badly worded one can pull messages to the agent.
- **Only one added tool family has been measured.** Later tools rely on their own gate run.

## Owner's answers

- **Q1, confirm before an idea is created: (a) confirm.** Same path as every agent write.
- **Q2, undo after create: (a) confirm only.** A wrong idea is fixed with `crm_idea_update`. No delete and no undo.
- **Q3, real or test idea from the console: (b) test.** Ideas the agent creates stay flagged test until the agent reaches
  WhatsApp. The trigger to flip `writes.IDEA_IS_TEST` is the lane that puts the agent on WhatsApp.
- **Q4, how wide is R3a: (a).** Any bot question keeps the next reply on the bot, and an agent question keeps it on the
  agent (R3b). The owner confirmed the goal: new idea conversations start on the agent, and (a) only protects a bot
  conversation already mid-question.

**Where that goal reaches today:** console turns, for contacts whose Agent switch is on (`access.py:352` defaults it off;
`router.py:66-67` sends the rest to the bot). WhatsApp ideas stay on the bot lane until the agent reaches WhatsApp.

### What Q3 changes

- **Test ideas are not in the shared service's list** (`services/ideas.py:507-508`, and the embed list has no way to ask
  for them). So `crm_ideas_list` alone could never find an idea the agent just created, and Q2's fix path would fail
  during the whole test phase. Decision: `crm_ideas_list` also returns the ideas from this contact's executed
  `crm_idea_create` steps. Remove that when the flag flips.
- **A single idea can still be read and edited by id** (`embed_get_idea`, `embed_update_idea`), so `crm_idea_update` and
  the link both work on a test idea.
- **The reply says it is a test idea**, because the person will not find it on the board.
- Similar ideas are read in the test lane too, so real ideas are not offered as similar during this phase.

### Decisions made while writing R2

- **The proposal never depends on the shared service.** The similar lookup is best effort: if ss is down or not set up,
  the proposal still shows with no similar line, and the create fails honestly at confirm. Otherwise the hand test could
  not show a confirm card, since copies reach no shared service (crew C2).
- **Who may edit:** the linked user must own the idea, even a linked user who manages ideas (the board stays the place
  for other people's ideas). A console operator acting for someone else must hold `ideation.ideas.manage`: rule R9 says
  both people must be allowed, and the board lets a view-only user edit only their own. The write runs as the linked
  user. The create needs `ideation.board.view` on both.
- **`intake_ref`** is derived from the linked user and the idea's text (uuid5) rather than minted, because a step keeps no
  private value between proposal and confirm. Proposing the same idea again lands on the same idea in ss.
- **`raw_transcript`** is built from the fields given, because a write tool sees its arguments and not the message.

### Decisions after the first review

- **Only test ideas can be edited while `IDEA_IS_TEST` is on.** Q3 ruled on creates only, but an edit from a console trial
  landing on a real idea is the same harm, and security review confirmed it was possible. It is one condition on the same flag.
  This goes beyond the owner's answer, so it was reported to crew.
- **A confirmed idea's link is added by code after verification**, as `proposal_block` does, because `final_reply` scrubs ids
  from anything the model writes (`loop.py:432`). A model-written URL carrying an id is dropped whole.
- **Test ideas in `crm_ideas_list` are read live by id**, not rebuilt from stored steps, so ss stays the one source of truth and
  an edit on the board shows too. The cost is one ss call per listed test idea, capped.

- **A code-added note is opt-in per write**, on `crm_idea_create` only. The first version added any step's note, which changed the
  purchase-request reply from #2021 and could say "It applies in N seconds" after the window had lapsed. That side effect is gone,
  so #2021's reply is unchanged.
- **The list reads only the 5 newest test ideas**, with the rest counted in `more`, instead of adding a time budget across calls.
  Pushing back on the review's deadline: test ideas exist only for console trials, and a hung call already stops at the first
  failure. Older test ideas cannot be edited through the agent during the test phase.

### To do when `IDEA_IS_TEST` flips (the lane that puts the agent on WhatsApp)

- Drop the second source in `crm_ideas_list`, and the test-only edit rule.
- Decide whether a view-only operator may create an idea in another user's name. R9 allows it, and the test flag hides it today.
- The proposal now hands full values back to the model while it waits (`waiting_reference`, history), up to 4000 characters a
  field, which gives injected text more room right where the model decides `confirm_action`. Look at this together with the
  pre-existing chat-confirm item below before real ideas are at stake.
- Invisible text: format characters (Cf) are removed, but variation selectors (Mn, from U+E0100), CGJ, Hangul filler and braille blank
  still survive, so a value can carry text the person cannot see. Close this before ideas reach the board.
- Editing use cases replaces the whole list, and list rows carry no use cases, so "add a use case" can drop the others (the card does
  show the new value). Give the rows their use cases, or a merge rule.
- Look-alike quotes (U+201D, U+FF02) are not escaped in the proposal. All the text stays visible.
- `raw_transcript` on the agent path holds the fields the model gave, not the user's own words (a write tool sees only its arguments), so ss
  loses the original wording that the bot's capture keeps. Decide whether to carry the turn's text through to the write.
- A re-proposed idea whose ss status has moved past `captured` replays and reads "could not be reached" (`call_create_idea`
  requires `captured`), and any ss 4xx reads the same. Unlikely while ideas are off the board; give these their own line then.

### What the console pass showed (31 Oct, 33 turns on the test copy)

- No create reached any shared service, no errors, no 429s. `asked_back` stayed on the agent 3 of 3 times, a small sample, and did not stick after a
  plain answer. A propose turn cost 2 rounds, 6,854 tokens in, 484 out. A typed confirm's cost is not shown in the console, so it was not measured.
- R3 covers bot questions that hold state (an open pick, a required ask, a held list), proved through the real console path by
  `test_agent_ideas_console.py`. A question the bot only words as a sentence holds no state, so Jev still decides the reply: state rules never read
  wording (`router.py:3`).
- An idea from a contact with a different chat history scored 0.14 and went to the bot, against 0.80 and 0.82 for a similar message on another. The
  history is the likely cause, unconfirmed. The eval's idea rows mostly carry no history, so real scores may vary more than the eval shows.
- The two console-tab Reset controls differ: Reset clears the Bot tab only, and New conversation clears the agent. The hand-test script says so.

### Owner's hand test, first round (31 Oct)

Message: "I think we need to have sorento agentic ai". Two causes, neither from this PR. Router: Jev scored it 0.40 on a contact with the Agent switch on, under the
floor, because the idea label did not cover a stated need. Bot lane: the extractor has no usable key on the copy (inferred, see the PR note), and an empty extraction
reads as "no idea". Crew split it (ruling, 31 Oct): this PR rewords the label; lane AI-KEY-PER-PROVIDER owns the key resolution and the honest failed-extraction reply. Until
that ships, the bot path (Agent switch off, or an under-floor score) can still show the dead end.

Reworded label, one run each: real first ideas 7/7, paraphrased ideas 13/13, real wrong routes 2 of 5 sent to the agent (one now scores 0.84, it was 0.72), held-out missed-agent
12/45 and wasted-agent 5/127, so no better than the earlier label and still worse than v2's 10/45 on missed-agent. On the owner's message: 0.88 and 0.90, against 0.44 to 0.50.

### Accepted, not changed

- The agent's own text repeats the proposal, and the card shows it again. Cosmetic. The fix was tried and reverted: see AC-RC-12.

- The proposal's similar line can show a view-only operator the linked user's similar titles: test lane only for now.
- `_recheck` repeats the similar lookup at confirm and discards it, up to 15 s more if ss hangs.
- In the console, `~x~` in a value renders struck through though it is sent in full, and a URL in a value is clickable.
- A model answer that is only an id-bearing URL becomes "no answer", and a URL with no scheme still reads `/(id)`. Both were dead links before.

### Found by review, pre-existing, reported to crew, not in this lane

- Chat confirm is decided by the model alone (`loop.py:525`); the server only refuses a same-turn confirm. An injected model can
  confirm a waiting proposal on any later message.
- A pending proposal is checked before the daily cap (`router.py:74`, `:83`), so a chain of proposals stays on the agent over the
  cap. `/agent/turn` (`api/v1/system/chatbot.py:713`) has no daily cap, only the rate limit.
- `crm_opportunity_create`'s proposal shows only title, target and close date (`writes.py:601`), so an `expected_amount` or another agent's
  `sales_agent_id` is stored without appearing on the proposal or the Done line. The model's own text is the only cover.
- Under impersonation, `run_as_user` records the target as `real_user_id` (`writes.py:148-155`), so the real admin is missing from
  the agent's actor. A shared-service write has no CRM audit row.

## For crew (not the owner)

- **C1, real rows (answered):** crew exports masked real idea messages from the 28 Oct backup to
  `crew/state/eval/agentic-ideate/ideas-real-31oct.jsonl`. The gold is built from those, with paraphrases scored apart.
- **C2, hand test (answered, option b):** the hand test covers the proposal, the confirm card and the refusal. The
  create is proved end to end with `tests/_ideation_ss_fake.py`. Copies must not reach any real shared service.

## Architecture

- **Layer:** router input (`decide_route`) and the agent registry (`agent/writes.py`). Nothing in the parser or the
  bot's lanes.
- **Shared mechanism:** `TOOL_LABELS`, `WRITES` / `USER_READS`, `propose_step` and `confirm`, `call_create_idea`.
  No new table, registry or setting.
- **Classes fixed:** a tool the router does not know about; a reply to a question landing on the side that did not
  ask it. Neither is specific to ideas.
