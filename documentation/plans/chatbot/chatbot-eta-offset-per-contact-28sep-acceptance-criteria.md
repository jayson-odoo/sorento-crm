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
