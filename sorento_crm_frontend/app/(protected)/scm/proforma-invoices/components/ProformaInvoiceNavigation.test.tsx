/**
 * `ProformaInvoiceNavigation` - the prev/next pager over the proforma-invoice list.
 *
 * Two things it has to get right, and both were wrong before:
 *
 * - **It walks the set the reader was looking at.** The neighbours are rebuilt from the
 *   query the list carried into the detail URL (supplier, packing-list state, search box,
 *   page). It used to fetch the newest 100 invoices unfiltered, so the row after the one you
 *   opened was not the row under it in the list.
 * - **It asks for a limit the backend accepts.** `GET /api/v1/scm/proforma-invoices` caps
 *   `limit` at 100 (`Query(25, ge=1, le=100)`); 200 422s the whole fetch, which surfaces as a
 *   stray toast, leaves `data` undefined and silently renders no pager at all.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const useProformaInvoices = vi.fn();
vi.mock('../../hooks/useProformaInvoices', () => ({
  useProformaInvoices: (...args: unknown[]) => useProformaInvoices(...args),
}));

const push = vi.fn();
let search = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => search,
}));

import ProformaInvoiceNavigation from './ProformaInvoiceNavigation';

function items(n: number) {
  return Array.from({ length: n }, (_, i) => ({ id: `pi-${i + 1}` }));
}

/** `[supplierId, options]` from the last call the component made. */
function lastCall(): [string | null, Record<string, unknown>] {
  const call = useProformaInvoices.mock.calls[useProformaInvoices.mock.calls.length - 1];
  return call as [string | null, Record<string, unknown>];
}

beforeEach(() => {
  push.mockReset();
  useProformaInvoices.mockReset();
  search = new URLSearchParams();
});

describe('ProformaInvoiceNavigation', () => {
  it('asks for a limit the backend actually accepts (<= 100), never the PO/SO pagers 200', () => {
    search = new URLSearchParams('page=1&limit=200');
    useProformaInvoices.mockReturnValue({ data: { data: items(6), total: 6 } });
    render(<ProformaInvoiceNavigation invoiceId="pi-1" />);

    expect(lastCall()[1].limit as number).toBeLessThanOrEqual(100);
  });

  it('rebuilds the SAME filtered, searched page the list was showing', () => {
    search = new URLSearchParams(
      'page=3&limit=25&query=FSCU&supplier_id=sup-1&placement=not_converted',
    );
    useProformaInvoices.mockReturnValue({ data: { data: items(6), total: 60 } });
    render(<ProformaInvoiceNavigation invoiceId="pi-3" />);

    const [supplierId, options] = lastCall();
    expect(supplierId).toBe('sup-1');
    expect(options).toMatchObject({
      placement: 'not_converted',
      query: 'FSCU',
      limit: 25,
      offset: 50,
    });
  });

  it('asks for the unfiltered first page when the URL carries no query', () => {
    useProformaInvoices.mockReturnValue({ data: { data: items(6), total: 6 } });
    render(<ProformaInvoiceNavigation invoiceId="pi-1" />);

    const [supplierId, options] = lastCall();
    expect(supplierId).toBeNull();
    expect(options).toMatchObject({ placement: null, query: null, offset: 0 });
  });

  it('renders prev/next once at least 2 invoices are known', () => {
    useProformaInvoices.mockReturnValue({ data: { data: items(6), total: 6 } });
    render(<ProformaInvoiceNavigation invoiceId="pi-3" />);

    expect(screen.getByRole('button', { name: /previous proforma invoice/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next proforma invoice/i })).toBeInTheDocument();
  });

  it('stops at both ends rather than wrapping round to the top', () => {
    useProformaInvoices.mockReturnValue({ data: { data: items(3), total: 3 } });
    render(<ProformaInvoiceNavigation invoiceId="pi-1" />);

    // First row: there is no previous, and a chevron that jumped to the last one would read
    // as a broken step rather than as a feature.
    expect(screen.getByRole('button', { name: /previous proforma invoice/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /next proforma invoice/i })).toBeEnabled();
  });

  it('keeps the list query on the URL as the reader steps', () => {
    search = new URLSearchParams('page=1&limit=25&placement=not_converted');
    useProformaInvoices.mockReturnValue({ data: { data: items(3), total: 3 } });
    render(<ProformaInvoiceNavigation invoiceId="pi-1" />);

    fireEvent.click(screen.getByRole('button', { name: /next proforma invoice/i }));

    expect(push).toHaveBeenCalledWith(
      '/scm/proforma-invoices/pi-2?page=1&limit=25&placement=not_converted',
    );
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
