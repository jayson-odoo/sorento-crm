/**
 * The warranty headline a consumer reads.
 *
 * The engine answers per PART - a water closet has a ceramic body, a seat cover and a
 * flush mechanism, each with its own term - and a homeowner reading five rows learns less
 * than one reading a sentence. This is the sentence, and the rules below are about not
 * making it worse than the truth.
 *
 * The asymmetry is deliberate: **any part covered means the visit is worth making**, so a
 * mixed result reads as covered. Rounding the other way tells someone with a live warranty
 * that they have none, which is the one wrong answer that costs them money.
 */
import { describe, expect, it } from 'vitest';

import { summariseWarranty, type LodgeWarrantyVerdict } from './portal-client';

function verdict(value: string, expires: string | null = null): LodgeWarrantyVerdict {
  return {
    complaint_product_line_id: 'line-1',
    claimed_text: 'SRTWC8152 WATER CLOSET',
    part_name: 'Ceramic body',
    verdict: value,
    expires_on: expires,
  };
}

describe('summariseWarranty', () => {
  it('says so plainly when nothing could be computed', () => {
    // The common case, and not an error: no purchase date means no verdict. 24% of
    // receipts print nothing usable, so this sentence is normal traffic.
    const result = summariseWarranty([]);
    expect(result.state).toBe('needs_review');
    expect(result.summary).toMatch(/our team will check/i);
  });

  it('reports covered with the expiry the consumer can act on', () => {
    const result = summariseWarranty([verdict('covered', '2030-10-16')]);
    expect(result.state).toBe('covered');
    expect(result.summary).toContain('2030-10-16');
  });

  it('reports covered without a date rather than inventing one', () => {
    // A lifetime term has no expiry. Printing a date here would be a number we made up.
    const result = summariseWarranty([verdict('covered', null)]);
    expect(result.state).toBe('covered');
    expect(result.summary).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  it('reads as covered when any part is, even if others expired', () => {
    // The asymmetry, as one test. One live part means the visit is worth making.
    const result = summariseWarranty([verdict('expired'), verdict('covered', '2027-01-01')]);
    expect(result.state).toBe('covered');
  });

  it('only says expired when every part is', () => {
    const result = summariseWarranty([verdict('expired'), verdict('expired')]);
    expect(result.state).toBe('expired');
    // "May be chargeable", never "is": the charge is CS's decision, and telling a consumer
    // they will be billed before anyone has decided is a promise we cannot keep.
    expect(result.summary).toMatch(/may be chargeable/i);
  });

  it('falls back to needs_review for anything else', () => {
    // `unknown`, `defect_not_covered`, `no_term` - the engine has five values and this
    // sentence must not guess which way an unfamiliar one leans.
    for (const value of ['unknown', 'defect_not_covered', 'no_term']) {
      expect(summariseWarranty([verdict(value)]).state).toBe('needs_review');
    }
  });
});
