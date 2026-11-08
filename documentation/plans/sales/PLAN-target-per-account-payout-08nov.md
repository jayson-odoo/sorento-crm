# PLAN: target per-account payout (08 Nov 2026)

Status: Built, reviewed (reviewer READY after fixes), browser-passed in the cloud sandbox; awaiting owner hand test. Track: full (migration). Lane TARGET-PER-ACCOUNT-PAYOUT, PR #2262.

UAC: `target-per-account-payout-08nov-acceptance-criteria.md` (alongside).

## Owner rulings (8 Nov ~22:20 to 22:50, card on PR #2262)

1. Separate targets stack. A combined multi-account target (TGT-000025 shape) pays on top of an
   account's own ladder target (TGT-000026 shape). "Replaced by" is removed (card Q1 a).
2. Each account earns its own share: account sales x that account's rate at the tier the combined
   total reached. A dealer target has no single "Pays to"; each counted account is its own payee
   (card Q2 a). Agent and team targets never had a payee field and are unchanged.
3. Card Q3 ("it should be per account also"): the marginal method and the fixed RM Additional are
   per account, like the rate (rule below).
4. Card Q4 a: Accounts tab shows each account's own Commission; the period total is the sum; no
   Pays to column anywhere (list, Periods, Accounts, summary card, statement, assistant).
5. Card Q5 a: each target stands alone; nothing cross-references a stacking target.
6. Card Q6 a ("yes use same rule"): Points beside Sales (RM) on a points target, at the ratio the
   engine reads the tiers with (one per period, in force on its last day).
7. Figures and the ordered/invoiced basis are out of scope: mechanism only.

## Mechanism

- Engine `commission_service.payout_for` returns `Payout.by_account`: each account's share of
  commission + bonus. Retroactive and the % Additional already paid per account (each rounded on its
  own); the shares are those amounts.
- Marginal: tier boundaries stay on the combined total T. Each slice of T is shared by the accounts
  in proportion to their sales; each account pays its own rate for the tier (per-account rate, else
  the tier's rate; 0 if the tier names other accounts) on its part, its slices added then rounded.
  One bucket (agent, team): unchanged. Per-account rates on marginal are no longer refused.
- RM Additional: `target_tier_rates.bonus_amount` per account when set (stored beside the rate);
  otherwise the tier's `bonus_amount` is paid to each counted account (once on agent/team targets).
  `_achieved_by_account` gives every counted account a key so an account with no sales still gets a
  one-for-all RM Additional. A tier sets its Additional per account or for the tier, not both.
- Points: `target_detail.period_out` divides the period's and each account's sales by the same
  `ratio_on(ratios, p.period_end)` the engine uses; null with no ratio.
- Migration `sales_0008_no_replace_payee`: drops `targets.replaced_by_target_id` and
  `targets.payout_customer_id` with their checks (dev had 7 links: TGT-000017, 026, 050, 051, 068,
  090, 091), adds `target_tier_rates.bonus_amount` numeric(15,2) >= 0.
- Import: no replaced-by link, no window-match refusal, PAY TO read as a no-op with a row warning, a
  bonus cell naming one counted account of a multi-account target becomes that account's own RM
  Additional.
- Statement xlsx: no Pays to; an "Each account's commission" block per period.
- Assistant `agent_target_summary`: `account_payouts` ("A/C I 9,946.07; A/C II 5,839.84") replaces
  `payout_account` and `replaced_by`.

## Files

Backend: `app/services/sales/commission_service.py`, `target_service.py`,
`commission_statement_xlsx.py`, `dealer_target_import.py`, `app/services/assistant_registry/sales.py`,
`app/models/sales.py`, `app/schemas/sales.py`, `alembic/versions/sales_0008_no_replace_payee.py`.
Frontend: `app/(protected)/sales/targets/components/TargetRecord.tsx`, `SalesTargetsView.tsx`,
`types/salesTarget.types.ts`. Doc: `dealer-targets-import-layout.md`.

## Tests

`tests/test_target_per_account_payout_engine.py`, `tests/test_target_per_account_payout_api.py`,
`tests/test_migration_sales_0008_no_replace_payee.py`, the import / assistant / statement suites
updated to the new mechanism, vitest `TargetRecord.test.tsx`, `SalesTargetsView.test.tsx`.
