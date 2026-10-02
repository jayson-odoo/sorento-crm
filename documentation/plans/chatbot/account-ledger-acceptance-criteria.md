# UAC: account N selects the ledger whose Account level is N

Plan: `PLAN-account-ledger-2oct.md`. Examples use dev data (25 Sep prod copy, levels as seeded).

- AC-1: The customer form and detail page show "Account level" (Account 1..9, clearable) in
  Basic Information; saving stores it, clearing stores none; the change is in the customer's history.
- AC-2: Only a user with `order_management.customers.edit` can change Account level (403 otherwise).
- AC-3: After the migration, every customer whose name carries `[A/C n]` / `(A/C n)` has that
  level (2,284 rows on the copy); every other customer has none. Names are never read afterwards.
- AC-4: The parser output carries `account` on every entity: "Soon Heng account 1" gives
  raw "Soon Heng", account 1; "acc 2", "a/c 2", "A/C II", "ac2", "akaun 2" give 2; none -> null.
- AC-5: A message with no account words behaves exactly as today (linked and staff).
- AC-6: Linked contact (links incl. six HANLIM TRADING SDN BHD rows): "Hanlim account 2
  outstanding" answers HANLIM TRADING SDN BHD [A/C II] only.
- AC-7: Same contact: "Soon Heng account 1" answers SOON HENG HARDWARE CO.SDN.BHD. [A/C I];
  "Soon Heng account 2" refuses naming only that linked ledger; no unlinked ledger is named.
- AC-8: Staff, "Soon Heng account 1 outstanding": the which-customer list shows the three
  level-1 ledgers (HARDWARE, PLUMBING & SANITARY WORKS, TRADING); a pick answers that one only.
- AC-9: Staff, "Soon Heng Trading account 2": refused, naming Account 1, Account 3 and Account 4.
- AC-10: "account 2 outstanding" with no customer named this message: "Which customer is
  Account 2 for?", nothing fetched, no customer carried from earlier turns.
- AC-11: Changing a ledger's Account level on the form changes what "account N" answers on
  the next chatbot turn.
