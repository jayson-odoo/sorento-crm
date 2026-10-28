# PLAN: product swap as Was/Now, and email = confirm preview = attachment

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface)
Lane: PRODUCT-CHANGE-TALLY

## Owner report (28 Oct)

SO426847 line 48: AutoCount edited the line's product in place (same line key), SPSRT61-CR to
SRT61-CR. The Order Inquiry EMAIL shows ITEM CODE (old) and NEW ITEM CODE (new). The confirm
popup preview did not show the old and new product columns, and the board / SO page show the
product swap only as a sentence, not as a row in the yellow Was/Now table next to Qty and Date.

## Scope

1. Product is the first row of the yellow Was/Now table (board and SO page). The separate
   "Product changed, was X" sentence and the "without changing its quantity..." line go away
   when the product moved. The SO page reads the old product from `from.item_code`.
   Suggestion lines on the SO page stay out of scope.
2. The confirm preview and the attachment show the same line columns as the email, from one
   shared row builder, with a test that renders all three from one fixture.
3. Hand test script with SO426847-like data.

## Acceptance

See the PR body and the hand test comment.
