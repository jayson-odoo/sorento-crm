# TARGET-COMMISSION-VIEW browser pass (cloud sandbox, 4 Nov 2026)

Stack: this lane's branch, backend :8000 + `next dev` :3000, an empty bootstrapped database
(`scripts.bootstrap_env`, every module installed) with one seeded dealer target shaped like
TGT-000008: account 300-A077 A CRAFT IDEA SDN BHD (A/C I), quarterly, own tiers per period
(Q1 6% from 60,000 and 8% from 72,000; Q2-Q4 5% from 60,000), seven sales orders. No prod data.
Sign-in: the NextAuth session cookie was minted from a real `/api/v1/auth/login` (the
sign-in form's CSRF round trip does not survive this sandbox's proxy). Navigation: `/`, then the
sidebar Sales > Targets, the Dealers tab, the row.

1280px
- Summary card: Commission earned to date 6,918.12; Current period so far 0.00, "01/10/2026 to
  31/12/2026, 2.1% of target, not final"; Pays to 300-A077 - A CRAFT IDEA SDN BHD (A/C I),
  "Payment is not tracked in the CRM".
- Periods: Q1 60,000.00 / 61,351.64 / 102.3% / Tier 1 / 6.00% / 3,681.10 / 300-A077 (A/C I);
  Q2 64,740.40 / 107.9% / Tier 1 / 5.00% / 3,237.02; Q3 39.1% None 0.00 -; Q4 Current 2.1% 0.00;
  Total 240,000.00 / 150,787.62 / 6,918.12.
- Accounts: per period the account's sales, then Period total with commission and pays to;
  Q4 reads "Period total (so far)" 1,235.58.
- Gear > Export commission statement downloaded commission-statement-TGT-000001-20261104.xlsx:
  Summary + TGT-000001 sheets, the same figures, tier table per period, documents SO-26-000001..3
  (08/01/2026, 14/02/2026, 21/03/2026, 18,220.50 + 25,004.00 + 18,127.14 = 61,351.64).
- Targets list, Dealers: ticking the row shows "Commission statement (1)" in the selection strip;
  it downloaded the same file.

375px
- Summary card stacks (earned, current, pays to); Periods and Accounts tables scroll inside
  their card; no page-level horizontal scroll.

Found and fixed during the pass: Achieved / Target showed "64,740.4" (now RM 2 decimals on an
amount target), the Pays to cell clipped at 1280 (now "300-A077 (A/C I)" with the full name as
its title), the Accounts current-period band stopped short (trailing cell restored).
