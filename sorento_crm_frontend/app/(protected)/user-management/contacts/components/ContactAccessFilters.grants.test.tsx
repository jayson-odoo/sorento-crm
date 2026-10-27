/**
 * ACCESS-SHEET-FIXES fix 3 (owner 27 Oct: "everything here should be company-less [...] same goes
 * for the filter selection"). The Customer filter searches every company the viewer holds, labels
 * each option with its company (the import picker's formatter, customerService.searchCustomersSelect),
 * and reads a URL-restored id back the same way, so a Mocha customer seen from Sorento keeps its name.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const customerSvc = vi.hoisted(() => ({ searchCustomersSelect: vi.fn(), getCustomer: vi.fn() }));
vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => customerSvc);
vi.mock('../../contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));
vi.mock('../[id]/services/contactService', () => ({ getContact: vi.fn(), getContacts: vi.fn() }));

const selects = vi.hoisted(() => ({ props: [] as Record<string, unknown>[] }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: Record<string, unknown> & { placeholder?: string; selectedOption?: { label: string } }) => {
    selects.props.push(props);
    return <div data-testid={props.placeholder}>{props.selectedOption?.label ?? ''}</div>;
  },
}));

import ContactAccessFilters from './ContactAccessFilters';

const MOCHA = { value: 'cust-m', label: 'Mocha · 300-1001 - DEALER M', description: '' };

function renderFilters(value: Record<string, string | null> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ContactAccessFilters value={value as never} onChange={() => {}} />
    </QueryClientProvider>,
  );
}

const customerSelect = () =>
  [...selects.props].reverse().find((p) => p.placeholder === 'Customer: any') as {
    fetchOptions: (q: string) => Promise<{ value: string; label: string }[]>;
  };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  selects.props = [];
});

describe('ContactAccessFilters customer filter', () => {
  it('searches every granted company and labels each option with its company', async () => {
    customerSvc.searchCustomersSelect.mockResolvedValue([MOCHA]);
    renderFilters();
    const options = await customerSelect().fetchOptions('300-1001');
    expect(customerSvc.searchCustomersSelect).toHaveBeenCalledWith('300-1001', 0, { companyScope: 'grants' });
    expect(options).toEqual([{ value: 'cust-m', label: 'Mocha · 300-1001 - DEALER M' }]);
  });

  it('reads a restored id back across companies with the same company-tagged label', async () => {
    customerSvc.searchCustomersSelect.mockResolvedValue([MOCHA]);
    renderFilters({ customerId: 'cust-m' });
    await waitFor(() =>
      expect(screen.getByTestId('Customer: any').textContent).toBe('Mocha · 300-1001 - DEALER M'),
    );
    expect(customerSvc.searchCustomersSelect).toHaveBeenCalledWith('', 0, {
      companyScope: 'grants',
      customerId: 'cust-m',
    });
    expect(customerSvc.getCustomer).not.toHaveBeenCalled();
  });
});
