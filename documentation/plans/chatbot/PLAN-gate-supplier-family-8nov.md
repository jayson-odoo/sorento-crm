# PLAN: Re-land #2144 + same-name supplier fix (GATE-SUPPLIER-FAMILY)

Status: built, in review (standard track: re-land of a ~900-line change; no migration, no
auth/RBAC change, no new ingest surface). Ships in the release after 9 Nov, once crew has run the
replay corpus and supplier_ask on the head.

## Rulings

- Owner 7 Nov ("2120a"): same-name suppliers are ONE supplier, never asked.
- Owner 9 Nov ~01:15: "it should just answer by the group, the user doesn't care about which
  account la, we should just return all accounts". No "which account?" for same-name or
  same-group accounts. The answer covers every account the asker may see. Where an explicit
  Customer Group exists, answer by the group. The 7 disallowed-entity-gate replay cases pass as
  captured, with no new divergences.
- Owner Q1, 9 Nov ~01:20: "we should treat it as part of group also, the key is user are less
  attentive to details when asking, so we should be more lenient". An ungrouped account whose
  base name matches a group's name joins that group's answer. Answer-time only: no data link.
- Crew Q2 (a): a group name in both Sorento and Mocha is answered as one, with the company code
  on each line. The bot never asks "Sorento or Mocha?".

## History

#2144 (f7755404) shipped "every ungrouped ledger is its own entry". That broke the supplier rule
(21 supplier_ask tests) and 7 replays. #2270 (7fd65fe4) reverted it for 9 Nov. This branch:
7a072db7 merges main keeping #2144 (that is, a revert of #2270), the supplier fix
(af448632, 815eb6a7), then a707effc applies the 9 Nov rulings.

## Kept from #2144

- The group lookup by customer id, or by exact full name when there is no id
  (`customer_group_service.family_maps` / `family_ids` / `family_overrides`;
  `ledger_family.customer_groups(mapping, ids=)`, `customer_group_of(text, uuid)`). A suffixed
  `[A/C I]` ledger now reaches its group.
- Both maps are loaded once per turn (`engine`, `stock_ask_service`).
- `trading_name_key` / `without_ledger_marker` helpers. Search uses `trading_name_key`.
- `customer_groups_auto.py` only PROPOSES groups.

## Changed on top (a707effc)

- `ledger_family_key`: a grouped row keys by `group_key(group)` = `trading_name_key(group)`.
  Every other row keys by `trading_name_key(text)`, the pre-#2144 key. So same-name ledgers are
  one entry, and an ungrouped ledger of a group's trading name is that group's entry (Q1).
- `ledger_family_label`: the row's group, else the group of its trading name (Q1), else the name
  without its marker.
- `customer_header_words`: an ungrouped ledger of a group's trading name prints as that group (Q1).
- `customer_group_service._group_labels`: the group's own name, no company tag (Q2).
- `resolve_gate._no_such_account`: one entry is one subject.
- Supplier rows: `supplier_family_key` / `supplier_family_label` and the `narrow` kind branch,
  so suppliers never follow the customer rule.

## Tests

- `test_supplier_ask.py`: the 21 regressed cases plus 2 narrow cases.
- #2144's re-pinned files are restored from b42cb9cc. The 2 Oct "stray ledger stays apart" cases
  are re-pinned to Q1 (`test_chat_customer_pick_resume` o5-o8, `test_customer_group_family`
  ac13, `test_customer_header_words`).
- `test_customer_group_gate.py`: re-pinned to the ruling, with one case added: an entry never
  covers a ledger the resolver did not return (access scope).
- Crew runs the 7 replays against the n8n corpus on the head.
