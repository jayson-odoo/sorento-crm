# PLAN: AutoCount write-back phase 2 (CRM side): quotation + sales order create / update / cancel from project sales

Lane: AC-QTSO-CRM. Status: Plan (behaviour card being drafted; no code before the owner answers).
Track: full pipeline (writes to an external system, new admin switch, security review required).

## Owner rulings carried in

- AutoCount is the source of truth. Every write is followed by a GET read-back.
- CRM decides intent; the Shared Service (SS) owns the AutoCount steps. Writes only reach the db3 test book until sign-off (SS guard).
- Never delete an AutoCount document; cancel instead. Anything needing the SS delete door is greyed "Waiting for AutoCount".
- Ships inert: an admin switch, default OFF, hides every write action and the API refuses.

## Behaviour card

To follow (posted as a crew-ask on the PR, then copied here with the owner's answers).
