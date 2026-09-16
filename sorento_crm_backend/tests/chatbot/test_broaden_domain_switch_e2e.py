"""RETIRED (AC-1032, chatbot-focus lane 1).

`TestBroadenBesideANewDomainReachesIncomingNotNeedsScope::
test_any_incoming_after_check_stock_ends_in_incoming_never_needs_scope` drove the REAL
engine with a hand-built v1/v2-shaped parser emission (`domain_hint`, `broaden_axis`,
`scope_intent`) to prove the AXIS BROADEN RESTORE / `domain_switch_over_broaden` logic in
`output_exchange.py` reached "incoming" rather than `needs_scope`, and carried the prior
product (SRTWC286) across the switch. That block is deleted (`output_exchange.py:1550`,
`:3257`) - parser v3 emits no `domain_hint` / `broaden_axis` / `scope_intent` at all, so
feeding this test's v1/v2-shaped fixtures through the real engine no longer exercises what
production traffic will look like once v3 promotes, and there is no `asks[]`-shaped
production capture yet to replace it with (D10's shadow window is what produces one).

The pure-function outcome this test stood in for - a domain switch keeps the prior alive
product when the switch domain and the product are compatible - is already covered at the
rule level:

* `tests/chatbot/test_focus_rules.py::TestDomainsFromAsks::
  test_the_domain_moves_and_the_products_stay`
* `tests/chatbot/test_focus_domains.py::TestDomainsFromAsks::
  test_domain_word_without_product_replaces_domains`

A real-engine, `asks[]`-shaped multi-turn replacement (this same "check stock" then "any
incoming" story, through `run_turn` twice) belongs in `tests/chatbot/test_worlds.py` once a
v3 world exists for it - out of this lane's Job 2 scope, flagged here rather than
silently dropped.
"""
