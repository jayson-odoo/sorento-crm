# UAC: target per-account payout (08 Nov 2026)

Plan: `PLAN-target-per-account-payout-08nov.md`. Lane TARGET-PER-ACCOUNT-PAYOUT.

- PA-1 A combined dealer target with per-account rates pays each account its sales x its own rate at
  the tier the combined total reached; the shares add up to the period's commission + bonus.
  (DELUXE shape: 663,071.20 x 1.5% / 583,984.44 x 1% / 37,013.06 x 1.5% = 9,946.07 / 5,839.84 /
  555.20, total 16,341.11.)
- PA-2 An account's own target and a combined target counting it both pay in full (they stack).
- PA-3 No "Replaced by" anywhere: API, Periods, Accounts, statement, assistant, import.
- PA-4 No "Pays to" on dealer targets anywhere: Dealers list, Periods, Accounts, summary card,
  statement, assistant; the API refuses `payout_customer_id` and `replaced_by_target_id` (422).
- PA-5 Accounts tab: each account row shows its own Commission (RM); the period total row shows the
  period's commission + bonus.
- PA-6 Marginal on a multi-account dealer target: each account pays its own rate on its part of each
  combined-total slice (crew-note example: A 12,000, B 14,000).
- PA-7 RM Additional set per account is paid to that account only. On a target counting several
  accounts it is set only per account (owner 8 Nov 23:59, a): no tier-level RM option in the
  editor, 422 from the API, the import refuses a bonus naming no single counted account and lists
  legacy ones, and a legacy tier-level amount there is never paid once per account. Agent, team and
  single-account targets keep the tier-level RM Additional, paid once.
- PA-8 Points target: Points column beside Sales (RM) per account and on the period total, at the
  ratio in force on the period's last day; "No ratio" without one.
- PA-9 Import: no link, no window refusal, PAY TO warns and is not used, a bonus naming one counted
  account of several is that account's own RM Additional.
- PA-10 Migration drops both columns and adds `target_tier_rates.bonus_amount`; one alembic head.
