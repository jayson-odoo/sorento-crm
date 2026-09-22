# UAC: stock ask with no placed subject (hotfix, 22 Sep 2026)

Plan: `PLAN-chatbot-stock-no-subject-hotfix-22sep.md`. Track: small fix.

Covering test named beside each AC. `R13` is
`tests/chatbot/test_rearch_r13_stock_no_subject.py`.

- AC-1790 An inventory turn whose fetch carries no entity with a uuid (none named, or
  the carry placed only as a kind inventory does not take) never calls
  `crm_inventory_stock_balance_list`.
  `R13::TestT1CarriedIncompatibleSubjectNeverFetchesTheWholeBook::test_the_stock_tool_
  is_never_called_for_a_carry_that_placed_as_a_set` +
  `R13::TestT2BareStockAskOnAFreshContact::test_a_bare_stock_ask_never_calls_the_stock_
  tool`.
- AC-1791 That turn replies with production's scope-needed wording ("That would search
  every stock we have - I need at least one filter to narrow it down. ..."), never a
  listing, never "Stock details found".
  `R13::TestT1...::test_the_reply_is_productions_own_scope_needed_sentence` +
  `R13::TestT2...::test_a_bare_stock_ask_replies_with_the_scope_needed_sentence`.
  The wording holds on a SINGLE-domain turn. A multi-domain fan-out ("stock and
  promotions", no entity) still satisfies AC-1790 - the refusal is per `FetchSpec` -
  but renders `fetch.NO_RESULT_INTRO` ("No matching results found.") instead of the
  sentence, because `engine.py`'s `bridge_answers_a_miss` requires
  `len(fetch_plan.fetch) == 1` before `answer_bridge.answer_for` composes a miss at
  all. Accepted for this hotfix; widening it means changing who composes a
  multi-domain miss.
- AC-1792 The live chain (turn 59 did-you-mean roster still open, turn 60 "Stock")
  satisfies AC-1790 and AC-1791.
  `R13::TestT1CarriedIncompatibleSubjectNeverFetchesTheWholeBook` (both tests).
- AC-1793 A bare "stock?" on a fresh contact satisfies AC-1790 and AC-1791.
  `R13::TestT2BareStockAskOnAFreshContact` (both tests).
- AC-1794 `intent_hint: low_stock_report` with no entities still runs its tool
  (`INTENTS_ALLOWING_EMPTY` unchanged).
  `R13::TestT3LowStockReportStillRunsWithNoEntities::test_a_scopeless_low_stock_report_
  still_calls_its_tool`, plus `tests/chatbot/test_low_stock_lane.py` (21 tests).
- AC-1795 An inventory ask with at least one placed entity (product, warehouse,
  category or brand uuid) still calls the stock tool with that filter.
  `tests/chatbot/test_rearch_r12_phase3_fixes.py::TestP9GuardStockToolStillCalledWhen
  OneEntityPlaces::test_one_unplaced_word_plus_one_placed_product_still_calls_stock_
  tool` (stays green).
- AC-1796 `tests/chatbot/test_turn_replay.py` corpus stays green (no DIVERGENCES entry
  added). The corpus itself is the test (97 passed, 133 skipped, 1 xfailed).
- AC-1797 A turn that NAMED a subject which did not resolve (the R6/R8 shape,
  "Srtks8060-BL stock") still refuses the tool and keeps its own "could not find it"
  miss wording - the scope-needed sentence never replaces it, and the refusal's
  fragment carries no `scope_gate`.
  `R13::TestT4AnUnresolvedTypedTokenKeepsTheOrdinaryMiss` (both tests; the
  `..._fragment_never_carries_a_scope_gate` one is red without the guard), plus
  `tests/chatbot/test_rearch_r12_handpass12_d.py` and
  `tests/chatbot/test_rearch_r8_recheck_round.py` staying green.
