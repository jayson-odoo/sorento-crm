/**
 * `proposalCountsSentence` - the "(M via a family card)" clause
 * (PLAN-flyer-family-proposals.md AC-B.2). Rendered on both the dealer kit's
 * reading page and the review screen header, so this is the one place the
 * clause is proven rather than twice.
 */
import { describe, expect, it } from 'vitest';

import type { FlyerSpecBatch } from '../services/flyerSpecProposalService';
import { proposalCountsSentence } from './countsSentence';

function batch(overrides: Partial<FlyerSpecBatch> = {}): FlyerSpecBatch {
  return {
    id: 'b-1',
    reading_id: 'r-1',
    filename: 'flyer.pdf',
    status: 'proposed',
    error_message: null,
    product_count: 8,
    proposal_count: 20,
    new_count: 10,
    change_count: 4,
    conflict_count: 2,
    unchanged_count: 3,
    suppressed_count: 1,
    applied_count: 0,
    read_at: null,
    created_at: null,
    finished_at: null,
    applied_at: null,
    created_by_name: null,
    applied_by_name: null,
    viaCount: 0,
    ...overrides,
  };
}

describe('proposalCountsSentence, the family-card clause', () => {
  it('adds the clause when viaCount is greater than zero', () => {
    const sentence = proposalCountsSentence(batch({ product_count: 8, viaCount: 7 }));

    expect(sentence).toContain('8 products (7 via a family card)');
  });

  it('omits the clause entirely when viaCount is zero', () => {
    const sentence = proposalCountsSentence(batch({ product_count: 1, viaCount: 0 }));

    expect(sentence).toContain('1 product:');
    expect(sentence).not.toContain('via a family card');
  });

  it('singularises "product" the same way with or without the clause', () => {
    const sentence = proposalCountsSentence(batch({ product_count: 1, viaCount: 1 }));

    expect(sentence).toContain('1 product (1 via a family card)');
  });
});
