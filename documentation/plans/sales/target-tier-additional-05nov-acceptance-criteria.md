# UAC: tier Additional as a column (lane TARGET-TIER-ADDITIONAL)

Plan: `PLAN-target-tier-additional-05nov.md`. Owner answers 5 Nov 11:10, adds 11:30 and 11:40.

## Engine and data

- A1. A tier carries an optional Additional: a % (`additional_rate`) or a fixed RM (`bonus_amount`),
  never both (422 "not both").
- A2. Only the reached tier's Additional pays. A CRAFT IDEA A/C I Q1 (76,793.92; 60,000 / 75,000 /
  85,000 at 5 / 6 / 7 % + 1 %) pays 4,607.64 + 767.94 = 5,375.58; Q2 (61,804.93, no Additional)
  pays 3,090.25.
- A3. The % Additional is added on every account the tier pays, each account rounded on its own.
- A4. Bonus (RM Additional) pays for the reached tier only.
- A5. `scripts/fold_tier_additionals.py` (dry run by default) lists every target with a
  "+ Additional" row or a Bonus with each period's old and new commission and bonus; `--apply`
  moves each row onto the tier of the same period and threshold; a row it cannot place stays and
  is listed with the reason.
- A6. The import reads "A/C I- 6% + Additional 1%" as tier 6% with Additional 1%, and the
  spreadsheet's Tier 3 (85000, 7%) + Tier 4 (>=85000, 7% + 1%) as one tier, 85,000 at 7% + 1%.

## Screens

- B1. Commission (view): column Additional shows "+ 1.00%" or "+ RM 250.00"; no "+ Additional from"
  rows once folded. Edit: Additional value + "%" / "RM" select per tier.
- B2. Periods: Rate reads "A/C I 6.00% + 1.00%".
- B3. Periods, Accounts and Commission (read mode) are the standard grid with the Columns chooser;
  totals rows kept.
- B4. Commission has a Period multi-select filter.
- B5. Periods Tier reached / Rate and the Accounts period cell open a lightbox with that period's
  tiers, the reached tier highlighted.
- B6. Dealer target: no "For ..." subtitle; KPI "Current period commission (RM)" with its dates
  only; no "Periods that have ended", "not final" or "Payment is not tracked in the CRM";
  Details shows "Customer" = the dealer's name.
