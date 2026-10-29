# UAC: smarter chatbot reports (lane REPORT-SMART-1021)

Plan: `PLAN-report-smart-1021.md`. Every check reads the parser's fields, never the message words.

- AC-RS-1: after a held ranking, a re-typed ask on the same axis that names neither measure nor basis asks both in one
  numbered reply, even when the parser flags it `ranking_refine`; the answer runs with the new ask's own channel and
  filters. A bare refine (`group_by` null) still keeps the held basis and measure.
  (`tests/chatbot/test_report_smart_step7.py`)
- AC-RS-2: a sales analysis or sales report split by sales agent, customer, product, brand, category, location or
  channel runs on the report ask; one question asks only what is missing; a breakdown is never asked "how many".
  (`test_report_smart_capability.py` e1, e2)
- AC-RS-3: a top selling ask ranking customers or sales agents for a product ranks that axis with the product as the
  filter. (e3, e4)
- AC-RS-4: an analysis by month or year, and a top selling ask with no axis, keep their own tools; an axis no sales tool
  draws is still said. (near misses)
- AC-RS-5: a dealer gets the refusal for a staff axis, and its own product breakdown runs. (dealer tests)
- AC-RS-6: "how many dealers sell X" is one distinct count of customers with a sale on that basis in the period;
  orders and products count the same way; a count ranking sorts by the count; the whole set's count is distinct, never
  the rows summed. (`tests/test_report_ask_counts.py`, presenter, e5)
- AC-RS-7: `compare_to` previous_period is the same number of days just before; last_year the same dates a year
  earlier; every row and the total carry the earlier figure and the change on the sort measure, "new" when the earlier
  figure is zero. (`tests/test_report_ask_compare.py`, presenter, lane)
- AC-RS-8: no reply carries `[object Object]`, a tool error string, an error code or an exception name; a period the
  parser wrote in words is asked, never run or echoed. (`test_report_smart_errors.py`)
- AC-RS-9: a sales body neither counted nor compared is unchanged on the wire.
  (`tests/test_report_ask_compare.py::test_no_compare_carries_nothing`, `test_report_ask_chat_route.py`)
