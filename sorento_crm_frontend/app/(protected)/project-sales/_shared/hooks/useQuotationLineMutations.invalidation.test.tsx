/**
 * A line write must refresh the DOCUMENT, not just the lines.
 *
 * Pinned because the bug it guards was visible on screen and invisible to every other test: the
 * per-scope footer and the letterhead total are fed by two different queries, so invalidating the
 * lines alone left the footer moving while the total at the top of the page kept its old figure.
 * Two numbers contradicting each other on one screen is exactly what putting a total under its
 * own column was meant to prevent.
 *
 * The assertion is on the invalidated KEYS rather than on rendered output, because the failure is
 * a cache-wiring mistake: a component test would have to mount the whole document screen and
 * still might pass on stale data that happens to match.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const updateQuotationLine = vi.fn();

vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    updateQuotationLine: (...args: unknown[]) => updateQuotationLine(...args),
  };
});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { useQuotationLineMutations } from './useProjects';
import { quotationDocumentsKey } from './useQuotationDocuments';

const PROJECT_ID = 'p1';
const VERSION_ID = 'v1';

function Harness({ onReady }: { onReady: (api: ReturnType<typeof useQuotationLineMutations>) => void }) {
  const api = useQuotationLineMutations(PROJECT_ID, VERSION_ID);
  // Braces matter: returning onReady's value would hand React a non-function "cleanup".
  React.useEffect(() => {
    onReady(api);
  }, [api, onReady]);
  return null;
}

let client: QueryClient;
let invalidated: unknown[][];

beforeEach(() => {
  vi.clearAllMocks();
  invalidated = [];
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const original = client.invalidateQueries.bind(client);
  client.invalidateQueries = ((filters?: { queryKey?: unknown[] }) => {
    if (filters?.queryKey) invalidated.push(filters.queryKey);
    return original(filters as never);
  }) as typeof client.invalidateQueries;
});

async function saveALine() {
  let api: ReturnType<typeof useQuotationLineMutations> | null = null;
  render(
    <QueryClientProvider client={client}>
      <Harness onReady={(value) => (api = value)} />
    </QueryClientProvider>,
  );
  await act(async () => {
    await api!.update.mutateAsync({ id: 'l1', body: { is_rate_only: true } });
  });
}

describe('useQuotationLineMutations', () => {
  it('refreshes the document behind the letterhead, not only the lines', async () => {
    updateQuotationLine.mockResolvedValue({ id: 'l1', is_below_floor: false });

    await saveALine();

    // The key the letterhead's grand total is read from. Without it, ticking rate-only moved the
    // footer and left the total at the top of the page stale.
    const documentKey = quotationDocumentsKey(PROJECT_ID);
    expect(invalidated).toEqual(
      expect.arrayContaining([expect.arrayContaining([documentKey[0]])]),
    );
  });

  it('still refreshes the lines and the scope list it always did', async () => {
    updateQuotationLine.mockResolvedValue({ id: 'l1', is_below_floor: false });

    await saveALine();

    const flattened = invalidated.map((key) => JSON.stringify(key));
    // The lines of the version being edited.
    expect(flattened.some((key) => key.includes(VERSION_ID))).toBe(true);
    // The scope list, which carries each scope's current total.
    expect(flattened.some((key) => key.includes(PROJECT_ID))).toBe(true);
  });
});
