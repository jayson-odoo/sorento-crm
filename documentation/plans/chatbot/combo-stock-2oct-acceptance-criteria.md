# UAC: combo (product set) stock in the chatbot (COMBO-STOCK)

Plan: `PLAN-combo-stock-2oct.md`. Tests: `sorento_crm_backend/tests/chatbot/test_combo_stock.py`
(engine-level, real resolver / gate / narrower, stock tool stubbed). Console cases:
`tests/chatbot/console_cases/2026-10-02-combo-stock.yaml`.

Full access = stock visibility `detailed` or `compact`; dealer = `availability`.

- AC-CS1 A stock ask naming a set code (a `product_sets.set_code`) calls the stock tool with
  exactly that set's `product_set_members`, never refused as filterless.
- AC-CS2 Full access: the reply opens with "*SET* is a set of A x1, B x1, C x2.",
  "Complete sets: N (limited by M)" and "By location: L1 n1, L2 n2", above the unchanged member
  lines. N = min over members of floor(member stock / qty per set), counted from the SAME stock
  rows the member lines print; a member with no row counts 0; a discontinued member counts 0;
  a tie names the first member in set order.
- AC-CS3 Dealer: a set code gets the existing availability lines only; no header, no number.
- AC-CS4 Full access, base code (typed token is no product's own code, products reached by
  prefix): the reply keeps its lines and adds "X is part of set(s) A, B - ask for the set code
  to see full-set stock." for each product in at least one active set of the caller's company.
  A code typed in full never gets the line.
- AC-CS5 Dealer, base code whose answer is only that base code's products: the reply is
  "BASE is part of N sets. Which one?" plus the numbered sets; picking one runs the stock ask
  over that set's members. A message that also names another product keeps its availability
  answer.
- AC-CS6 Membership only ever comes from `product_set_members`; inventory stock asks only.
