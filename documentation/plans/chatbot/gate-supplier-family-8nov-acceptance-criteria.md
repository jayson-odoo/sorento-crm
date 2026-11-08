# UAC: GATE-SUPPLIER-FAMILY

1. "PO for hanlim" answers for the HANLIM TRADING supplier family (both records), never
   "Which one do you mean?".
2. All 21 regressed `tests/chatbot/test_supplier_ask.py` cases and the 7 replay cases
   (s57-ok, s57-t0, s57-t1, exec-14206818, exec-14212345, exec-14213895, exec-14337593) pass
   with their expected outputs unchanged.
3. #2144's customer-group gate tests stay green: ungrouped customer ledgers are still their own
   lines.
