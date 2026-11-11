# PLAN: COST-ACCESS-UNIFIED - one cost-visibility rule everywhere

Status: Plan (size M, permission change; security-reviewer required). Behaviour card pending owner answers.

Owner go (12 Nov, chat): "I agree the cost access should be centralized and unified."

## Goal
One cost-visibility rule: role permission `products.cost.view` on the person's user, checked in one
shared place that the chatbot (WhatsApp), the staff agent, the AI panel and the screens all call.
A WhatsApp sender is a contact: resolve it to its linked user; no linked user or an inactive user
means no cost.

(Behaviour card, UAC and slices follow once the owner's answers arrive.)

## Behaviour card (crew-ask, posted on PR #2354)

### What the code does today (verified on this branch's base, 001ca053)
- Screens and staff API: `products.cost.view` through `app/services/cost_access.py:47-65`
  (`can_view_cost`, `holds_cost_view`).
- AI panel (staff principal): `chatbot/principal.py:57-62` maps the user's permissions to reveal keys
  (`contact_field_reveal_service.py:104` maps `purchase_orders.cost` -> `products.cost.view`). Already the role rule.
- WhatsApp business lane: refuses the `purchase_cost` domain unless the CONTACT holds the stored key
  (`lanes/business/answer.py:1240-1241`, keys from `head/access.py:46-61` -> `granted_keys`).
- Agent, contact WITH a linked user: tool needs `products.cost.view` on the user AND the contact key
  (`agent/tools.py:121`, `agent/access.py:147`). Contact with NO user: contact key only (`agent/tools.py:163`).
- Dealer "my cost" -> promotions when the contact lacks the key (`engine.py:10873-10898`). Kept.
- Contacts list "Cost" column, filter and sort read the stored key (`contact_service.py:187,314,360`;
  FE `ContactsList.tsx:611-617`, `ContactAccessFilters.tsx:160`); the Access tab checklist toggles it
  (`contact_field_reveal_service.py:64`, FE `ContactFieldRevealsSection`).
- A contact has at most ONE linked user: partial unique index `uq_users_respond_contact_id`
  (`models/user.py:148-151`). "Linked to several users" cannot happen.

### Proposed rule
A person sees purchase cost if and only if their user (role) holds `products.cost.view`. For a WhatsApp
contact the person is its linked ACTIVE user; no linked user, or an inactive one, means no cost.
One function decides it: `cost_access.contact_can_view_cost(db, contact_pk)` -> linked active user ->
`can_view_cost`. `granted_keys_for` (`contact_field_reveal_service.py:144`) computes the
`purchase_orders.cost` key from that function and ignores the stored row, so every chatbot/agent seam that
reads granted keys gets the same answer with no per-seam change.
