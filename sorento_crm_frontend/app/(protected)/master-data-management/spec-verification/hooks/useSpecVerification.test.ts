/**
 * useSpecVerification - the pure summary/skip helpers and the cache patcher.
 *
 * These are the pieces AC-D.11 and AC-D.22 actually hinge on: the bulk outcome
 * copy, which codes stay selected, and that a patched row keeps its position in
 * the list rather than being re-sorted out from under the reviewer.
 */
import { describe, it, expect } from 'vitest';

import {
  skippedUnverifyCodes,
  skippedVerifyCodes,
  summariseUnverify,
  summariseVerify,
} from './useSpecVerification';
import type {
  SpecVerificationRow,
  UnverifyBulkResult,
  VerifyBulkResult,
} from '../types/specVerification.types';

describe('summariseVerify', () => {
  it('reports a clean batch as just the verified count', () => {
    const results: VerifyBulkResult[] = [
      { product_code: 'A', outcome: 'verified' },
      { product_code: 'B', outcome: 'already_verified' },
    ];
    expect(summariseVerify(results)).toBe('2 verified');
  });

  it('names each skip reason with its own count', () => {
    // Two reasons left: the open-exception refusal went with the exceptions UI
    // (captain ruling 2026-08-17), so a code that used to be skipped now verifies.
    const results: VerifyBulkResult[] = [
      ...Array.from(
        { length: 42 },
        (_, i): VerifyBulkResult => ({
          product_code: `V${i}`,
          outcome: 'verified',
        }),
      ),
      { product_code: 'C1', outcome: 'values_changed' },
      { product_code: 'G1', outcome: 'not_found' },
    ];

    expect(summariseVerify(results)).toBe(
      '42 verified, 1 skipped - changed while you were reviewing, 1 skipped - no longer in the list',
    );
  });

  it('a batch that is entirely skipped carries no "verified" clause', () => {
    const results: VerifyBulkResult[] = [
      { product_code: 'A', outcome: 'values_changed' },
      { product_code: 'B', outcome: 'not_found' },
    ];
    expect(summariseVerify(results)).toBe(
      '1 skipped - changed while you were reviewing, 1 skipped - no longer in the list',
    );
  });
});

describe('summariseUnverify', () => {
  it('counts unverified vs unchanged', () => {
    const results: UnverifyBulkResult[] = [
      { product_code: 'A', outcome: 'unverified' },
      { product_code: 'B', outcome: 'unverified' },
      { product_code: 'C', outcome: 'no_change' },
    ];
    expect(summariseUnverify(results)).toBe('2 unverified, 1 unchanged');
  });

  it('an all-no_change batch carries no "unverified" clause', () => {
    const results: UnverifyBulkResult[] = [
      { product_code: 'A', outcome: 'no_change' },
    ];
    expect(summariseUnverify(results)).toBe('1 unchanged');
  });
});

describe('skippedVerifyCodes / skippedUnverifyCodes', () => {
  it('verify: only acted codes (verified/already_verified) are released, the rest stay', () => {
    const results: VerifyBulkResult[] = [
      { product_code: 'A', outcome: 'verified' },
      { product_code: 'B', outcome: 'already_verified' },
      { product_code: 'D', outcome: 'values_changed' },
      { product_code: 'E', outcome: 'not_found' },
    ];
    expect(skippedVerifyCodes(results)).toEqual(['D', 'E']);
  });

  it('unverify: only "unverified" is acted, "no_change" stays selected', () => {
    const results: UnverifyBulkResult[] = [
      { product_code: 'A', outcome: 'unverified' },
      { product_code: 'B', outcome: 'no_change' },
    ];
    expect(skippedUnverifyCodes(results)).toEqual(['B']);
  });
});

// Driven through the mutation hook rather than by calling `patchWorklistRows`
// directly, so the test still pins the real cache-patching behaviour end to end.
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import React from 'react';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));
vi.mock('../services/specVerificationService', () => ({
  getSpecVerificationWorklist: vi.fn(),
  verifySpecBulk: vi.fn(),
  unverifySpecBulk: vi.fn(),
}));

import { verifySpecBulk } from '../services/specVerificationService';
import {
  useSpecVerificationMutations,
  WORKLIST_KEY,
} from './useSpecVerification';
import type { SpecVerificationWorklistResponse } from '../types/specVerification.types';

const mockVerifyBulk = vi.mocked(verifySpecBulk);

function baseRow(
  code: string,
  state: 'unverified' | 'verified' | 'needs_reverify',
): SpecVerificationRow {
  return {
    product_id: `id-${code}`,
    product_code: code,
    product_name: code,
    class_label: 'Kitchen Sink',
    brand_name: null,
    is_discontinued: false,
    coverage: {
      have: 1,
      applicable: 2,
      items: [
        {
          spec_key: 'material',
          label: 'Material',
          value: { value: 'ceramic' },
        },
        { spec_key: 'finish', label: 'Finish', value: null },
      ],
    },
    open_exceptions: 0,
    values_hash: `hash-${code}`,
    verification: {
      state,
      verified_by_name: null,
      verified_at: null,
      invalidated_at: null,
      invalidated_reason: null,
      invalidated_by_name: null,
      invalidated_diff: null,
    },
  };
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return React.createElement(QueryClientProvider, { client }, children);
  };
}

beforeEach(() => vi.clearAllMocks());

describe('patchRows via useSpecVerificationMutations().verify', () => {
  it('patches only the acted row in place, keeps order, and refreshes values_hash', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const initial: SpecVerificationWorklistResponse = {
      data: [
        baseRow('A', 'needs_reverify'),
        baseRow('B', 'unverified'),
        baseRow('C', 'unverified'),
      ],
      pagination: { total: 3, page: 1, limit: 25 },
      summary: { total: 3, verified: 0, needs_reverify: 1, unverified: 2 },
      classes: ['Kitchen Sink'],
    };
    client.setQueryData([WORKLIST_KEY, 0, 25, [], '', '', '', false], initial);

    mockVerifyBulk.mockResolvedValue({
      results: [
        {
          product_code: 'B',
          outcome: 'verified',
          values_hash: 'hash-B-v2',
          verification: {
            state: 'verified',
            verified_by_name: 'Jay',
            verified_at: '2026-08-10T09:00:00',
            invalidated_at: null,
            invalidated_reason: null,
            invalidated_by_name: null,
            invalidated_diff: null,
          },
        },
      ],
      counts: { verified: 1, skipped: 0 },
    });

    const { result } = renderHook(() => useSpecVerificationMutations(), {
      wrapper: wrapper(client),
    });

    await result.current.verify.mutateAsync([
      { product_code: 'B', values_hash: 'hash-B' },
    ]);

    await waitFor(() => {
      const cached = client.getQueryData<SpecVerificationWorklistResponse>([
        WORKLIST_KEY,
        0,
        25,
        [],
        '',
        '',
        '',
        false,
      ]);
      expect(cached?.data.map((r) => r.product_code)).toEqual(['A', 'B', 'C']); // order unchanged
      expect(cached?.data[1].verification.state).toBe('verified');
      expect(cached?.data[1].values_hash).toBe('hash-B-v2'); // refreshed
      expect(cached?.data[0].verification.state).toBe('needs_reverify'); // untouched
      expect(cached?.data[2].verification.state).toBe('unverified'); // untouched
      expect(cached?.summary).toEqual({
        total: 3,
        verified: 1,
        needs_reverify: 1,
        unverified: 1, // one row left unverified -> now stamped verified
      });
    });
  });
});
