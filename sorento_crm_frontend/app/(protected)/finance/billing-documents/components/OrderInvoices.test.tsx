/**
 * The Invoices tab of a sales order and of a delivery order (UAC S3-1, DOC-RELATIONS): the same
 * grid, scoped by the order it sits on, every column sorted on the server (owner rule 27 Oct).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/x',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ columnOrder: [], columnVisibility: {}, isLoaded: true, save: vi.fn(), reset: vi.fn() }),
}));
vi.mock('../lib/permissions', () => ({ useCanViewOutstanding: () => true }));
const useBillingDocumentsQuery = vi.fn();
vi.mock('../hooks/useBillingDocuments', () => ({
  useBillingDocumentsQuery: (...a: unknown[]) => useBillingDocumentsQuery(...a),
}));

import { OrderInvoices } from './OrderInvoices';

const ROW = {
  id: 'iv-1',
  document_type: 'invoice',
  doc_no: '202610-3905',
  doc_date: '2026-10-22',
  customer_id: null,
  customer_name: null,
  debtor_code: 'D-1',
  agent_code: null,
  agent_name: null,
  currency_code: 'MYR',
  net_total: 100,
  tax_total: 0,
  total: 100,
  status: 'posted',
  outstanding: null,
  due_date: null,
  outstanding_as_of: null,
};

beforeEach(() => {
  useBillingDocumentsQuery.mockReset();
  useBillingDocumentsQuery.mockReturnValue({ data: { data: [ROW], pagination: { total: 1 } }, isLoading: false, error: null, refetch: vi.fn() });
});

describe('OrderInvoices', () => {
  it('reads a delivery order\'s documents by its id', () => {
    render(<OrderInvoices deliveryOrderId="do-1" />);
    expect(useBillingDocumentsQuery).toHaveBeenLastCalledWith(
      expect.objectContaining({ deliveryOrderId: 'do-1', salesOrderId: undefined }),
    );
    expect(screen.getByRole('link', { name: '202610-3905' })).toHaveAttribute('href', '/finance/billing-documents/iv-1');
  });

  it('reads a sales order\'s documents by its id', () => {
    render(<OrderInvoices salesOrderId="so-1" />);
    expect(useBillingDocumentsQuery).toHaveBeenLastCalledWith(
      expect.objectContaining({ salesOrderId: 'so-1', deliveryOrderId: undefined }),
    );
  });

  it('starts newest first and re-asks the server when a header is clicked', async () => {
    render(<OrderInvoices salesOrderId="so-1" />);
    expect(useBillingDocumentsQuery).toHaveBeenLastCalledWith(
      expect.objectContaining({ sorting: [{ id: 'doc_date', desc: true }] }),
    );
    const header = screen.getAllByRole('columnheader').find((h) => /Number/.test(h.textContent ?? ''));
    fireEvent.click(within(header as HTMLElement).getByRole('button', { name: /Number/ }));
    await waitFor(() =>
      expect(useBillingDocumentsQuery).toHaveBeenLastCalledWith(
        expect.objectContaining({ sorting: [{ id: 'doc_no', desc: false }] }),
      ),
    );
  });

  it('says which kind of order has no documents yet', () => {
    useBillingDocumentsQuery.mockReturnValue({ data: { data: [], pagination: { total: 0 } }, isLoading: false, error: null, refetch: vi.fn() });
    render(<OrderInvoices deliveryOrderId="do-1" />);
    expect(screen.getByText('No billing documents point at this delivery order yet.')).toBeInTheDocument();
  });
});
