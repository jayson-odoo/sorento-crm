# UAC - oi-retire-cancel-email

- AC-1: an AutoCount-deleted line with a raised OI row, plus an added line of another product, on
  one planning change batch: Confirm sends ONE handover email with CANCEL ALL for the old line's
  row and ORDER for the new line.
- AC-2: the deleted line's row prints exactly once (no duplicate CANCEL line).
- AC-3: an `actioned` row on the deleted line stays live (note stamped) and still prints CANCEL ALL
  on the same email, so purchasing can act on it.
- AC-4: a row already cancelled before the apply prints nothing.
