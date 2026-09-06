/**
 * M5-06 - the source proforma invoices table renders on DataGrid instead of
 * a raw `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const INVOICES = [
  {
    id: 'pi-1',
    pi_number: 'PI-0001',
    supplier_id: 's-1',
    supplier_name: 'Sanjiang',
    invoice_date: '2026-01-05',
    revision_no: 1,
    revision_count: 1,
    status: 'current' as const,
    source_ref: null,
    currency: 'USD',
    lines: 10,
    total_lines: 10,
    qty: 100,
    total_qty: 100,
    amount: 5000,
  },
  {
    id: 'pi-2',
    pi_number: 'PI-0002',
    supplier_id: 's-2',
    supplier_name: 'Ocean Freight Co',
    invoice_date: '2026-01-10',
    revision_no: 2,
    revision_count: 2,
    status: 'current' as const,
    source_ref: null,
    currency: 'USD',
    lines: 5,
    total_lines: 8,
    qty: 50,
    total_qty: 80,
    amount: 2500,
  },
];

vi.mock('../hooks/usePackingLists', () => ({
  usePackingListSourceInvoices: () => ({
    data: { invoices: INVOICES, created_by: 'Jane Doe' },
    isLoading: false,
  }),
}));

import { SourceProformaInvoicesCard } from './SourceProformaInvoicesCard';

describe('SourceProformaInvoicesCard - DataGrid', () => {
  it('renders the column headers and a real cell value for each invoice', () => {
    render(<SourceProformaInvoicesCard packingListId="pl-1" />);

    expect(screen.getByText('Proforma invoice')).toBeInTheDocument();
    expect(screen.getByText('Supplier')).toBeInTheDocument();
    expect(screen.getByText('Quantity here')).toBeInTheDocument();

    expect(screen.getByText('PI-0001')).toBeInTheDocument();
    expect(screen.getByText('PI-0002')).toBeInTheDocument();
    expect(screen.getByText('Sanjiang')).toBeInTheDocument();
    expect(screen.getByText('Revision 2 of 2')).toBeInTheDocument();
    expect(screen.getByText(/Uploaded by Jane Doe/)).toBeInTheDocument();
  });
});
