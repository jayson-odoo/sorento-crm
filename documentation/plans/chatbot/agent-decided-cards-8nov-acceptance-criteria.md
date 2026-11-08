# UAC: AGENT-DECIDED-CARDS

- AC-1: After a card is cancelled, the model's history for the next turn states that the card was cancelled and
  lists its rows.
- AC-2: After a card is confirmed, the history states it was confirmed and which rows were done.
- AC-3: A follow-up batch proposal that repeats a cancelled card's row (same write, same arguments) does not
  propose it; it lists it under "Not changed" as from the earlier cancelled table, unless the user's latest
  message asks for it again.
- AC-4: A follow-up batch proposal that repeats a row a confirmed card already did lists it as already done.
- AC-5: Rows the user asks for in the current message still propose normally.
