# UAC: GATE-SUPPLIER-FAMILY (re-land of #2144)

1. "PO for hanlim" answers for the HANLIM TRADING supplier family (both records), never
   "Which one do you mean?".
2. All 21 regressed `tests/chatbot/test_supplier_ask.py` cases pass with their expected outputs
   unchanged.
3. The 7 replay cases (s57-ok, s57-t0, s57-t1, exec-14206818, exec-14212345, exec-14213895,
   exec-14337593) pass as captured, with no new divergence.
4. Same-name customer ledgers, grouped or not, are one customer: no "which account?" question, and
   the answer covers every one of them that the asker may see. An explicit group answers by the
   group's name.
5. An ungrouped ledger whose base name is a group's name is answered with that group (no data
   written).
6. A group name in both Sorento and Mocha is one customer: never "Sorento or Mocha?", with the
   company codes on the line.
7. Two different trading names are still two customers, and the bot asks between them.
8. An answer never covers a ledger the asker cannot see.
