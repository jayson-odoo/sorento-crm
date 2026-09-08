# UAC: broaden_axis beside a new activity domain is a switch

Plan: `PLAN-broaden-domain-switch.md`. All tests in `sorento_crm_backend/tests/chatbot/`.

AC-1  "Any incoming" after a stock turn (prev inventory/check_stock, prior entity srtwc286
      product; model incoming/check_incoming, broaden_axis all, scope_intent broaden,
      entity_op clear, entities []) -> domain_hint incoming, intent_hint check_incoming,
      entity_op_applied reuse, entities == the prior product, broaden_axis None,
      scope_intent None, domain_switch_over_broaden == "inventory",
      broaden_axis_domain_restored absent. Unit test in test_output_exchange_rules.py.
AC-2  Same shape with prev entity hint "customer" (blocked under incoming) -> domain switches,
      entity_op stays "clear", entities []. Unit test.
AC-3  Same shape with a current_message product entity in the model output -> domain switches,
      entity_op left as emitted, executor result unchanged from today for that op. Unit test.
AC-4  "all products" mid-order (existing test_r4_widening_one_axis_keeps_the_question_it_was_asked_about)
      still restores to order: master_products is a catalogue domain. Existing test green.
AC-5  Date widen with model domain_hint null + prev order -> restore fills order as today.
      Unit test (mirrors captures e4381b0d / 98526b81).
AC-6  Model domain == prev domain with broaden_axis all + clear -> restore path as today
      (genuine "show me everything"). Unit test.
AC-7  Model domain != prev but intent NOT in DOMAIN_SPEC[model domain].intents -> not a
      coherent pair, restore as today. Unit test.
AC-8  parser-15121180 vendored + field-scoped divergence; `pytest tests/chatbot/test_replay.py
      -q` green on the vendored set; the full-corpus replay reports no NEW red beyond the 57
      pre-existing ones in #755 (list the reds before and after, diff must be empty).
AC-9  End to end through `engine`: a two-turn run "check stock srtwc286" then "Any incoming"
      against the local DB ends in the incoming domain with a product picker or an incoming
      answer, never needs_scope. Test in tests/chatbot (engine-level, mocked parser output).
AC-10 `pytest tests/chatbot -q` green except the #755 pre-existing reds.
AC-11 Review blocker B2 regression (1): prev order, model incoming + broaden_axis date on
      "not just August" -> `switched` does NOT fire (ba != "all"), domain_hint restored to
      order, broaden_axis_domain_restored True. Unit test.
AC-12 Review blocker B2 regression (2): prev promotion with a date window, model order +
      broaden_axis date, entity_op reuse, turn names no date -> broaden_axis reaches the
      reuse executor untouched (not nulled by a wrongly-firing switch), so the all_time
      wipe fires: date_filter_start/end None after the turn. Unit test.
AC-13 Review blocker B2 regression (3): prev inventory with entities hanlim (customer) +
      srtwc286 (product), model order + broaden_axis customer, entity_op reuse -> the axis
      reaches the final ba_final drop pass untouched, so the named customer entity is
      dropped: entities == [srtwc286] only. Unit test.
