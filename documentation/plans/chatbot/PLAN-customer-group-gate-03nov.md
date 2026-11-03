# PLAN: chatbot gate applies the office's explicit customer groups (CUSTOMER-GROUP-GATE)

Status: in progress (small fix track: under 300 lines, no migration, no auth/RBAC change)

## Bug

`gate._cust_base` (`sorento_crm_backend/app/services/chatbot/lanes/business/gate.py`) looks the
customer group up with `customer_group_of(_cust_name(match))`. `_cust_name` has already stripped
the trailing `[A/C ..]` / `- [A/C ..]` account suffix, while the group map
(`customer_group_service.family_overrides`) and `ledger_family.customer_group_of` match only the
exact normalised FULL ledger name (owner ruling (b), 2 Oct 2026). So a ledger with a suffix is
never found in its group, and every such ledger falls to the name rule. On the dev copy all 8
FULLSHUN ledgers (both companies, grouped or not) became one name-rule family.

This feeds every domain's which-one list (stock / outstanding / sales / DO): the gate's
`bases` / `picker_families` are keyed by `_cust_base`.

## Fix

Look the group up by the row's FULL display name (`display.customer_name` /
`display.debtor_name`, unstripped), falling back to the stripped name / canonical code only as
before. Grouped ledgers then key to their group; ungrouped ledgers keep the name rule (with the
existing `apart_from_group` separation).

## Tests (red first)

`sorento_crm_backend/tests/chatbot/test_customer_group_gate.py`: per domain (`inventory`,
`outstanding`-class domain, `sales`, `order`), a grouped `[A/C ..]` ledger pair plus an
ungrouped customer of the same trading name: the gate's family map puts the grouped ledgers in
the group's family and the ungrouped one apart.

## Report (no change)

How many ledgers still fall to the name rule after the fix, with real examples from the dev DB,
goes to crew as a PR comment for the owner's no-auto-name-matching ruling.
