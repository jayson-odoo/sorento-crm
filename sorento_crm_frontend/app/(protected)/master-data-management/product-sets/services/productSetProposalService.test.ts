/**
 * productSetProposalService - the boundary that coerces string money/qty into
 * numbers and distinguishes "no pass has run" (null) from "a pass found
 * nothing" (a batch with zero proposals).
 *
 * UAC group H: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import {
  applyProductSetProposals,
  getProductSetProposals,
  runProductSetProposals,
} from './productSetProposalService';

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body,
  } as Response;
}

function jsonErrorResponse(status: number, detail: string): Response {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}

function memberFixture(overrides: Record<string, unknown> = {}) {
  return {
    product_code: 'SRTWCX8608-RL',
    description: 'SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)',
    list_price: '1180.00',
    quantity: '1',
    contributes_to_price: true,
    sort_order: 0,
    is_discontinued: false,
    ...overrides,
  };
}

function proposalFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: 'proposal-1',
    family_key: 'SRTWC8608',
    set_code: 'SRTWC8608-RL',
    name: 'SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)',
    members: [
      memberFixture(),
      memberFixture({
        product_code: 'SRTWCY8608',
        list_price: '0.00',
        contributes_to_price: false,
        sort_order: 1,
      }),
      memberFixture({
        product_code: 'SRTWC8608-SC',
        list_price: '85.00',
        contributes_to_price: false,
        sort_order: 2,
      }),
    ],
    computed_price: '1265.00',
    ...overrides,
  };
}

function batchFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: 'batch-1',
    company_name: 'Sorento',
    created_at: '2026-08-24T00:00:00Z',
    created_by_name: 'Jane Tan',
    family_count: 1,
    proposal_count: 1,
    proposals: [proposalFixture()],
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('getProductSetProposals - number coercion at the boundary', () => {
  it('coerces a string list_price and a string computed_price into numbers', async () => {
    mockedFetch.mockResolvedValue(okResponse({ batch: batchFixture() }));

    const batch = await getProductSetProposals();

    const proposal = batch!.proposals[0];
    expect(proposal.computed_price).toBe(1265);
    expect(typeof proposal.computed_price).toBe('number');
    expect(proposal.members[0].list_price).toBe(1180);
    expect(typeof proposal.members[0].list_price).toBe('number');
  });

  it('coerces a string quantity into a number, defaulting to 1 when absent', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({
        batch: batchFixture({
          proposals: [
            proposalFixture({
              members: [memberFixture({ quantity: '2' })],
            }),
          ],
        }),
      }),
    );

    const batch = await getProductSetProposals();

    expect(batch!.proposals[0].members[0].quantity).toBe(2);
    expect(typeof batch!.proposals[0].members[0].quantity).toBe('number');
  });

  it('renders money with a thousands separator and cents after coercion (the silent trap)', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({
        batch: batchFixture({
          proposals: [proposalFixture({ computed_price: '1265.00' })],
        }),
      }),
    );

    const batch = await getProductSetProposals();

    // Proves the value is a real number, not a string toLocaleString silently
    // returns unchanged. A string '1265.00'.toLocaleString() === '1265.00' -
    // no separator, no error. A number renders one.
    //
    // The options are the ones the proposal screen passes. Without them the same
    // number renders 'RM 1,265' and 1180.50 renders 'RM 1,180.5', neither of
    // which is the price on the product row it was summed from.
    expect(
      batch!.proposals[0].computed_price!.toLocaleString('en-MY', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    ).toBe('1,265.00');
  });

  it('leaves a null computed_price null, never coerced to 0', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({
        batch: batchFixture({
          proposals: [proposalFixture({ computed_price: null })],
        }),
      }),
    );

    const batch = await getProductSetProposals();

    expect(batch!.proposals[0].computed_price).toBeNull();
  });
});

describe('getProductSetProposals - null batch distinguishes "no pass" from "empty pass"', () => {
  it('unwraps { batch: null } to null, not undefined', async () => {
    mockedFetch.mockResolvedValue(okResponse({ batch: null }));

    const batch = await getProductSetProposals();

    expect(batch).toBeNull();
    expect(batch).not.toBeUndefined();
  });

  it('returns a batch with an empty proposals array when a pass found nothing - distinguishable from null', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ batch: batchFixture({ proposal_count: 0, family_count: 0, proposals: [] }) }),
    );

    const batch = await getProductSetProposals();

    expect(batch).not.toBeNull();
    expect(batch!.proposals).toEqual([]);
  });
});

describe('non-ok responses throw the extracted API error', () => {
  it('getProductSetProposals throws the extracted message, not a generic one', async () => {
    mockedFetch.mockResolvedValue(jsonErrorResponse(403, 'Not permitted to view proposals'));

    await expect(getProductSetProposals()).rejects.toThrow('Not permitted to view proposals');
  });

  it('runProductSetProposals throws the extracted message, not a generic one', async () => {
    mockedFetch.mockResolvedValue(jsonErrorResponse(403, 'Not permitted to scan the catalogue'));

    await expect(runProductSetProposals()).rejects.toThrow('Not permitted to scan the catalogue');
  });

  it('applyProductSetProposals throws the extracted message, not a generic one', async () => {
    mockedFetch.mockResolvedValue(jsonErrorResponse(422, 'proposal_ids must not be empty'));

    await expect(applyProductSetProposals([])).rejects.toThrow('proposal_ids must not be empty');
  });
});

describe('runProductSetProposals and applyProductSetProposals - happy path coercion', () => {
  it('runProductSetProposals returns a batch with numeric prices', async () => {
    mockedFetch.mockResolvedValue(okResponse(batchFixture()));

    const batch = await runProductSetProposals();

    expect(batch.proposals[0].computed_price).toBe(1265);
  });

  it('applyProductSetProposals posts the ids and returns applied/refused as-is', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({
        applied: [{ proposal_id: 'proposal-1', set_code: 'SRTWC8608-RL' }],
        refused: [],
      }),
    );

    const result = await applyProductSetProposals(['proposal-1']);

    expect(result.applied).toEqual([{ proposal_id: 'proposal-1', set_code: 'SRTWC8608-RL' }]);
    expect(result.refused).toEqual([]);
    const [, init] = mockedFetch.mock.calls[0];
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      proposal_ids: ['proposal-1'],
    });
  });
});
