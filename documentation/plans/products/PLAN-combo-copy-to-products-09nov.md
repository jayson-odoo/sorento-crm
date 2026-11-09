# PLAN: Copy a product combo to other products (COMBO-COPY-TO-PRODUCTS)

Status: Plan (behaviour card posted, waiting on owner answers). Track: TBD after card answers.

## Journey

Owner, 9 Nov 2026: many bathtubs carry the same combo. Today a combo is built inside one
product's page. The owner wants the reverse: on a product's Combos card, pick one combo and
copy it to many other products in one go.

## Scope (so far)

- Button on each combo on the product detail Combos card: "Copy to other products".
- Reuses the product picker dialog from ACC-COPY-TO-PRODUCTS (#2280).
- One atomic server call, audited.

Behaviour card and open questions: posted on the lane PR as `crew-ask`.
