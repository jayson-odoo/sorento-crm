# PLAN: COST-ACCESS-UNIFIED - one cost-visibility rule everywhere

Status: Build complete, in review / hand test (track M, permission change; security-reviewer done, PR #2354).

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

## Owner answers (crew relay, 12 Nov)
Q1 (a), Q2 (a), Q3 (b), Q4 (a), Q5 (a). UAC: `cost-access-unified-11nov-acceptance-criteria.md`.

## Slices (one lane, one PR)
1. Backend rule: `cost_access.contact_can_view_cost` + a SQL form of it for the list; `granted_keys_for`
   computes the cost key from it; checklist + copy-access stop handling the key (key stays in the
   `FIELD_REVEAL_KEYS` literal so the catalogue pin test and `staff_reveal_keys` keep working; a
   `RETIRED_CHECKLIST_KEYS` set hides it from the checklist and from `set_granted_keys`).
2. Contacts list `cost_visible`, filter, sort from the SQL form.
3. Copy text that says "contact holding purchase_orders.cost" (`mcp_catalog_copy.py:1642`,
   `reused_tools.py:637`, docstrings) reworded to the role rule. No frontend code change expected: the
   checklist renders the server's key list and the Cost column already reads `cost_visible`.
4. User guide: contacts access page + the cost permission page.

Track: M (permission change) -> security-reviewer required. No migration (stored rows kept, ignored).

## Test list (tester)
pytest, Postgres fixture: AC-1..AC-9, plus updates to existing tests that pin the old rule
(`tests/test_contact_field_reveals.py`, `tests/chatbot/test_dealer_my_cost.py`, `tests/chatbot/test_last_cost_gate.py`,
`tests/chatbot/test_chatbot_field_reveals_api.py`). No paid API calls: chatbot turns use the existing fixtures.

## Standing rules that apply
- AI/chatbot: "states only what the data holds", refusal wording unchanged.
- Lists: Cost column still sorts on the server; filter still multi-value-safe (yes/no).
- Data: no automatic joining by name (link is the explicit `users.respond_contact_id`).

## Progress
- Red tests e24d2d82 (60) and 9614699b (8, tag settings); code c8d92c17, 8f9e05a5, 67098dd1.
- Reviewer: tag settings blocker fixed in 67098dd1; kill tests pass. Security review: no blockers.
- Browser pass PASS at 1280 and 375 on 1f39f8e8.
- Pre-existing, out of scope: agent `eligible_contact` ignores workspace on a shared respond.io id;
  30s RBAC cache delays a role revoke on WhatsApp.
