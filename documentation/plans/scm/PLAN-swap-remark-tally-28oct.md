# PLAN: a swapped line's saved remark tallies with the email

Status: in progress (small fix track: one backend function, no migration, no auth/RBAC change, no new ingest surface)
Lane: SWAP-REMARK-TALLY. Follow-up of PRODUCT-CHANGE-TALLY (#1956).

## Finding

A line AutoCount swapped the product of (OLD61-CR to NEW61-CR) WITH a saved draft (Buy 10): the
Confirm review's split REMARK reads `ORDER`, while the Order Inquiry email line and the attachment
row say the product change too. The preview prefers the board's saved words (`saved_remark`, from
`saved_draft_remark`), which know nothing of the swap.

## Fix

The board's saved remark for a swapped line says exactly what the email says, through the same
function the email uses (no second copy of the rule).

## Tests

Red first: swap fixture + saved draft, board `saved_remark` == email remark == attachment REMARK.
Kill test on the fix.
