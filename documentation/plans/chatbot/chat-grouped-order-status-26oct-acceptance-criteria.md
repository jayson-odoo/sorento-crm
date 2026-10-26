# UAC: CHAT-GROUPED-ORDER-STATUS

Plan: `PLAN-chat-grouped-order-status-26oct.md`.

- AC-1: A delivery order check grouped by customer (or any orders `group_by` axis) answers with
  each group's orders listed; the turn never fails with "Sorry, I ran into a problem".
- AC-2: In a grouped answer, Status reads as the status name (for example "Delivered"), exactly as
  it does in the ungrouped list; no raw object, no id.
- AC-3: Group rows of the orders list tool carry no UUID (`id`, `company_id`, ...) and are trimmed
  the same way as the flat rows.
- AC-4: Any answer row whose field value is an object or a list no longer crashes the reply
  composer; two identical rows are still shown once.
- AC-5: An outstanding sales order list prints each row's Customer, flat or grouped.
