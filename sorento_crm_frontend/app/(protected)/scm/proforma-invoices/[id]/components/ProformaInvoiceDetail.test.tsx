/**
 * The proforma-invoice detail page: meta strip (Created/Uploaded-style fields never inside a
 * tab body) plus the lines grid, both always rendered per the CRUD standard - even when the
 * lines list is empty, the section stays and states so explicitly.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ProformaInvoiceDetail as ProformaInvoiceDetailData } from '../../../services/proformaInvoiceService';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const state = {
  data: undefined as ProformaInvoiceDetailData | undefined,
  isLoading: false,
  isError: false,
};

vi.mock('../../../hooks/useProformaInvoices', () => ({
  useProformaInvoice: () => state,
  // The header's ProformaInvoiceNavigation (S9) pulls the neighbour list via this hook - one
  // row is not enough to show a pager (see RecordNavigation's `items.length < 2` guard), so
  // it stays hidden and out of these tests' way without a dedicated navigation test.
  useProformaInvoices: () => ({ data: undefined, isLoading: false }),
}));

import { ProformaInvoiceDetail } from './ProformaInvoiceDetail';

function detail(over: Partial<ProformaInvoiceDetailData> = {}): ProformaInvoiceDetailData {
  return {
    id: 'pi-1',
    supplier_id: 'sup-1',
    supplier_code: 'KAILU',
    supplier_name: 'Kailu Hardware Factory',
    pi_number: 'PI-2026-001',
    invoice_date: '2026-08-01',
    currency: 'CNY',
    container_no: 'TEMU1234567',
    bl_no: 'BL-991',
    total_amount: 1000,
    line_count: 1,
    source_ref: 'proforma.xlsx',
    block_index: 0,
    uploaded_by: 'Ms Tee',
    created_at: '2026-08-01T02:00:00',
    updated_at: '2026-08-01T02:00:00',
    lines: [
      {
        id: 'line-1',
        line_no: 1,
        row_number: 2,
        item_code: 'ITEM-1',
        description: 'Widget',
        qty: 10,
        uom: 'PCS',
        unit_price: 100,
        amount: 1000,
        po_ref: 'PO-1',
        remark: null,
        product_code: 'ITEM-1',
        matched: true,
      },
    ],
    ...over,
  };
}

function renderDetail() {
  return render(<ProformaInvoiceDetail id="pi-1" />);
}

beforeEach(() => {
  state.data = undefined;
  state.isLoading = false;
  state.isError = false;
});

describe('ProformaInvoiceDetail - loading / error / data states', () => {
  it('shows a loading skeleton while the detail is fetched', () => {
    state.isLoading = true;
    renderDetail();

    expect(screen.queryByText('PI-2026-001')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to proforma invoices/i })).toBeInTheDocument();
  });

  it('says the invoice was not found rather than rendering a blank page', () => {
    state.isError = true;
    renderDetail();

    expect(screen.getByText('Proforma invoice not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to proforma invoices/i })).toBeInTheDocument();
  });

  it('renders the meta strip fields, none of them inside a tab', () => {
    state.data = detail();
    renderDetail();

    expect(screen.getByText('PI-2026-001')).toBeInTheDocument();
    expect(screen.getByText(/Kailu Hardware Factory/)).toBeInTheDocument();
    expect(screen.getByText('(KAILU)')).toBeInTheDocument();
    expect(screen.getByText('TEMU1234567')).toBeInTheDocument();
    expect(screen.getByText('BL-991')).toBeInTheDocument();
    expect(screen.getByText('Ms Tee')).toBeInTheDocument();
    expect(screen.getByText('proforma.xlsx')).toBeInTheDocument();
  });

  it('renders the invoice lines with matched/unmatched product status', () => {
    state.data = detail({
      lines: [
        { ...detail().lines[0] },
        {
          id: 'line-2', line_no: 2, row_number: 3, item_code: 'ZZ-NOPE',
          description: 'Unknown part', qty: 5, uom: 'PCS', unit_price: 20, amount: 100,
          po_ref: null, remark: null, product_code: null, matched: false,
        },
      ],
    });
    renderDetail();

    // ITEM-1 appears twice - the line's own item code column, and the matched product code
    // subtext under the Matched badge (both correctly the same code here).
    expect(screen.getAllByText('ITEM-1').length).toBeGreaterThanOrEqual(2);
    // "Matched" also names the column header, so the badge is one of at least two matches.
    expect(screen.getAllByText('Matched').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('ZZ-NOPE')).toBeInTheDocument();
    expect(screen.getByText('Not in catalogue')).toBeInTheDocument();
  });

  it('states plainly when the invoice has no lines, rather than an empty table', () => {
    state.data = detail({ lines: [], line_count: 0 });
    renderDetail();

    expect(screen.getByText('This proforma invoice has no lines.')).toBeInTheDocument();
  });
});
