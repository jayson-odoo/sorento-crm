# UAC: AGENTIC-UNIFY console, one conversation instead of Bot and Agent tabs

Status: written 31 Oct 2026. Owner approved mock v1 ("Ok", 31 Oct). Q5 (a): the agent reads recent bot replies, and the thread survives a reload.

Contract: section (a) of `CARD-agentic-unify-31oct.md` and the Console tabs of `documentation/mockups/agentic-unify/index.html`. Both arrive on main with PR #2048; until then read them on branch `crew/agentic-unify`.

## One thread

- **AC-1** The console has no tabs. One thread shows chat and agent turns in the order they happened.
- **AC-2** Every reply shows the route pill: Chat or Agent. Opened, it shows reason, score, model and time, as `RoutePill` does today.
- **AC-3** A turn that went to the agent shows, inside its bubble, the steps and reasoning that the Agent tab shows today, including the steps of a turn the router chose.
- **AC-4** A proposal shows its before and after with Confirm and Cancel in the thread, straight after the turn that made it, including a slow media follow-up routed to the agent. After Confirm it shows the countdown and Undo where the action has grace, then the outcome. It behaves as on the Agent tab today, using the same endpoints.
- **AC-5** Everything the Bot tab has stays: attachments, voice, paste, reply-to, copy, retry, trace link, prompt version, quick replies.
- **AC-6** An agent turn also has a trace link. Bubbles in a thread have unique keys, even when a busy or failed agent reply has no turn id.

## Forcing the agent

- **AC-7** The composer has an Agent toggle. When on, the next message goes to the agent, and the toggle then switches itself off. That covers a typed message and a quick-reply chip; a voice note or attachment turns it off and goes to the bot.
- **AC-8** The toggle is disabled while an attachment is present, because media always goes to the bot. `POST /system/chatbot/console/turn` with `force_agent: true` and media answers 422.
- **AC-9** A forced turn goes through `POST /system/chatbot/console/turn` with `force_agent: true`. It skips the router, so no Jev call is made. Its reply has the same shape as any other turn, and its pill reads Agent with the reason "Forced".
- **AC-10** A forced turn is not blocked by the daily cap and is counted against it, as today.
- **AC-11** For a contact the agent may not run for, a forced turn returns the refusal as reply text, like a routed turn, in words that name the reason (`AGENT_REFUSAL_MESSAGES`). It is not a 409.
- **AC-12** `POST /system/chatbot/agent/turn` and `GET /system/chatbot/agent/conversation` are removed; `GET /console/thread` replaces the read. Confirm, cancel and withdraw stay as they are.

## New conversation and reload

- **AC-13** One "New conversation" button starts both sides afresh: a new run for the bot and a new agent conversation. A proposal still waiting expires, with no decider recorded, for any operator: nothing was written, and the record names nobody who did nothing (a deliberate exception to rule R11, as `store_proposal` already expires older proposals). A later "yes" cannot confirm it. The reset is refused 409 while a turn runs for that contact, and the button is disabled during a running turn and a grace countdown, so an open Undo never leaves the screen.
- **AC-14** After a reload the thread is back for that contact, in order: this run's bot turns and this agent conversation's turns, each with its pill, steps, write cards and sent files. A media turn shows its caption, never a blank bubble, and a turn still in progress adds no "(no reply)" line. A waiting proposal can still be confirmed, and a running countdown still shows. A loading skeleton shows until the read lands, and a message sent before it lands loses nothing.
- **AC-15** The read returns only this contact's turns from this run and this agent conversation, never live WhatsApp turns or another run's. It is gated by `system.chat_history.view`, like the rest of the console, and is paginated within the list-limit guard if it takes a limit.
- **AC-16** Switching contact shows that contact's thread. A reply still in flight for the first contact never lands in the second's thread or stored session, and its session still reaches the first contact's store.
- **AC-16b** A thread read never duplicates or reorders a turn: only a thread's first read adds turns, later reads update what is there, and a turn appears once whichever of its read and its reply lands first.

## Memory

- **AC-17** An agent turn sees the recent bot replies of the same thread. A question that follows a bot answer, then routed to the agent, can use that answer. Asserted on what the provider receives. These replies and the customer text with them never enter the system role (rule R10): they go as quoted data messages, in time order around the agent's history, so they cannot forge a speaker. While a proposal waits they are left out of that turn altogether, because only the model reads the "yes" and quoted text must not be able to supply one.
- **AC-18** The bot's input is unchanged: its parser and memory do not read agent turns. Pinned, because a change there needs a prompt gate.
- **AC-19** Bot replies shown to the agent are bounded, and counted within its existing input budget.

## Contacts and screens

- **AC-20** A contact without the agent switched on still gets chat, with the pill saying why. No error banner on load.
- **AC-21** Usable and non-clipped at 375 and 1280, with long tool names, long reasoning and write cards.
- **AC-22** No new on-screen explanation.

## Unchanged, each pinned

- **AC-23** Console turns stay test turns: nothing goes to WhatsApp, and a turn writes no `system_settings` row (`run_turn(switch_overrides=)`).
- **AC-24** Confirmed agent changes stay real, with the operator rules as today (`CHAT/agent/writes.py:72-76`): operator and linked user both need the slug, and the audit names the operator.
- **AC-25** Live WhatsApp turns are unaffected.

## Known limits

- A message sent as a reply to a bubble and routed to the agent does not carry the quote to the agent, as today.
- Agent turns have no message id, so their user bubbles cannot be quoted, as today.
- A follow-up that Jev sends to the bot after an agent reply does not give the bot that reply (AC-18).

## Hand test

Pick an agent-enabled contact. Ask a chat question, then a report question, approve a request and undo it, reload, force the agent once.
