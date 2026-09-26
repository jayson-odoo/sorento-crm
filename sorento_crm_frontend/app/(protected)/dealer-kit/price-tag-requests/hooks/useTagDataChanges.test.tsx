/**
 * `useTagDataChanges` - polls the product-data diff behind an open request.
 *
 * AC-C1 (PLAN-price-tag-currency-token-extract-prompt.md section C). Measured
 * 16 Sep on the local prod copy: the batched live resolve behind
 * `GET /{id}/data-changes` costs 16-414 ms; a fixed 30s poll per open page is
 * under 1% of one worker - no push channel, no listener needed. Written
 * test-FIRST: `useTagDataChanges.ts` does not exist yet.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';

import { createTestQueryClient } from '../[id]/design/components/testQueryClient';

const listTagDataChanges = vi.fn();
vi.mock('../../services/priceTagDataService', () => ({
  listTagDataChanges: (...a: unknown[]) => listTagDataChanges(...a),
}));

// THE red import - the hook module does not exist yet.
import { useTagDataChanges, tagDataChangesKey } from './useTagDataChanges';

let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  queryClient = createTestQueryClient();
  listTagDataChanges.mockResolvedValue([]);
});

describe('useTagDataChanges (AC-C1)', () => {
  it('polls every 30s, never in the background, and refetches on window focus', async () => {
    const { result } = renderHook(
      () => useTagDataChanges('req-1', { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(listTagDataChanges).toHaveBeenCalledWith('req-1');

    const query = queryClient
      .getQueryCache()
      .find({ queryKey: tagDataChangesKey('req-1') });
    expect(query).toBeDefined();
    expect(query!.options.refetchInterval).toBe(30_000);
    expect(query!.options.refetchIntervalInBackground).toBe(false);
    expect(query!.options.refetchOnWindowFocus).toBe(true);
  });

  it('is disabled for a terminal request status - the service is never called', async () => {
    renderHook(() => useTagDataChanges('req-1', { enabled: false }), { wrapper });

    // A disabled query never fires its queryFn; give queued microtasks a
    // turn so a wrongly-enabled query would have had the chance to run.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(listTagDataChanges).not.toHaveBeenCalled();
  });
});
