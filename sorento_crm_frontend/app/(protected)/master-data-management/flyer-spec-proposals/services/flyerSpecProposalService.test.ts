/**
 * `via_count` / `via_product_code` mapped off the wire (PLAN-flyer-family-
 * proposals.md S1). Every other field in this service's wire shape is already
 * snake_case straight through - these two are the only ones the review screen
 * and `countsSentence` read camelCased, so this is the one seam that would
 * silently go back to reading `undefined` if the mapping were dropped.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ extractApiError: vi.fn() }));

import { apiFetch } from '@/lib/api';

import { getFlyerSpecProposals, listFlyerSpecBatches } from './flyerSpecProposalService';

const mockFetch = vi.mocked(apiFetch);

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

describe('getFlyerSpecProposals, via_count / via_product_code', () => {
  it('maps via_count onto the batch and via_product_code onto each group', async () => {
    mockFetch.mockResolvedValueOnce(
      ok({
        id: 'b-1',
        reading_id: 'r-1',
        filename: 'SRTWC8152-SH.pdf',
        status: 'proposed',
        product_count: 8,
        via_count: 7,
        groups: [
          {
            product_id: 'p-base',
            product_code: 'SRTWC8152-SH',
            product_name: 'Sorento Wall Hung WC',
            pages: [3],
            via_product_code: null,
            proposals: [],
          },
          {
            product_id: 'p-sib',
            product_code: 'SRTWC8152-SH-UF',
            product_name: 'Sorento Wall Hung WC UF',
            pages: [3],
            via_product_code: 'SRTWC8152-SH',
            proposals: [],
          },
        ],
      }),
    );

    const result = await getFlyerSpecProposals('r-1');

    expect(result.viaCount).toBe(7);
    expect(result.groups[0].viaProductCode).toBeNull();
    expect(result.groups[1].viaProductCode).toBe('SRTWC8152-SH');
  });

  it('defaults viaCount to 0 and viaProductCode to null on an old batch with neither field', async () => {
    mockFetch.mockResolvedValueOnce(
      ok({
        id: 'b-2',
        reading_id: 'r-2',
        filename: 'Old Flyer.pdf',
        status: 'proposed',
        product_count: 1,
        groups: [
          {
            product_id: 'p-1',
            product_code: 'SRT1',
            product_name: 'Sink',
            pages: [1],
            proposals: [],
          },
        ],
      }),
    );

    const result = await getFlyerSpecProposals('r-2');

    expect(result.viaCount).toBe(0);
    expect(result.groups[0].viaProductCode).toBeNull();
  });
});

describe('listFlyerSpecBatches, via_count', () => {
  it('maps via_count on every row of the list', async () => {
    mockFetch.mockResolvedValueOnce(
      ok([
        {
          id: 'b-1',
          reading_id: 'r-1',
          filename: 'SRTWC8152-SH.pdf',
          status: 'proposed',
          product_count: 8,
          via_count: 7,
        },
      ]),
    );

    const rows = await listFlyerSpecBatches();

    expect(rows[0].viaCount).toBe(7);
  });
});
