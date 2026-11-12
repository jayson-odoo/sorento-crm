# Hand test and release notes: target per-account payout (lane TARGET-PER-ACCOUNT-PAYOUT, PR #2262)

Plan: `PLAN-target-per-account-payout-08nov.md`. UAC: `target-per-account-payout-08nov-acceptance-criteria.md`.
Owner hand test: PASS (last owner round 9 Nov 00:58 MYT; the Accounts grid Code column fix was
verified by crew's browser pass instead).

## Hand-test script

### URL
crew test copy

### Setup
Apply the additive part of `sales_0008_no_replace_payee` to the test copy's DB (the two dropped
columns are nullable and no longer mapped, so the test copy runs without dropping them):

```sql
ALTER TABLE sales.target_tier_rates ADD COLUMN IF NOT EXISTS bonus_amount numeric(15,2);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_sales_target_tier_rates_bonus_amount') THEN
    ALTER TABLE sales.target_tier_rates
      ADD CONSTRAINT ck_sales_target_tier_rates_bonus_amount CHECK (bonus_amount IS NULL OR bonus_amount >= 0);
  END IF;
END $$;
```

Log in as an admin.

### Steps
1. Sidebar: Sales > Targets, open the Dealers tab.
2. Look at the column headers of the Dealers list and at TGT-000025's Commission.
3. Open TGT-000025 (DELUXE HOME CENTRE 2026 yearly).
4. Look at the commission summary card above the tabs.
5. Open the Accounts tab.
6. Open the Periods tab.
7. Click Edit, open the Commission tab, look at the tier table, then click Cancel.
8. Open TGT-000026 (A/C I's own ladder target) from the Dealers list.
9. Open its Periods tab.
10. Open "MY KITCHEN & BATHROOM ACC TRADING 2026 points quarterly" from the Dealers list.
11. Open its Accounts tab.
12. Tick TGT-000025 in the Dealers list, export the commission statement, open it from My Downloads.

### Expected
- Step 2: no "Pays to" column; the list's Commission equals the detail page's current period
  commission (RM Additional included).
- Step 4: Commission earned to date and Current period commission only; no "Pays to". Earned to
  date counts ended periods only, so a yearly 2026 target reads 0 until the year ends.
- Step 5: each account row has its own Commission (RM); they add up to the Period total row. Each
  account = its sales x its own rate at the tier the combined total reached (prod check at the 1M
  tier: 663,071.20 x 1.5% = 9,946.07; 583,984.44 x 1% = 5,839.84; 37,013.06 x 1.5% = 555.20).
  Code shows in full (e.g. 300-D093) and Commission (RM) is not under the right-edge fade at 1280.
- Step 6: no "Pays to" column, no "Replaced by" note.
- Step 7: one "A/C n additional (RM)" input per account beside the rate columns; the tier's own
  Additional offers % only (a combined target sets its RM Additional per account).
- Step 9: TGT-000026 pays its own ladder tier even where TGT-000025 reached a tier.
- Step 11: a Points column beside Sales (RM) on every account row and the period total; Points =
  Sales (RM) / the period's RM per point (the ratio in force on the period's last day).
- Step 12: no "Pays to"; each period has an "Each account's commission" block; the Rate cell
  names the account of a per-account RM Additional ("A/C n + RM x").

## Before deploying `sales_0008_no_replace_payee` to production: snapshot (READ-ONLY)

The upgrade drops `sales.targets.payout_customer_id` and `sales.targets.replaced_by_target_id`
(and their checks `ck_sales_targets_payout_dealer`, `ck_sales_targets_replaced_by_dealer`, which
hold no data). Nothing else is dropped; `target_tier_rates.bonus_amount` is added. Run this on
prod before the deploy and keep the CSV with the release record:

```sql
-- READ-ONLY: a SELECT, nothing is written. Every target that has a payee or a replaced-by link.
SELECT t.id, t.company_id, t.target_no, t.name, t.subject_kind,
       t.payout_customer_id, pc.customer_code AS payout_customer_code, pc.customer_name AS payout_customer_name,
       t.replaced_by_target_id, rt.target_no AS replaced_by_target_no
FROM sales.targets t
LEFT JOIN customers pc ON pc.id = t.payout_customer_id
LEFT JOIN sales.targets rt ON rt.id = t.replaced_by_target_id
WHERE t.payout_customer_id IS NOT NULL OR t.replaced_by_target_id IS NOT NULL
ORDER BY t.target_no;
```

As a file from psql (one line, client-side `\copy`, still read-only on the server):

```
\copy (SELECT t.id, t.company_id, t.target_no, t.name, t.subject_kind, t.payout_customer_id, pc.customer_code AS payout_customer_code, pc.customer_name AS payout_customer_name, t.replaced_by_target_id, rt.target_no AS replaced_by_target_no FROM sales.targets t LEFT JOIN customers pc ON pc.id = t.payout_customer_id LEFT JOIN sales.targets rt ON rt.id = t.replaced_by_target_id WHERE t.payout_customer_id IS NOT NULL OR t.replaced_by_target_id IS NOT NULL ORDER BY t.target_no) TO 'sales_targets_payee_snapshot.csv' WITH CSV HEADER
```

Checked against a scratch schema built by the sales migrations up to `sales_0007_tier_additional`:
it returns exactly the targets carrying a payee or a link, with the payee's code and name and the
replacing target's number.

## Downgrade cannot restore the data

`sales_0008`'s downgrade re-creates both columns and their checks EMPTY (all NULL). It cannot
restore any payee or replaced-by link from nothing: the values exist only in the snapshot above.
Putting them back would need the snapshot and a hand-written UPDATE, and the code after this lane
reads neither column, so a downgrade alone changes no payout.
