# PLAN: Pricing UX fixes (live min-price alerts on a new quotation, series line remove + save)

Status: in progress (M lane, cloud). Track: small-fix-shaped diff, no migration expected.
Lane: PRICING-UX-FIXES. UAC: `pricing-ux-fixes-01nov-acceptance-criteria.md`.

## Journey
A salesperson types a price on a brand-new quotation and sees at once that a line is below the
minimum price or is a non-standard item, exactly as on a saved quotation. An admin on a series
page can remove a product line, and every edit visibly saves.

## A. Quotation editor
- New route `GET /api/v1/projects/quotation-line-verdict?series_id=&product_id=&product_set_id=&unit_price=`
  (same READ permission as the per-quotation verdict). The per-quotation route keeps working and
  both share one judge function, so there is still one implementation.
- FE `useLineVerdict` calls the new route when there is no quotation id, passing the scope's
  `series_id`. The editor no longer needs a saved quotation to judge a line.
- Wording: "priced below its floor" becomes "priced below minimum price" (singular and plural).
  The "Set on <level>" line under the rate is removed; "Minimum price RM x" stays.

## B. Series page
- Owner Q1 (pending): remove an in-scope product = exclusion (crew rec a).
- Owner Q2 (pending): floor with price only = the price (crew rec a).
- Saved row: the product cell has no clear X (the product is fixed). New row with no product: an
  inline message, not just a red cell.
- Search / page change / leaving the page with unsaved rows: valid rows are saved first; rows that
  cannot save are warned about, never silently dropped.
- A successful save shows a toast.

## Tests
pytest for the new route (new quotation, below-floor, non-standard, permission); vitest for the
wording, the removed level line, the verdict hook without a quotation id, and series row rules.
