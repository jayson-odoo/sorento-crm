# PLAN: chatbot which-one lists apply the office's explicit customer groups (CUSTOMER-GROUP-GATE)

Status: in review (opened as small fix track; the 3 Nov ruling grew the diff to ~600 lines, still no migration, no auth/RBAC change, no new ingest surface)

## Bug

`gate._cust_base` (`sorento_crm_backend/app/services/chatbot/lanes/business/gate.py`) looked the
customer group up with the `[A/C ..]`-stripped name, while the group map
(`customer_group_service.family_overrides`) and `ledger_family.customer_group_of` match only the
exact normalised FULL ledger name. So a suffixed ledger never reached its group and every ledger
fell to the name rule. On the dev copy all 8 FULLSHUN ledgers (both companies, grouped or not)
became one name-rule family. This fed every domain's which-one list.

## Owner ruling (CUSTOMER-GROUP 2 Oct 2026, restated by crew 3 Nov 2026)

Explicit, staff-set groups only:

1. Groups apply, looked up by customer id (or exact full name when no id is at hand), per
   company: 190 group names exist in both MCH and SRT on the 20 Oct prod copy and must never
   merge across companies.
2. The name-rule family is removed for grouping: every ungrouped ledger is its own entry in a
   which-one list (3,713 of 6,854 ledgers are ungrouped on the copy, so lists may get longer:
   accepted). Name matching stays for SEARCH only (what a typed word matches).

## Change

- `customer_group_service`: `family_ids` (customer id -> group name) beside `family_overrides`
  (full name -> group name; a name in two groups, in one company or two, or in a group and none,
  is left out). A group name shared by companies in scope carries its company code,
  "NAME (SRT)", so the two groups are two entries.
- `ledger_family`: `customer_groups(mapping, ids=)`; `customer_group_of`, `ledger_family_key`,
  `ledger_family_label` take the row's id. An ungrouped row keys by its own full name.
  `trading_name_key` is the search-only name rule; `without_ledger_marker` for a line that must
  not print a marker. `UNGROUPED_JOINS_NAME_MATCHED_GROUP` / `apart_from_group` removed (ruled).
- `gate._cust_base` = `ledger_family_key(full display name, uuid)`; the gate's roster title for
  a several-ledger entry is the group's name.
- `narrow._options` keys by id too and never prints a company tag twice.
- `resolve_gate` "a word that IS one trading name" uses `trading_name_key` (search).
- `engine` and `stock_ask_service` load both maps.

## Tests (red first)

`sorento_crm_backend/tests/chatbot/test_customer_group_gate.py`: loaders over two seeded
companies; per list (gate `order` DO, `order` outstanding, `sales`, and the stock roster), one
entry per group and per ungrouped ledger, covering grouped, ungrouped, the same full name grouped
and ungrouped, and one group name in two companies.

## Report (to crew, rows not on GitHub)

Name-rule ledgers after the lookup fix on the 20 Oct copy: 3,713 of 6,854 (MCH 1,148, SRT
2,565); 1,136 rows over 227 trading names share a name with a grouped ledger. Crew offers the
owner a reviewed grouping list for those, separately.

## Crew answers recorded

- An UNGROUPED ledger whose full name is IDENTICAL in both company books stays ONE entry
  ("NAME (SRT, MCH)"): the owner's 3 Nov R2 on #2105 forbids asking "Sorento or Mocha?" for the
  same account. A near-identical name (another marker, punctuation) is another customer.

## Lane decisions (for review)

- `customer_groups_auto.py` (staff-run group PROPOSALS) keeps the trading-name key: it proposes
  explicit groups for review, it does not join anything itself.

## Left as is (not which-one lists)

- `ledger_family.group_names` / `family_words` (DO / SO-status header text) still print one
  marker-stripped name per trading name. It is header copy, not a list or a figure.
