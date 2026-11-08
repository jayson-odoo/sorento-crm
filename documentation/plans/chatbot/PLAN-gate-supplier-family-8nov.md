# PLAN: Re-land #2144 + same-name supplier fix (GATE-SUPPLIER-FAMILY)

Status: planned, waiting on #2270 (revert of #2144) to merge and on the owner's Q1 answer (crew: plan for (c)).
Standard track (re-land of a ~900-line change). No migration, no auth/RBAC change.

## Rulings

- Owner 7 Nov ("2120a"): same-name suppliers are ONE supplier, never asked.
- Owner 9 Nov 01:15, verbatim: "actually it shouldn't it should just answer by the group, the user
  doesn't care about which account la, we should just return all accounts". So: no "which account?"
  for same-name or same-group accounts. Answer for all the accounts the asker may see. Where an
  explicit Customer Group exists, answer by the group. The 7 disallowed-entity-gate replay cases
  pass as captured, with NO new divergences.

## Kept from #2144

1. Group lookup by customer id, or by exact full name when there is no id
   (`customer_group_service.family_ids` / `family_overrides` / `family_maps`;
   `ledger_family.customer_groups(mapping, ids=)`, `customer_group_of(text, uuid)`). This is
   #2144's real bug fix: a suffixed ledger (`[A/C I]`) now reaches its group.
2. `group_key` = exact normalised group name + " (GROUP)" (review B1).
3. `trading_name_key` and `without_ledger_marker` as public helpers. Search keeps using
   `trading_name_key` (`resolve_gate`).
4. `engine` / `stock_ask_service` load both maps once per turn.
5. `customer_groups_auto.py` only PROPOSES groups. No name auto-linking as data.

## Changed vs #2144 (the ruling)

- `ledger_family_key(text, uuid)`: an ungrouped row keys by `trading_name_key(text)` (the
  pre-#2144 rule), not by its full name. All same-name accounts are one entry, so the gate's picker
  arm (`gate.py` `len(bases) > 1 and len(printed_lines) > 1`) does not fire for them.
- `ledger_family_label`: an ungrouped row is called `without_ledger_marker(text)` (pre-#2144).
- Two keys, one job each:
  - `ledger_family_key` / `ledger_family_label` (LINE key): which accounts one answer line or
    roster line covers and what it is called. Group -> the group (per company, "NAME (SRT)" when
    the name is in both books). Ungrouped -> trading name.
  - new `ledger_choice_key(text, uuid)` (ASK key): whether two lines are one CHOICE for the
    "which one?" question. `trading_name_key` of the group's name when grouped, else of the
    row's own name. Used only where the code counts choices: `gate.py` `printed_lines`
    (the picker arm's condition) and `narrow._choices`. Never joins data, never relabels a line.
- Q2 (crew answer (a)): a group name in both Sorento and Mocha is two LINES ("NAME (SRT)",
  "NAME (MCH)") but one CHOICE, so the bot answers both, company code on each line, never asks.
- Q1 (owner pending, crew's (c)): an ungrouped account whose trading name equals a group's name
  is its own LINE (labelled by its own name, no data link) but the same CHOICE as the group, so
  one reply carries the group's lines plus the account's lines, no question. Switch:
  `ledger_family.NAME_MATCHED_GROUP_ANSWERED_TOGETHER = True`; False makes `ledger_choice_key`
  answer with the line key for that case only, which asks (the 2 Oct behaviour). One line.
- `pickers._customer_base`: back to the family key. The "has DO" stamp follows the entry, and
  the entry is now the whole same-name family.
- Supplier fix stays (`supplier_family_key` / `supplier_family_label`, `narrow` kind branch):
  it decouples suppliers from the customer rule.

## Tests

- Red on main-after-#2270-revert-then-#2144 (i.e. #2144 as merged), green on the re-land:
  the 7 `test_full_corpus_replay[disallowed-entity-gate/...]` cases (crew runs, corpus local),
  21 + 2 `test_supplier_ask.py` cases.
- #2144's re-pinned tests go back to their pre-#2144 expectations where they encoded "ungrouped
  same-name ledgers are separate".
- `test_customer_group_gate.py`: keep the loader / group-key / search cases; flip the
  "one entry per ungrouped ledger" cases to "one entry per group, else per trading name".
- New: a dealer contact linked to 2 of HANLIM's 6 ledgers gets an answer over those 2 only.
- New (Q2): a group name in SRT and MCH -> no ask, two lines each carrying its company code,
  the answer covers both groups' accounts.
- New (Q1 (c)): JUBIN BMS group + ungrouped JUBIN BMS (NS) -> no ask, one reply, the group line
  and the (NS) line each by its own name; with the switch False -> asks (2 Oct behaviour).
- New: two DIFFERENT trading names in one group never merge suppliers or customers beyond the
  group (existing `test_a_customer_group_never_merges_two_suppliers_of_different_names`).
