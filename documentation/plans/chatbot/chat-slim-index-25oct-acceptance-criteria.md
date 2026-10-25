# UAC: CHAT-SLIM-INDEX slice 1 (a product kind on a sales total), 25 Oct 2026

Plan: `PLAN-chat-slim-index-25oct.md` section 4. Status: DRAFT, waiting for the owner's answers (plan section 8).
Prompt: production v63 (md5 0f3b48e6) unchanged. Customer names masked (public repo).

## Journey

A staff member asks the chatbot for one dealer's total sales in a month, narrowed to a kind of product, in one
message. They get the total in one reply, without being asked which customer or shown a promotion file.

## Acceptance criteria

- AC-1: "Dealer <customer F> oct total sales for water closet" answers customer F's October total for products of
  class / category Water Closet, in one reply; the dealer channel applies when the parse carries it.
- AC-2: no customer pick is built from a word of a product-kind span: "water" in "water closet" never lists
  customers whose name contains WATER.
- AC-3: a product-kind span never resolves to a promotion, a promotion file name, a customer or a transporter;
  when it matches no category / class it is said back ("no product kind called <word>"), and the rest of the ask
  is still answered or asked once.
- AC-4: a customer pick whose options merge into one company is no pick: the ask runs for that company.
- AC-5: "Dealer <customer F> oct total sales" answers customer F's October total even when the parse says
  sales_analysis.
- AC-6: the same product-kind filter works on every report ask that already supports it (sales ranking keeps its
  current behaviour; its tests stay green unchanged).
- AC-7: a product code in the same sentence keeps the exact-code path ("SRTWC286 oct total sales" unchanged).
- AC-8: a customer whose name contains a product-kind word still resolves as a customer when the parser hints it
  customer.
- AC-9: the parser's input (system prompt + user block) is byte-equal to main's on every TRAIN, R5 and console item
  (no parse moves).

## Edge cases

- Two categories match the span equally (e.g. a class label and a category name that differ): one question with at
  most 3 options.
- The class filter leaves zero sales lines: the answer says the total is 0 for that filter, it never drops the
  filter silently.
- The span carries a typo or a Malay / Chinese word: out of scope for slice 1 (phase 2, the span index); slice 1
  says the word back (AC-3).
