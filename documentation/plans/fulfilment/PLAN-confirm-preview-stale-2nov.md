# PLAN: CONFIRM-PREVIEW-STALE

Status: Plan (small fix track candidate; no migration expected, no auth/RBAC change)

Owner report (2 Nov 2026, Fulfilment Planning): a sales order whose lines are all delivered in
full, with a pending AutoCount change on one line (date 28/09 -> 02/11; suggestion Borrow 3 ->
Buy 3). The Confirm dialog's Review split showed DELIVERY DATE 28/09, NEW DATE blank, breakdown
"Delivered in full: nothing goes to purchasing", REMARK "ORDER BACK". After a board Save, Confirm
did not show the latest decision until a page refresh.

Owner rulings this lane honours: "popup = email = Excel" (26 and 28 Oct); "one bad line never
refuses an order"; "delivered or not doesn't affect our planning" (22 Sep, 12 Oct, 1 Nov); own-bin
borrow emails purchasing (2 Nov).

## Fix (to be detailed after code read)

1. Cache freshness: board Save refreshes the board; opening Confirm re-reads the board and split
   sheets and waits; a newer server decision is never silently overwritten by a stale tab.
2. Review sheet = email rows: delivered lines named by a pending change show NEW DATE and the
   change words; no "nothing goes" note.
3. Warning, never refusal: a saved decision that differs from the pending suggestion is flagged
   with Keep / Take suggestion.
4. Plain Confirm, delivered line with an order back goes to purchasing (remove the #1362 skip).
