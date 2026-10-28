# PLAN: a swapped line's saved remark tallies with the email

Status: built, reviewer READY, awaiting CI (small fix track: one backend function, no migration, no auth/RBAC change, no new ingest surface)
Lane: SWAP-REMARK-TALLY. Follow-up of PRODUCT-CHANGE-TALLY (#1956).

## Finding

A line AutoCount swapped the product of (OLD61-CR to NEW61-CR) WITH a saved draft (Buy 10): the
Confirm review's split REMARK reads `ORDER`, while the Order Inquiry email line and the attachment
row say the product change too. The preview prefers the board's saved words (`saved_remark`, from
`saved_draft_remark`), which know nothing of the swap.

## Fix

Measured on main: only a draft of the same kinds of decision as the held one (Buy 10 kept, or
the same Buy grown with the line) differed. The email then sends no saved line, only the swap's
settle line (`NEW ITEM CODE`, `ORDER 2, NEW ITEM CODE`). A draft that changes the held decision
(CHANGED) or adds a new kind of part (ORDER 10) already tallied.

- `saved_draft_remark` takes `settle_words` and returns them for a held line with no CHANGED
  whose decision keeps the same kinds (`_queue_saved_line`'s `same_kinds` rule).
- The board (`_swap_settle_words`) reads them off the split read's own `line_plans`
  `remark_generated` for a held line with a PENDING product swap and no splits.

## Known gaps (on main before this lane, follow-ups)

- The email drops NEW ITEM CODE when a swapped line's draft adds a new kind of part (ORDER 10).
- A line whose mirror still names the old product gets no settle words (`mirror_stale`).
- A swap plus a date move with a new kind of part: board `ORDER 10`, email `DELAY, ORDER 10`.
- No test pins the `not plan.involved` / `plan.facts.pending` guards.

## Tests

Red first: swap fixture + saved draft, board `saved_remark` == email remark == attachment REMARK.
Kill test on the fix.
