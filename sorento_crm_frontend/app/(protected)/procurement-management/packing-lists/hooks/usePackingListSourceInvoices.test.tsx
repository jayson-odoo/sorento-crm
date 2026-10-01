/**
 * The proforma invoices behind a container (PL-TABS-ACCESS).
 *
 * This read is shared by every tab of the packing list, so its failure must not be loud on
 * a tab that never asked for it: it opts out of the app-wide error toast and reports in
 * place instead, and a 403 is an answer rather than a blip, so it is not retried. The card
 * that does show it must say it failed, never fall through to its "none" empty state.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, renderHook, screen, waitFor } from '@testing-library/react';
import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getSourceInvoices = vi.fn();
vi.mock('../services/packingListService', () => ({
  getPackingListSourceInvoices: (id: string) => getSourceInvoices(id),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { usePackingListSourceInvoices } from './usePackingLists';
import SourceProformaInvoicesCard from '../components/SourceProformaInvoicesCard';

/** The app's own defaults (providers/query-provider.tsx): retry once, toast on error unless
 *  the query says `meta.silent`. */
function appClient(toasts: string[]) {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, retryDelay: 0 } },
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.meta?.silent) return;
        toasts.push((error as Error).message);
      },
    }),
  });
}

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

beforeEach(() => getSourceInvoices.mockReset());
afterEach(() => cleanup());

describe('usePackingListSourceInvoices', () => {
  it('does not retry a 403 and raises no toast', async () => {
    getSourceInvoices.mockRejectedValue(new Error('Permission required: scm.dashboard.view'));
    const toasts: string[] = [];
    const { result } = renderHook(() => usePackingListSourceInvoices('pl-1'), {
      wrapper: wrapper(appClient(toasts)),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(getSourceInvoices).toHaveBeenCalledTimes(1);
    expect(toasts).toEqual([]);
  });

  it('fetches nothing when told it may not', async () => {
    const { result } = renderHook(
      () => usePackingListSourceInvoices('pl-1', { enabled: false }),
      { wrapper: wrapper(appClient([])) },
    );

    await new Promise((r) => setTimeout(r, 20));
    expect(result.current.fetchStatus).toBe('idle');
    expect(getSourceInvoices).not.toHaveBeenCalled();
  });
});

describe('SourceProformaInvoicesCard', () => {
  it('says the read failed instead of claiming the container has no proforma invoice', async () => {
    getSourceInvoices.mockRejectedValue(new Error('Permission required: scm.dashboard.view'));
    render(<SourceProformaInvoicesCard packingListId="pl-1" />, {
      wrapper: wrapper(appClient([])),
    });

    expect(await screen.findByText('Permission required: scm.dashboard.view')).toBeInTheDocument();
    expect(screen.queryByText(/Read from a packing list/)).not.toBeInTheDocument();
  });
});
