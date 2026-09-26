# UAC - Ideation chat reply format (issue #1277)

Plan: `PLAN-ideation-chat-reply-format.md`. Owner's words and transcript: #1277.

## Journey

A dealer tells the WhatsApp bot an idea in their own words, typos and all. The bot echoes it back
as a short point-form recap with bold labels and a clean, readable problem statement, shows them
the recent photos it thinks might belong to the idea (each one numbered) and asks which relate.
Once the fields are in, it shows the recap and asks "Submit this idea? Reply yes to submit, or
tell me what to change."; only a yes creates it, and the final message names the idea by its
title with the idea number and the tracking link.

## Criteria

- **AC-1 Bold labels.** Every ideation reply that carries a field line shows it as `*Problem:*`,
  `*Solution:*`, `*Impact:*`, `*Department:*` (WhatsApp bold), whether the LLM composed it or the
  shared-service template fallback spoke. A label already bold is not double-wrapped.
- **AC-2 Bold is accepted.** A composed reply that already bolds its labels passes the
  deterministic checks (it is not replaced by the template).
- **AC-3 Clean problem statement.** The extractor's problem (and proposed_solution, impact) value
  is a clean statement: conversational preamble stripped, spelling corrected, later detail merged
  into one readable sentence, never joined with a semicolon. `raw_transcript` still carries the
  user's original words. Shipped as a new prompt version of `ideate_extractor` (and
  `ideate_reply`), published to `production` by migration.
- **AC-4 Replay.** The #1277 transcript replayed through the extractor before and after the new
  prompt version is shown in the PR.
- **AC-5 No title line in recaps.** No reply other than `complete` carries a line that is only the
  draft title (quoted or not). The `complete` reply keeps the title on line 1, the idea number on
  line 2 and `Track it here: <link>`. (Ruling assumed per #1277; owner may overrule.)
- **AC-6 Offered images are sent.** On the turn the bot offers recent files, each IMAGE among them
  is sent in the same turn as its own attachment captioned with its menu number (`1`, `2`, ...);
  the text list stays as the question. A non-image candidate keeps its number in the list but is
  not sent. No offer, no attachment send.
- **AC-7 Console shows them.** The chatbot console renders WhatsApp `*bold*` as bold in the bot's
  bubble, and shows each offered image as a thumbnail with its caption under the reply.
- **AC-8 Window.** The images ride the chatbot's existing `send_attachments` action, the same path
  and the same 24h rule as every other chatbot outbound media (a reply to an inbound message, so
  the window is open); a console turn flags the action `dry_run` and sends nothing.

## Round 2: owner console test 26 Sep 2026 14:09Z

Owner rulings of 26 Sep 2026 (PR #1279): no typo or preamble in any field on any turn; typed
punctuation never stored in a value; confirm before create, only a yes creates.

- **AC-9 Clean from turn one.** No field line on any turn shows the user's raw message, a
  conversational preamble or a typo. A captured value the extractor did not produce (the
  intake's seed of `problem`) shows as `still being worked out`; once the extractor produces
  the field, its value shows.
- **AC-10 No typed punctuation.** A `?` or `!` the user typed is never part of a stored value;
  the department is a short Title Case name without "the"/"our" ("the manufactuirng?" becomes
  "Manufacturing", the spelling fixed by the extractor prompt).
- **AC-11 Confirm before create.** A `review` reply is the recap (bold labels, no title line)
  followed by `Submit this idea? Reply yes to submit, or tell me what to change.` as its last
  line; it never asks for another field.
- **AC-12 Only a yes.** In `review`, only a yes (yes, ok, ya, boleh, 好, 可以, also submit /
  confirm) sets `confirm`; a question, a hesitation, an edit or a cancel does not, and the next
  reply shows the recap and the confirm question again. A bare yes submits even when the
  extractor failed. Outside `review` nothing confirms.
