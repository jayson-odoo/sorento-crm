# UAC: Target commission view (TARGET-COMMISSION-VIEW)

- CV-1 The target page shows Commission earned to date (ended periods, commission + bonus), the
  current period so far with its % and "not final", and (dealer) Pays to with "Payment is not
  tracked in the CRM". Hidden on a target with no commission. TGT-000008: 6,918.12.
- CV-2 Periods shows per period Tier reached, Rate (per-account rates labelled "A/C I 2.00%"),
  Commission (RM, 2 decimals), Pays to (dealer, only on a period that pays), and a Total row.
- CV-3 Accounts (dealer, read mode) shows every started period: each counted account's sales,
  then Period total (so far on the current one) with the commission and Pays to. The old
  "Sales, <period> (provisional, incl. tax)" header is gone; the label reads "sales orders, incl. tax".
- CV-4 Gear menu: Export commission statement downloads an xlsx for the target.
- CV-5 Targets list: ticking rows offers Commission statement (N); one file for all; at most 50.
- CV-6 The statement's Summary sheet has one row per target; each target sheet holds the period
  summary (same numbers as the screen), the tier table used per period, and the documents
  (document no., date dd/mm/yyyy, account, amount 2 decimals) adding up to Achieved to the cent.
- CV-7 Statement totals == screen totals == period rows (one computation), Ordered and Delivered
  (a DO-dated split puts each part in its own period).
- CV-8 The export needs sales.targets.view; none or more than 50 ids is a 422; an unknown id 404.
