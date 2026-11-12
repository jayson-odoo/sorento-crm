# PLAN: sales targets count "Invoiced" (TARGET-INVOICED)

Status: in progress (standard track: carries a migration widening `ck_sales_targets_basis`)

## Journey

Owner, 4 Nov ~13:30 MYT: "for slaes target, we cannot set 'Invoiced'? cause now we have all the
billing documents in the production already". Sales > Targets > a target > What counts: the basis
offers only Ordered and Delivered.

## Rulings followed

- Sales definition (27 Oct): sales = IV + CS + DN - CN, net (`local_net_total`), by DocDate, not
  cancelled. `app/services/sales/invoiced_sales.py` is the one place the sign and the predicate live.
- One shared sales service (27 Oct): the Invoiced achievement reads `invoiced_sales.posted()`,
  `signed_amount()`, `signed_line_amount()`, `signed_line_quantity()`, `agent_id()`. No second
  definition of a sale.
- "Invoiced" is the first choice (chatbot basis ruling); the target screen preselects Invoiced for
  a new target, saved targets keep their basis. The API and column defaults stay `ordered`, so
  the dealer import and API callers keep their behaviour.
- No extra permission (owner, 4 Nov, crew-ask answer (a)): whoever may view a target sees its
  achievement on any basis; the target's own scope rules apply unchanged (tested).

## Build

1. `sales.targets.basis` accepts `invoiced` (model CHECK + migration, schema `Basis` literal).
2. `achievement_service`: invoiced periods are counted by a separate statement over
   `finance.billing_documents` (+ lines when the target scopes products or measures quantity),
   per period by `doc_date`, credited:
   - agent: the sale's agent (`invoiced_sales.agent_id()`, which honours the company's agent
     source) is the agent or a label sibling;
   - team: a member stay whose window covers the document's date;
   - dealer: the document's customer is one of the target's counted accounts (split per account).
   Amount, all products: the document's signed `local_net_total` (tallies AutoCount to the cent).
   Amount, scoped: signed line net x rate over the in-scope lines. Quantity: signed line quantity
   (a credit note line's quantity counts negative, so a returned unit nets out in the CN's period).
3. Every reader of `basis` handles `invoiced` (listed in the PR).
4. FE: basis select offers Invoiced first; Counts label "Invoiced". A dealer's Invoiced figure is
   never marked "provisional, incl. tax" (record Periods and Accounts tabs, list column, chatbot
   line); a mixed dealers list marks each provisional figure with `*`.
5. Owner add-on (4 Nov): read-only Details of a dealer target shows the Accounts field (code -
   name, one per line) as Edit does, never "Dealer: <name>". Dates stay with DATE-FORMAT-UNIFY.

## Tests (red first)

- invoiced target over a period with IV + CS + DN + CN for the target's accounts equals the shared
  sales total; cancelled excluded; doc_date decides the period; qty nets CN; scoped amount.
