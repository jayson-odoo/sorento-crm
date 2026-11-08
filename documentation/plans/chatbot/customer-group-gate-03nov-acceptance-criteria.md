# UAC: CUSTOMER-GROUP-GATE (03 Nov 2026)

Plan: `PLAN-customer-group-gate-03nov.md`. Each row is pinned by `sorento_crm_backend/tests/chatbot/test_customer_group_gate.py` unless named otherwise.

| # | Given | When | Then |
|---|-------|------|------|
| 1 | Ledgers with "[A/C ..]" markers sit in one customer group | the chatbot shows a which-one list (DO, outstanding, sales, stock) | they are ONE line named after the group, and picking it covers every ledger of the group |
| 2 | A ledger of the same trading name sits in no group | the list is shown | it is its own line, under its full name |
| 3 | Two rows have the same full name, one grouped and one not | the list is shown | they are two lines |
| 4 | A group name exists in both SRT and MCH | the list is shown | two lines, "NAME (SRT)" and "NAME (MCH)", each covering only its company's ledgers |
| 5 | Two groups' names differ only by punctuation or "SDN BHD" | the list is shown | they are separate lines |
| 6 | An ungrouped ledger has the identical full name in SRT and MCH | the list is shown | one line "NAME (SRT, MCH)" covering both (no "Sorento or Mocha?") |
| 7 | An ungrouped ledger has a near-identical name in the other company | the list is shown | separate lines |
| 8 | A user types a trading name ("soon heng trading account 2") | the account narrowing runs | the word still matches every ledger of that trading name (search), and a group's exact name speaks for that group (`test_account_ledger_*`, `test_customer_group_family.py`) |
