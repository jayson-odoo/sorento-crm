/**
 * `ProformaInvoiceNavigation` - the prev/next pager over the plain proforma-invoice list.
 *
 * Regression pin (browser evidence run, 20 Aug): the neighbour fetch used `limit: 200`, but
 * `GET /api/v1/scm/proforma-invoices` caps `limit` at 100 (`Query(25, ge=1, le=100)`). 200
 * 422'd the whole fetch - a stray "Input should be less than or equal to 100" toast, `data`
 * stays undefined, and the pager silently rendered nothing instead of prev/next. The mocked
 * hook in `ProformaInvoiceDetail.test.tsx` never exercises the real cap, so this asserts the
 * hook is called with a value the backend actually accepts.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const useProformaInvoices = vi.fn();
vi.mock('../../hooks/useProformaInvoices', () => ({
  useProformaInvoices: (...args: unknown[]) => useProformaInvoices(...args),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import ProformaInvoiceNavigation from './ProformaInvoiceNavigation';

function items(n: number) {
  return Array.from({ length: n }, (_, i) => ({ id: `pi-${i + 1}` }));
}

describe('ProformaInvoiceNavigation', () => {
  it('asks for a limit the backend actually accepts (<= 100), never the PO/SO pagers\' 200', () => {
    useProformaInvoices.mockReturnValue({ data: { data: items(6), total: 6 } });
    render(<ProformaInvoiceNavigation invoiceId="pi-1" />);

    const [, opts] = useProformaInvoices.mock.calls[0] as [unknown, { limit?: number }];
    expect(opts.limit).toBeLessThanOrEqual(100);
  });

  it('renders prev/next once at least 2 invoices are known', () => {
    useProformaInvoices.mockReturnValue({ data: { data: items(6), total: 6 } });
    render(<ProformaInvoiceNavigation invoiceId="pi-3" />);

    expect(screen.getByRole('button', { name: /previous proforma invoice/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next proforma invoice/i })).toBeInTheDocument();
  });

  it('renders nothing for a single-invoice list - there is nowhere to go', () => {
    useProformaInvoices.mockReturnValue({ data: { data: items(1), total: 1 } });
    const { container } = render(<ProformaInvoiceNavigation invoiceId="pi-1" />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing while the neighbour fetch has not resolved yet', () => {
    useProformaInvoices.mockReturnValue({ data: undefined });
    const { container } = render(<ProformaInvoiceNavigation invoiceId="pi-1" />);

    expect(container).toBeEmptyDOMElement();
  });
});
