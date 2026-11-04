import { describe, expect, it } from 'vitest';

import { promotionOptionLabel } from './line-pricing-types';

describe('promotionOptionLabel', () => {
  it('shows the figure when the option has one', () => {
    expect(promotionOptionLabel({ description: 'Flyer', sell_price: 1800 })).toBe('Flyer - RM 1,800');
  });

  it('shows only the name when the figure is null (a combo with no stored price)', () => {
    expect(promotionOptionLabel({ description: 'Flyer', sell_price: null })).toBe('Flyer');
  });

  it('keeps the expired suffix', () => {
    expect(promotionOptionLabel({ description: 'Flyer', expired_on: '2026-09-30', sell_price: null })).toBe(
      'Flyer (expired 30 Sep 2026)',
    );
  });
});
