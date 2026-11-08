# UAC: agent batch keeps the not-changed rows of the current request (AGENT-BATCH-NOTCHANGED)

- AC-1: A 3-row table where row 3 is not changed and rows 1-2 wait for a pick; the user picks codes; even when the
  model sends only rows 1 and 2, the reply shows row 3 under "Not changed:" with its reason, and the first line
  reads "Rows from your table: 2 ready to confirm, 1 not changed."
- AC-2: The Confirm card holds only the 2 ready rows; nothing is written before Confirm.
- AC-3: A new table sent when no earlier table turn left rows waiting carries no rows from earlier turns.
- AC-4: The batch tool description asks for every row of the current request (ready, waiting and not changed).
- AC-5: The same holds for the tags write: a 5-row tags table, row 3 waiting, rows 4-5 not changed; the pick of row
  3 keeps rows 4 (Already tagged) and 5 (No tag named ...) under "Not changed:".
- AC-6: A one-row request with nothing to change ends "Nothing can change yet; fix what is above and ask again.";
  a table of 2+ rows keeps "...fix the rows above and send the table again."
