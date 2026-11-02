# UAC: chatbot failure review, PR #2061 (1 Nov 2026)

Owner: "when the stock lookup fails, the bot shouldnt say no stock. Its a very dangerous business consequences."
"Gemini timeout can retry up to N times with configurable." "Please dont guess all the thing. Prove it."

## AC-1 A failed stock, incoming or on-order read never claims an absence

Scope is those three, as the owner asked. A failed promotion read can still say "no promotion": found in review, the
same before this PR, and reported to crew rather than widened here.

- AC-1a A stock read that fails in any way (timeout, tool error, dropped connection, HTTP error envelope, plain text)
  replies "I could not fetch stock just now, please try again." and nothing else: no "No stock", no "No incoming", no
  salesman line, no further lookup.
- AC-1b The same for an incoming read, for a contact asking about several codes, and with or without a quantity.
- AC-1c The CRM failing behind the MCP server (connection refused or dropped, a read timeout, an unreadable or oversized
  body) reaches the chatbot as an error, for every presenter tool, so no report prints a zero total over it.
- AC-1d A PO rung that fails does not say "nothing on order". The stock and incoming absences it follows were read, so
  they stand.
- AC-1e A plain-text answer on a multi-ask line reads as a failed line, not "Stock: 0".
- AC-1g A failed probe stamps no "- no incoming" on a roster or a related-products line. The codes are still offered.
- AC-1f A read that worked and found nothing still says "No stock and no incoming".

## AC-2 A model call that hung or lost its connection is tried again

- AC-2a A timeout or dropped connection is tried again up to `CHATBOT_LLM_RETRIES` times, default 3, 0 turns it off.
- AC-2b Every attempt and wait stays inside the 35 s call budget; a retry with under 5 s left is not started.
- AC-2c A refusal (a 400, a safety block) is not retried.
- AC-2d Every model call but the parser states its own budget: the clarifier and the chat report extractor keep one
  attempt's time, so a parser retry does not stack a second 35 s on one turn.
- AC-2e The parser answers after one timeout, where the turn used to fail.
