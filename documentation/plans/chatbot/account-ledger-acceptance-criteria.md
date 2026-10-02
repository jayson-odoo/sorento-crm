# UAC: account N selects the [A/C N] ledger

Plan: `PLAN-account-ledger-2oct.md`. Examples use dev data (customers from the 25 Sep prod copy).

- AC-1: The parser output carries `account` on every entity; "Soon Heng account 1" gives a
  customer entity with raw "Soon Heng" and account "I". "acc 2", "a/c 2", "A/C II", "ac2",
  "akaun 2" all give "II". No account words -> null.
- AC-2: A message with no account words behaves exactly as today (linked and staff).
- AC-3: Linked contact (links incl. HANLIM TRADING SDN BHD bare, (CERAMIC & ELLECI),
  [A/C I]..[A/C IV]): "Hanlim account 2 outstanding" answers HANLIM TRADING SDN BHD [A/C II] only.
- AC-4: Same contact (linked to SOON HENG HARDWARE CO.SDN.BHD. [A/C I] only of that name):
  "Soon Heng account 1" answers that ledger; "Soon Heng account 2" refuses and names only
  SOON HENG HARDWARE CO.SDN.BHD. [A/C I]; no unlinked ledger is ever named.
- AC-5: Linked contact, "my account 1": only its [A/C I] links are answered; none ->
  refusal naming its linked ledgers.
- AC-6: Staff, "Soon Heng account 1 outstanding": picker lists the three [A/C I] ledgers
  (HARDWARE, PLUMBING & SANITARY WORKS, TRADING); a pick answers that one ledger only.
- AC-7: Staff, "Soon Heng Trading account 2": refused, naming accounts I, III and IV.
- AC-8: A ledger number no row has ("account 7") refuses the same way as AC-4 / AC-7.
- AC-9: A row without an A/C marker (bare, (PROJECT), [CERAMIC]) is never in an account answer.
