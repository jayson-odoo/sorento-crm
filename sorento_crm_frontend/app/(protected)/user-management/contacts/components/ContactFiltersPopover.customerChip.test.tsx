/**
 * ACCESS-SHEET-FIXES fix 3: the toolbar chip for a Customer filter restored from the URL names the
 * customer across every granted company. It shares its query key with ContactAccessFilters, so both
 * read through the same grants read-back; the company-scoped single-customer GET 404s for a Mocha
 * customer seen from Sorento and left the chip on "Selected customer".
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const customerSvc = vi.hoisted(() => ({ searchCustomersSelect: vi.fn(), getCustomer: vi.fn() }));
vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => customerSvc);
vi.mock('../../contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));
vi.mock('../[id]/services/contactService', () => ({ getContact: vi.fn(), getContacts: vi.fn() }));

import { useContactFiltersToolbar } from './ContactFiltersPopover';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('contacts filter chip: customer', () => {
  it('labels a restored Mocha customer through the grants read-back', async () => {
    customerSvc.searchCustomersSelect.mockResolvedValue([
      { value: 'cust-m', label: 'Mocha · 300-1001 - DEALER M', description: '' },
    ]);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () =>
        useContactFiltersToolbar({
          accessFilters: { customerId: 'cust-m' } as never,
          customersNone: false,
          noTags: false,
          setAccessFilters: () => {},
          setCustomersNone: () => {},
          setNoTags: () => {},
        }),
      { wrapper },
    );
    await waitFor(() =>
      expect(JSON.stringify(result.current.activeSummary)).toContain('Customer: Mocha · 300-1001 - DEALER M'),
    );
    expect(customerSvc.getCustomer).not.toHaveBeenCalled();
  });
});
