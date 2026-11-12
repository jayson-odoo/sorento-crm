# UAC: chatbot honest scoreboard (CHATBOT-SCOREBOARD)

Plan: `PLAN-chatbot-scoreboard-12nov.md`. No user-visible change; the reader is the owner's weekly line.

- AC-1 A stock turn whose reply asked the quantity (open `stock_qty` task touched this turn) is
  outcome `clarified`, not `answered_empty`, so it is not a couldn't-find.
- AC-2 A turn whose reply is a pick-one menu (`replied.facts.asking` set, not an escalation offer)
  is `clarified`, not `answered`.
- AC-3 "Couldn't find X. Did you mean Y?" (a did-you-mean product pick) keeps the outcome the lookup
  gave it (`answered_empty` / `missed`): still a miss in the couldn't-find line.
- AC-4 An answer followed by an escalation offer (`team_pick`, `member_offer`, `company_pick`)
  stays `answered`.
- AC-5 Scoreboard technical % = engine failures + delivery failures, where a `send_unconfirmed`
  turn with an outgoing `chat_histories` row for that turn counts as delivered (not a failure).
- AC-6 Scoreboard shows stock couldn't-find and, next to it, dead-end couldn't-find (no code
  offered).
- AC-7 Statement 3 returns one line per week:
  `wk dd/mm/yyyy: stock not-found X% (dead-end Y%), median Z s, asked-again A%, technical T%`.
- AC-8 The classifier reads no reply text and no customer words.
