/**
 * `productFallbackFor` - the pure function `SalesOrderDetail.tsx` resolves the Product
 * cell's `SearchableSelect selectedOption` from (coder, 2420ee00f, "a picked product stays
 * picked on the sales order line").
 *
 * A sibling file, not a block inside `SalesOrderDetail.test.tsx`: the function is pure and
 * exported precisely so the rule it encodes can be read and tested on its own, without the
 * render/mock machinery the rest of that file needs - and because the defect it exists to
 * stop (picking a product resets the cell to "Select product") is INVISIBLE in jsdom, where
 * `SearchableSelect`'s own async fetch resolves only after the popover has already closed
 * (see the tester's browser-triage findings the same day). Testing the full click-driven UI
 * path here would not exercise the fix at all.
 *
 * Precedence: `draft.picked_product` when its `value` equals the draft's own `sku`; else the
 * row's own product when the draft still names it; else `undefined`.
 */
import { describe, it, expect } from 'vitest';
import { productFallbackFor } from './SalesOrderDetail';

describe('productFallbackFor', () => {
  // THE REGRESSION (13 September 2026, browser, twice: keyboard and a direct click): the
  // draft's `sku` now names a DIFFERENT product than the row loaded with. Pre-fix, the
  // original `productFallback(row, draftSku)` (git show 48b5e135d:.../SalesOrderDetail.tsx)
  // read:
  //   const sku = draftSku ?? row.sku;
  //   if (!row.sku || sku !== row.sku) return undefined;
  // Once `draftSku` ('NEW-SKU-99') differs from `row.sku` ('CW-BASIN-450'), that check is
  // true and the OLD function returns `undefined` unconditionally - there was no second
  // source to fall back to, which is exactly why the cell went blank the instant
  // `SearchableSelect`'s own fetched page (the only other place it could read a label from)
  // was discarded on close. `productFallbackFor` fixes this by keeping the picked option
  // whole on the draft and preferring it.
  it('returns the PICKED option when the draft names a different product than the row (the regression case)', () => {
    const row = { sku: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm' };
    const pickedOption = { value: 'NEW-SKU-99', label: 'NEW-SKU-99 · New Product' };
    const draft = { sku: 'NEW-SKU-99', picked_product: pickedOption };

    expect(productFallbackFor(row, draft)).toEqual(pickedOption);
  });

  it("returns the row's OWN product, as 'SKU · name', when the draft still names it (unchanged case)", () => {
    const row = { sku: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm' };
    const draft = { sku: 'CW-BASIN-450', picked_product: undefined };

    expect(productFallbackFor(row, draft)).toEqual({
      value: 'CW-BASIN-450',
      label: 'CW-BASIN-450 · Ceramic Wash Basin 450mm',
    });
  });

  // A line added via "Add line" (R4c, 48b5e135d) starts with `sku: ''` - it never had a row
  // product to fall back to at all, so the picked option is the ONLY source that can ever
  // label it.
  it('returns the picked option on a NEW line (no row sku to fall back to)', () => {
    const row = { sku: '', product_name: '' };
    const pickedOption = { value: 'NEW-SKU-99', label: 'NEW-SKU-99 · New Product' };
    const draft = { sku: 'NEW-SKU-99', picked_product: pickedOption };

    expect(productFallbackFor(row, draft)).toEqual(pickedOption);
  });

  it('returns undefined when the draft names a different product and nothing picked it (neither source can label it)', () => {
    const row = { sku: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm' };
    const draft = { sku: 'NEW-SKU-99', picked_product: undefined };

    expect(productFallbackFor(row, draft)).toBeUndefined();
  });

  it('returns undefined when draft itself is undefined and the row has no sku', () => {
    const row = { sku: '', product_name: '' };

    expect(productFallbackFor(row, undefined)).toBeUndefined();
  });
});
