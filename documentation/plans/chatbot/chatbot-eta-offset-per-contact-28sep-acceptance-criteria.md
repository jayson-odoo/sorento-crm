# UAC: chatbot ETA offset per contact, deniable container and quantity, incoming packing list gate

Plan: `PLAN-chatbot-eta-offset-per-contact-28sep.md` (issue #1328)

- AC-EO1: a contact with the switch ON asking stock for a product with a known shipment and
  offset y sees ETA = shipment ETA + y days (today's behaviour).
- AC-EO2: the same contact asking incoming for the same product sees the same padded ETA
  (and a padded ETA delay when one is recorded).
- AC-EO3: a contact with the switch OFF sees the exact shipment ETA on both routes.
- AC-EO4: a product with no offset set on itself or its category shows the exact ETA with
  the switch on.
- AC-EO5: a staff caller with no contact in play sees the exact ETA (unchanged).
- AC-EO6: the switch is shown and edited on the contact's Access > Chatbot card; default ON.
- AC-EO7: "Container number" and "Quantity" appear in the Incoming Stock Enquiries field list
  and in the "Fields for <contact>" dialog; allowed by default.
- AC-EO8: denied on the agent, the incoming reply has no container number and no quantity
  keys (absent, not null); a per-contact "allowed" exception restores them for that contact.
- AC-EO9: an incoming answer for a contact whose "Packing list allowed" is off carries no
  attachment; for one whose switch is on it carries the packing list.
- AC-EO10: an incoming ETA window ("arriving before X") is judged on the date the contact is
  told, and a full page of rows that pad out of the window never hides a later match.
- AC-EO11: a row naming several products is padded by the largest of their offsets.
- AC-EO12: the single-shipment routes (`/shipments/{id}/products`, `/shipments/{id}/attachment`)
  follow the same contact rules.

Fix round, owner hand test 28 Sep 2026:

- AC-EO13: a dealer (availability-only policy) whose stock ask the parser reads as stock
  gets the availability answer ("How many units of X?", then one sentence per product) and
  never the incoming reply. The routing half (a stock or incoming word winning over the
  parser's reading or the carried focus, "stoick X", "X x 150") was stripped on 29 Sep
  2026 by owner ruling and moves to the picker lane on #1352.
- AC-EO14: WITHDRAWN 29 Sep 2026 (routing patch stripped, owner ruling on #1352); the
  incoming-word routing belongs to the picker lane.
- AC-EO15: a dealer's incoming reply is one message: per product, the code once and its
  distinct ETAs sorted (padded by the contact's offset rule), then "Please refer to your
  salesperson, <name>." (or without the name when the contact has no salesperson); no
  container, quantity, allocation, packing list, numbering or intro.
- AC-EO16: two incoming lines that read the same after the contact's view is applied print
  once; staff keep today's full incoming reply.
