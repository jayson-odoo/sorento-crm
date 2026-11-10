import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

/** QUOTE-TERMS-SELECT owner hand test (10 Nov): a read-only list of the synced AutoCount
 *  payment terms - Term (DisplayTerm), Rule (Terms), Company, Status; no write action. */

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const getPaymentTermList = vi.fn(async () => ({
  data: [
    {
      id: 'pt-1',
      term_code: 'CASH BEFORE DELIVERY',
      term_rule: 'C.O.D.',
      company_code: 'SRT',
      is_active: true,
      updated_at: null,
    },
    {
      id: 'pt-2',
      term_code: '*Net 60 days',
      term_rule: 'Net 60 days',
      company_code: 'MCH',
      is_active: false,
      updated_at: null,
    },
  ],
  pagination: { total: 2, page: 1, limit: 50 },
  empty: false,
}));
vi.mock('../services/paymentTermListService', () => ({
  getPaymentTermList: (...args: unknown[]) =>
    (getPaymentTermList as (...a: unknown[]) => unknown)(...args),
}));

import PaymentTermList from './PaymentTermList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PaymentTermList />
    </QueryClientProvider>,
  );
}

describe('PaymentTermList', () => {
  it('lists each synced term on one row with its rule, company and status', async () => {
    renderList();
    expect(await screen.findByText('CASH BEFORE DELIVERY')).toBeInTheDocument();
    expect(screen.getByText('C.O.D.')).toBeInTheDocument();
    expect(screen.getByText('SRT')).toBeInTheDocument();
    expect(screen.getByText('*Net 60 days')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('asks the server sorted by term, and offers no add or delete', async () => {
    renderList();
    await waitFor(() => expect(getPaymentTermList).toHaveBeenCalled());
    const params = (getPaymentTermList.mock.calls as unknown as [{ sorting: unknown }][])[0][0];
    expect(params.sorting).toEqual([{ id: 'term_code', desc: false }]);
    expect(screen.queryByRole('button', { name: /add/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull();
  });
});
