# PLAN: GATE-SUPPLIER-FAMILY (same-name supplier family counts as one)

Status: built, in review (small fix track: no migration, no auth/RBAC, no new ingest surface).

## Problem

#2144 (CUSTOMER-GROUP-GATE, merge f7755404) changed `ledger_family_key` so an ungrouped row is
keyed by its own full name. Supplier lines share the `ledger_family` grouping
(`policy_rows.SUPPLIER_KIND_ROW`, migration `sfam_0001_supplier_ledger_family`), so the two
HANLIM TRADING records (400-H018, 403-H007) stopped being one supplier and the bot asked
"Which one do you mean?". 28 tests regressed (21 in `tests/chatbot/test_supplier_ask.py`, 7
replay cases under `disallowed-entity-gate/`).

## Ruling

Owner, 7 Nov ("2120a"): same-name suppliers are ONE supplier, grouped by `ledger_family`. The
bot never asks which one. #2144's customer rule (explicit customer groups only) stays.

## Change

Supplier rows keep the pre-#2144 `ledger_family` key (the trading-name key with no customer
group in play: `ledger_family.trading_name_key`). Customer rows keep #2144's key. No new word
list or regex; the existing family rule only.

## Tests

The 28 regressed tests, red on main 46418c30, green on the lane head. Plus #2144's own tests
(`tests/chatbot/test_customer_group_gate.py`, `tests/test_ledger_family.py`, and the files it
re-pinned).
