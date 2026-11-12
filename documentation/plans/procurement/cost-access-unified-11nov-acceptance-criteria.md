# UAC: COST-ACCESS-UNIFIED

Owner answers (crew relay, 12 Nov): Q1 (a) retire the contact cost switch, Q2 (a) keep the Contacts list
Cost column + filter computed from the linked user, Q3 (b) dealers keep promotions, Q4 (a) no user = no cost
tool, Q5 (a) bulk copy stops copying the cost key.

"Cost viewer" below = a user with status ACTIVE who holds `products.cost.view` by the existing permission
check (`UserPermissionService.check_user_has_permission`, so admin/superadmin roles hold it by bypass).
"Linked user" = `users.respond_contact_id = respond_contacts.id` (at most one, `uq_users_respond_contact_id`).

- AC-1 `cost_access.contact_can_view_cost(db, contact_pk)` is True iff the contact's linked user is a cost
  viewer. No contact, no linked user, inactive linked user, linked user without the permission: False.
  Fails closed (False) on a lookup error.
- AC-2 `contact_field_reveal_service.granted_keys` / `granted_keys_for`: `purchase_orders.cost` is present
  iff AC-1 is True for that contact. A stored `contact_field_reveals` row for the key (granted or not) has
  no effect either way. Every other key behaves exactly as before.
- AC-3 WhatsApp business lane, `purchase_cost` ask: answered for a contact whose linked user is a cost
  viewer even with no stored cost row; refused with the existing wording for a contact holding a stored
  granted row whose linked user lacks the permission, is inactive, or does not exist.
- AC-4 Dealer contact whose linked user is not a cost viewer (or no user): "my cost" still reads as the
  promotions ask (`engine._dealer_cost_as_promotion`), stored row or not. Dealer whose linked user IS a
  cost viewer: the cost answer, not promotions.
- AC-5 Agent: a contact principal (no linked active user) never gets `crm_procurement_po_last_cost_list`,
  stored row or not. A user principal gets it iff the linked user holds `products.cost.view` (no stored
  row needed); a stored row without the permission gives nothing.
- AC-6 Contacts > Access field-reveal checklist: the list of keys offered (`field_reveal_keys()` and its
  API) no longer contains `purchase_orders.cost`; a save (`set_granted_keys`) never creates, grants or
  revokes a `purchase_orders.cost` row, whatever the list sent; existing rows are kept untouched.
- AC-7 Bulk copy access: copying from a source holding a cost row creates or changes no cost row on the
  target, and the target's cost visibility is unchanged.
- AC-8 Contacts list: `cost_visible` on each row equals AC-1. Filter `cost=yes|no` and sort on
  `cost_visible` run in SQL on the same rule (stored rows ignored), so a sorted/filtered page 2 agrees.
- AC-9 Unchanged: staff screens / API (`holds_cost_view`, `require_cost_view`), the AI panel's staff
  principal (`staff_reveal_keys`), and every non-cost reveal key (DO defaults, sellable, supplier, ...).
