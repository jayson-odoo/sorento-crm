# UAC: stock ask with no placed subject (hotfix, 22 Sep 2026)

Plan: `PLAN-chatbot-stock-no-subject-hotfix-22sep.md`. Track: small fix.

- AC-1790 An inventory turn whose fetch carries no entity with a uuid (none named, or
  the carry placed only as a kind inventory does not take) never calls
  `crm_inventory_stock_balance_list`.
- AC-1791 That turn replies with production's scope-needed wording ("That would search
  every stock we have - I need at least one filter to narrow it down. ..."), never a
  listing, never "Stock details found".
- AC-1792 The live chain (turn 59 did-you-mean roster still open, turn 60 "Stock")
  satisfies AC-1790 and AC-1791.
- AC-1793 A bare "stock?" on a fresh contact satisfies AC-1790 and AC-1791.
- AC-1794 `intent_hint: low_stock_report` with no entities still runs its tool
  (`INTENTS_ALLOWING_EMPTY` unchanged).
- AC-1795 An inventory ask with at least one placed entity (product, warehouse,
  category or brand uuid) still calls the stock tool with that filter (P9 guard stays
  green).
- AC-1796 `tests/chatbot/test_turn_replay.py` corpus stays green (no DIVERGENCES entry
  added).
