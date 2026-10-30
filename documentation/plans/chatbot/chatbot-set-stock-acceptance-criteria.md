# UAC: CHATBOT-SET-STOCK

From the owner's answers on card v3 (30 Oct 2026 ~17:35): "1 resolver change the resolver should
be able to identify it as set also, 2 it should be the same as existing logic for product, 3 we
should just show all product under the set, simple as that, 4 the logic should still be the same
as current, 5 i don't think we need prompt change".

Tests: `sorento_crm_backend/tests/chatbot/test_chatbot_set_stock.py` (SS-1 to SS-8, SS-10 to SS-12),
`tests/chatbot/test_code_lookup_set_codes.py::test_gate_off_the_set_only_code_answers_its_members` (SS-4),
`tests/chatbot_eval/test_parser_gold.py::test_set_stock_gold_file` (SS-9).

- SS-1. A catalogue code that no product or set carries exactly (SRTWC7405, SRTWC8826) resolves to
  every active set whose code holds it, each with its members. Resolver, both modes.
- SS-2. "Pls check stock srtwc7405 x 6 sets" (staff) fetches the stock of every member of every
  such set: tank (X), bowl (Y) and seat cover (SC), never the seat cover alone.
- SS-3. The reply lists each set under its own "Set <code>" heading with all its parts, in
  today's product stock format (same fields, same per-location rows, same O/S). No new set maths.
- SS-4. A full set code (SRTWC8826-S) answers its members with or without the CODE LOOKUP prompt
  section. A full set code that heads other set codes also answers those (same rule as a product
  code, which brings its variants).
- SS-5. "stock srtwc8826" fetches both tanks, the shared bowl and the seat cover once each.
- SS-6. A set with a member the contact may not see is not expanded; the hidden part is never
  fetched. The visible products holding the code still answer.
- SS-7. A member code typed in full (SRTWC7405-SC) answers that product (and its usual variants),
  never its sets, tank or bowl.
- SS-8. An availability-only contact asking "srtwc8826 x 6 sets" gets every part of the sets
  checked (the existing got-stock verdict per part, no numbers).
- SS-9. No parser prompt change: gold rows for set asks expect no canonical code for a catalogue
  or set code the shortlist does not list (the resolver finds the sets), and a member's own code
  picked as itself.
- SS-10. (owner, card v4 Q1 a) Every domain that takes products expands a visible set to its parts:
  stock, product info, ETA, photos and files, promotion, orders, sales and delivery, SPO, last cost, PO.
  "srtwc8826 eta" checks the ETA of both tanks, the bowl and the seat cover, never the seat cover alone.
- SS-11. (owner, card v4 Q2 / Q3) A set is never a choice and never asks "how many sets": in ETA and photos
  a set's parts resolve; only products outside every matched set can still make today's picker. No set
  maths and no "Complete sets" line.
- SS-12. A set the contact may not see is never expanded, in any domain.
- Unchanged: long-answer caps and paging, price dropped for set members, company and brand scope, today's
  numbered quantity list for products (owner Q4 a).
