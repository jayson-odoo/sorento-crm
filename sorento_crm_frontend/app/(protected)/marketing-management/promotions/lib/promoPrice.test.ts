import { describe, it, expect } from 'vitest';
import { displayPromoPrice } from './promoPrice';

describe('displayPromoPrice', () => {
  it('shows the stored promo price', () => {
    expect(displayPromoPrice({ promotion_price: 80, product: { list_price: 100 } })).toBe(80);
  });

  it('falls back to list price for an ordinary line with no stored price', () => {
    expect(displayPromoPrice({ promotion_price: null, product: { list_price: 100 } })).toBe(100);
  });

  it('shows none for a brand whose promotions carry no selling price', () => {
    expect(
      displayPromoPrice({ promotion_price: null, no_selling_price: true, product: { list_price: 100 } }),
    ).toBeNull();
  });
});
