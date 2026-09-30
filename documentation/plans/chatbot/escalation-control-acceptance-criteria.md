# UAC: escalation control

1. A contact whose only access type is "Sorento Dealer" and no override: no-result answer carries
   no customer service offer; no member picker.
2. Same contact says "talk to a human": reply is the salesperson referral, no handoff.
3. Same contact replies "yes" to an older offer: no handoff.
4. Staff profile behaviour unchanged.
5. Dealer with contact override = allow: offers and handoff work as before.
6. Non-dealer contact with override = block: behaves like 1-3.
7. Contact Chatbot section shows "Can escalate to customer service" as inherit / allow / block
   with the inherited value; access-type editor shows the attribute.
