# UAC: WA-PHONE-SHARE-LOOP

- SL1 A tapped card (signed ingress, origin `contact_request`, phone present) from a username-only contact whose
  webhook carries no `channel.meta.wa_id` is accepted and runs the link. A present wa_id that differs is still refused.
- SL2 Accepted card, no Respond.io / CRM contact holds the phone: phone set on the contact (Respond.io PUT + CRM row),
  no template, branch `phone_linked`.
- SL3 Accepted card, link step fails: one staff comment, no template, branch `phone_handoff`.
- SL4 Any later message (card or text) from a contact whose card was accepted: never the template.
- SL5 The trace of a refused card names the check that refused it (no phone in the trace).
