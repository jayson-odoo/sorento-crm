# UAC: escalation control

1. A contact whose only access type is any dealer type (Sorento / Cabana / Mocha / NL Dealer) and no override: no-result answer carries
   no customer service offer; no member picker.
2. Same contact says "talk to a human": reply is "Please refer to your salesman.", no handoff.
3. Same contact replies "yes" to an older offer: no handoff.
4. Staff profile behaviour unchanged.
5. Dealer with contact override = allow: offers and handoff work as before.
6. Non-dealer contact with override = block: behaves like 1-3.
7. Contact Chatbot section shows "Can escalate to customer service" as inherit / allow / block
   with the inherited value; access-type editor shows the attribute.
8. The migration seeds every access type whose name ends in the word "Dealer" (any case) as
   barred, and leaves every other type allowed.
