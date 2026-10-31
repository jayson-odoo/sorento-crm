# PLAN: ideas through the agent, and routing that follows the agent's tools (AGENTIC-IDEATE)

**Status:** behaviour card filed 31 Oct 2026, waiting for answers. No code yet. Track: size M, lead pattern.
UAC, tickets and the slice list get written here once the answers are in.

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
  builder moves out of `handle_capture_turn` so both paths share it. `intake_ref` is minted at the proposal, so a
  retried confirm lands on the same idea.
- The agent fills the fields itself, so `extract_ideate_turn` is not called on this path.
- Similar ideas: the proposal reads ss `similar-own` and names up to 3 of the user's similar ideas with their links.
  The user confirms to log a new one or cancels. No held numbered list on this path.
- The reply after confirm names the idea number and link, and the optional fields not given, same facts as today.
- Status, merge, vote and editing other people's ideas stay on the board.
- Why not `crm_ideation_turn`: it writes at once with no proposal, and its state lives in `session_vars.ideation`.

### R3. Multi-turn: a question stays with the side that asked it

Measured gap: `router.py:76` does NOT keep a bot capture on chat. `pending_of` reads only `open_question`
(`session_state.py:244-246`), while the bot's idea ask lives on `focus.required_ask` (`engine.py:9455`) and its held
similar list on `ideation` (`ideation_capture_service.py:375`).

- **a. The bot asked:** `focus.required_ask` set, or `ideation.status == similar_offered`, routes to chat (see Q4).
- **b. The agent asked:** the `answer` tool gets a new `asked_back` flag, stored on the turn. The next turn stays on
  the agent, for one turn only, as the bot's slot does. Needed because all 3 replies to the agent's "what is the idea?"
  fall under the floor and would land on the bot (see Eval). It also fixes every other clarifying question
  the agent asks today.
- **c. A proposal is waiting:** already goes to the agent (`router.py:70`), before the daily cap (`:80`).

### R4. What does not change

WhatsApp, media (`router.py:68`), ineligible contacts, the Agent switch, over-cap turns and every Jev failure stay on
the bot. `lanes/ideate.py` is not edited. Over the cap, an idea is still captured by the bot lane.

## Examples

**No real idea message was available.** Every example is a paraphrase. See "For crew" below.

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

**Gate:**
- The brief says re-label the idea rows, but there are none: 0 of the 218 rows in `gold.jsonl` + `gold_topup.jsonl`
  carry parser domain ideate. Two rows are idea-shaped (t020, t033), both labelled chat. Decision: t020 goes
  borderline and is reported apart, t033 stays chat (it asks for new product codes, not an idea).
- New crew-only file `crew/state/eval/agentic-ideate/gold_ideate.jsonl` (never committed): the 13 idea rows, 7
  decoys, 5 follow-ups, plus any real rows crew exports.
- Bar: at least 12 of 13 idea rows reach the agent; held-out missed-agent and wasted-agent no worse than the frozen
  v2 run. Crew runs the hidden gate.

## Risks

- **Cost:** more console turns reach the agent. An idea takes one agent turn to propose, plus one more when confirmed by
  message rather than the console button, against one bot turn. Cost per idea is UNVERIFIED and gets measured in the console pass. Idea volume is UNVERIFIED (see "For
  crew"). WhatsApp cost does not change, since the agent is not on WhatsApp.
- **Daily cap:** 50 agent turns per contact (`router.py:37`, `agp2_0001_router.py:59`). A confirm is not blocked
  (`router.py:70` runs first), but it still counts toward the total. Over the cap the bot captures the idea.
- **A tool can change routing with no owner publish.** That is the point of goal 2. The guard is the snapshot test
  plus the router gate on the PR. Each label is 2 to 6 words, so a badly worded one can pull messages to the agent.
- **Only one added tool family has been measured.** Later tools rely on their own gate run.

## Questions (the answers go here)

- **Q1. Confirm before an idea is created?** Today's capture creates at once ("no draft, no review step",
  `ideation_capture_service.py:3-4`). Every agent write proposes first (`actions.py:1-5`, `loop.py:1101`).
  (a) confirm, same as every agent write; (b) create at once, a new direct-write path. **Rec (a):** one write path,
  and a misread message never reaches the board. Cost: one more turn per idea.
- **Q2. Undo after create?** The #2021 grace window and undo exist only for form actions (`actions.py:114-117`,
  `writes.py:1481`). The CRM gateway has no idea delete (`api/v1/ideation/ideas.py`), though ss does (`embed.py:620`).
  (a) confirm only, corrected with `crm_idea_update`, as `crm_opportunity_create` works today; (b) add a gateway
  delete, an undo tool and a grace window. **Rec (a):** no new delete surface, and a wrong idea can still be edited.
- **Q3. Real idea or test idea from the console?** Bot console ideas are flagged test and hidden from the board by
  default (`lanes/ideate.py:230`). Agent writes have no test mode (no `is_test` in `writes.py`), and all agent turns
  are console turns today. (a) real after confirm, same as opportunities and purchase requests; (b) flagged test
  until the agent reaches WhatsApp. **Rec (a):** the person confirmed it deliberately. Cost: console trials post
  real ideas to the board.
- **Q4. How wide is rule R3a?** (a) any bot question (`focus.required_ask` on every lane) stays on chat; (b) only
  idea questions. **Rec (a):** the same class as `router.py:76`, and the slot is one turn long
  (`required_fields.py:53-54`). Cost: an analytics question in that one turn goes to the bot, and gold rows carry no
  session state, so the eval cannot measure it.

## For crew (not the owner)

- **Real rows:** my read-only query of `chatbot.turns` (branch_kind = ideate) on the lane's dev DB was denied by the
  auto-mode classifier and I did not retry it. Please export real idea messages, masked, with their count, or say
  paraphrases are enough for the gate.
- **Hand test:** `crew.toml:155` has no shared-service host in `no_proxy`, so creating an idea on a copy fails at
  transport. The copy's configured ss URL is UNVERIFIED. Options: (a) point the copy at a local ss, (b) hand-test
  the proposal and refusal only, and prove the create with `tests/_ideation_ss_fake.py`. Recommendation: (a), since
  the end state is the whole point.

## Architecture

- **Layer:** router input (`decide_route`) and the agent registry (`agent/writes.py`). Nothing in the parser or the
  bot's lanes.
- **Shared mechanism:** `TOOL_LABELS`, `WRITES` / `USER_READS`, `propose_step` and `confirm`, `call_create_idea`.
  No new table, registry or setting.
- **Classes fixed:** a tool the router does not know about; a reply to a question landing on the side that did not
  ask it. Neither is specific to ideas.
