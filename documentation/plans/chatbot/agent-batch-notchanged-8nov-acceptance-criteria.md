# UAC: agent batch keeps the not-changed rows of the current request (AGENT-BATCH-NOTCHANGED)

- AC-1: A 3-row table where row 3 is not changed and rows 1-2 wait for a pick; the user picks codes; even when the
  model sends only rows 1 and 2, the reply shows row 3 under "Not changed:" with its reason, and the first line
  reads "Rows from your table: 2 ready to confirm, 1 not changed."
- AC-2: The Confirm card holds only the 2 ready rows; nothing is written before Confirm.
- AC-3: A new table sent when no earlier table turn left rows waiting carries no rows from earlier turns.
- AC-4: The batch tool description asks for every row of the current request (ready, waiting and not changed).
