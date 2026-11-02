/**
 * CABANA-NO-SELLING-PRICE: a line of a brand whose promotions carry no selling price
 * loads with a blank price. Saving its dealer discount or list price must not send a
 * price (the backend refuses one), so a blank price omits the key.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { updatePromotionProductPrice } from './promotionService';

function sentBody(): Record<string, unknown> {
  const [, init] = apiFetch.mock.calls[0];
  return JSON.parse((init as RequestInit).body as string);
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
});

describe('updatePromotionProductPrice', () => {
  it('omits promotion_price when no price is given', async () => {
    await updatePromotionProductPrice('p1', 'l1', { dealerDiscountPercent: 0.3, listPrice: 100 });
    const body = sentBody();
    expect('promotion_price' in body).toBe(false);
    expect(body.dealer_discount_percent).toBe(0.3);
    expect(body.list_price).toBe(100);
  });

  it('sends a typed price as before', async () => {
    await updatePromotionProductPrice('p1', 'l1', {
      promotionPrice: 80,
      dealerDiscountPercent: null,
      listPrice: 100,
    });
    expect(sentBody().promotion_price).toBe(80);
  });
});
