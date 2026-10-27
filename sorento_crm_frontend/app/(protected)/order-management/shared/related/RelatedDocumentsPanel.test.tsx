/**
 * DOC-RELATIONS (owner, mock v2 approved 27 Oct): Related is ONE table on the sales order, the
 * delivery order and the billing document - Type, Number (a link to that record), Date, Status,
 * Amount - every column sorted on the server.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/x',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ columnOrder: [], columnVisibility: {}, isLoaded: true, save: vi.fn(), reset: vi.fn() }),
}));
const getRelatedDocuments = vi.fn();
vi.mock('./relatedDocumentsService', () => ({
  getRelatedDocuments: (...a: unknown[]) => getRelatedDocuments(...a),
}));

import { RelatedDocumentsPanel, relatedHref } from './RelatedDocumentsPanel';

const ROWS = [
  { kind: 'sales_order', type: 'sales_order', id: 'so-1', doc_no: 'SO427775', doc_date: '2026-10-14', status: 'open', amount: 1360, currency_code: null },
  { kind: 'delivery_order', type: 'delivery_order', id: 'do-1', doc_no: '202610-3905', doc_date: '2026-10-21', status: 'In Transit', amount: 1280, currency_code: 'MYR' },
  { kind: 'billing_document', type: 'credit_note', id: 'cn-1', doc_no: 'CN-202610-0041', doc_date: '2026-10-25', status: 'posted', amount: 80, currency_code: 'MYR' },
  { kind: 'delivery_order', type: 'delivery_order', id: null, doc_no: 'GHOST-DO-1', doc_date: null, status: null, amount: null, currency_code: null },
];

function renderPanel(kind: 'sales_order' | 'delivery_order' | 'billing_document' = 'billing_document') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RelatedDocumentsPanel kind={kind} id="iv-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getRelatedDocuments.mockReset();
  push.mockReset();
});

describe('RelatedDocumentsPanel', () => {
  it('names every row by what it is and links its number to that record', async () => {
    getRelatedDocuments.mockResolvedValue({ sales_orders: [], delivery_orders: [], billing_documents: [], rows: ROWS });
    renderPanel();

    expect(await screen.findByRole('link', { name: 'SO427775' })).toHaveAttribute('href', '/scm/sales-orders/so-1');
    expect(screen.getByRole('link', { name: '202610-3905' })).toHaveAttribute('href', '/order-management/orders/do-1');
    expect(screen.getByRole('link', { name: 'CN-202610-0041' })).toHaveAttribute('href', '/finance/billing-documents/cn-1');
    expect(screen.getByText('Sales order')).toBeInTheDocument();
    expect(screen.getAllByText('Delivery order')).toHaveLength(2);
    expect(screen.getByText('Credit note')).toBeInTheDocument();
    // Statuses read as words, never slugs.
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('Posted')).toBeInTheDocument();
    expect(screen.getByText('In Transit')).toBeInTheDocument();
  });

  it('keeps a DO the CRM does not hold as plain text', async () => {
    getRelatedDocuments.mockResolvedValue({ sales_orders: [], delivery_orders: [], billing_documents: [], rows: ROWS });
    renderPanel();
    expect(await screen.findByText('GHOST-DO-1')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'GHOST-DO-1' })).toBeNull();
  });

  it('asks the server for date ascending first, then for whatever header is clicked', async () => {
    getRelatedDocuments.mockResolvedValue({ sales_orders: [], delivery_orders: [], billing_documents: [], rows: ROWS });
    renderPanel('sales_order');
    await screen.findByRole('link', { name: 'SO427775' });
    expect(getRelatedDocuments).toHaveBeenLastCalledWith('sales_order', 'iv-1', 'doc_date', 'asc');

    const amount = () =>
      within(
        screen.getAllByRole('columnheader').find((h) => /Amount/.test(h.textContent ?? '')) as HTMLElement,
      ).getByRole('button', { name: /Amount/ });
    fireEvent.click(amount());
    await waitFor(() =>
      expect(getRelatedDocuments).toHaveBeenLastCalledWith('sales_order', 'iv-1', 'amount', 'asc'),
    );
    fireEvent.click(amount());
    await waitFor(() =>
      expect(getRelatedDocuments).toHaveBeenLastCalledWith('sales_order', 'iv-1', 'amount', 'desc'),
    );
    // A third click would clear the sort; the table keeps the last one instead.
    fireEvent.click(amount());
    await new Promise((r) => setTimeout(r, 50));
    expect(getRelatedDocuments).toHaveBeenLastCalledWith('sales_order', 'iv-1', 'amount', 'desc');
  });

  it('opens the record a row is for', async () => {
    getRelatedDocuments.mockResolvedValue({ sales_orders: [], delivery_orders: [], billing_documents: [], rows: ROWS.slice(0, 1) });
    renderPanel();
    fireEvent.click(await screen.findByText('Open'));
    expect(push).toHaveBeenCalledWith('/scm/sales-orders/so-1');
  });

  it('shows an empty state when nothing is related', async () => {
    getRelatedDocuments.mockResolvedValue({ sales_orders: [], delivery_orders: [], billing_documents: [], rows: [] });
    renderPanel();
    expect(await screen.findByText('No related documents')).toBeInTheDocument();
  });
});

describe('relatedHref', () => {
  it('has no link for a row without an id', () => {
    expect(relatedHref({ kind: 'delivery_order', id: null })).toBeNull();
  });
});
