# UAC - Ideation chat reply format (issue #1277)

Plan: `PLAN-ideation-chat-reply-format.md`. Owner's words and transcript: #1277.

## Journey

A dealer tells the WhatsApp bot an idea in their own words, typos and all. The bot echoes it back
as a short point-form recap with bold labels and a clean, readable problem statement, shows them
the recent photos it thinks might belong to the idea (each one numbered) and asks which relate.
When they confirm, the final message names the idea by its title with the idea number and the
tracking link.

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
