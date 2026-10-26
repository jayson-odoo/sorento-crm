# UAC: CHAT-PO-LOCATION-SCOPE

- AC-1: A contact whose stock-visibility policy names BRW and MWH asks stock of a product with 0
  stock and open PO lines at BRW, BRW-BB and BRW-NTC. The "but PO is placed" list shows the BRW
  line only, with `Location: BRW`. No line without a location is printed for that contact.
- AC-2: The same contact never sees a PO line at a location its stock lines would not show:
  include list, exclusion list, and a merged access-type policy all decide it through
  `warehouse_criterion`, the function the stock lines use.
- AC-3: A sub-location (BRW-BB, BRW-NTC) is its own location: scoped to BRW does not include it.
- AC-4: A PO line with no warehouse is not shown to a contact whose policy names locations.
- AC-5: `availability` mode: rows are scoped the same way and print no location.
- AC-6: An unresolvable contact gets no PO rows (fail closed, same as the stock list).
- AC-7: A contact whose policy names no location list, and any call without `contact_id`, gets
  exactly today's rows.
- AC-8: `summary` (when asked) counts exactly the rows returned.
- AC-9: If every on-order line of a zero-stock product is outside the scope, the rung finds
  nothing and the reply reads "Stock is 0 at every location, no incoming and nothing on order for
  X." (no PO header, no empty list; existing wording, `answer.py:1575-1576`, pinned by
  `tests/chatbot/test_crossdomain_ladder.py:1239`).
