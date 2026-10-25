# PLAN: sales target achievement and sales opportunities over the chat (SALES-TARGET-CHAT)

Status: **scout (25 Oct 2026).** Behaviour card filed to the owner as one `crew report --ask`; no product
code until the owner answers. Size estimate and track are set in the card. Lane branch
`crew/sales-target-chat`, base origin/main b2f15efb32.

## Owner ask (25 Oct ~19:17 MYT, verbatim)

"btw for sales targer right, we need to look into exposing this via rhe chat for dealer and salesperson to
check the sales target achievements and be able to create sales opportunities to hit the target"

## Scope of the scout

1. What exists: the target engine (salesperson targets #1297, sales teams #1260, dealer targets and incentive
   schemes #1715), its achievement service, endpoints and permission rules.
2. The chatbot seams a new read intent and a new write flow would use (parser route, executor, MCP tool,
   renderer, audience gating, confirm step).
3. What the CRM calls a sales opportunity today and how one is created.
4. Real examples from the crew dev DB (sorento_prod_1020, read-only), personal data masked.

## Measured facts

Filled from the scout; every line cites file:line or a query.

## Behaviour card

Filed as the lane ask; copied here once the owner answers.

## Owner rulings

None yet.

## Slices

Proposed in the card; fixed here after the owner answers.
