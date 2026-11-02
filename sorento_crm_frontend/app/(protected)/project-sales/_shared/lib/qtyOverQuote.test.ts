import { describe, expect, it } from 'vitest';
import { isQtyOver, qtyOverAwareError, QTY_OVER_QUOTED } from './qtyOverQuote';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const products = [
  { product_code: 'SKU-1', description: 'Tile', ordered: '12', quoted: '10' },
];

describe('qtyOverAwareError', () => {
  it('carries the code and products of a 409 po_qty_over_quoted', async () => {
    const error = await qtyOverAwareError(
      json(409, { message: 'Over quoted', code: 'po_qty_over_quoted', details: { products } }),
      'fallback',
    );
    expect(error.code).toBe('po_qty_over_quoted');
    expect(error.products).toEqual(products);
    expect(error.message).toBe('Over quoted');
    expect(isQtyOver(error)).toBe(true);
  });

  it('gives empty products for any other refusal', async () => {
    const error = await qtyOverAwareError(
      json(422, { message: 'Bad input', code: 'validation_error', details: { products } }),
      'fallback',
    );
    expect(error.code).toBe('validation_error');
    expect(error.products).toEqual([]);
    expect(isQtyOver(error)).toBe(false);
  });

  it('gives empty products when the 409 names none', async () => {
    const error = await qtyOverAwareError(
      json(409, { message: 'Over', code: QTY_OVER_QUOTED }),
      'fallback',
    );
    expect(error.products).toEqual([]);
    expect(isQtyOver(error)).toBe(true);
  });
});

describe('isQtyOver', () => {
  it('is true only for the over-quoted code', () => {
    expect(isQtyOver({ code: 'po_qty_over_quoted' })).toBe(true);
    expect(isQtyOver({ code: 'other' })).toBe(false);
    expect(isQtyOver(new Error('x'))).toBe(false);
    expect(isQtyOver(null)).toBe(false);
    expect(isQtyOver(undefined)).toBe(false);
  });
});
