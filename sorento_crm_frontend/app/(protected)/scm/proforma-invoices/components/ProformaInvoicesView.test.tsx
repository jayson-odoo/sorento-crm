/**
 * The proforma-invoice list: what is on file per supplier. Read-only besides delete - a
 * proforma is the supplier's document, and the correction path is re-upload or delete.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ProformaInvoiceListRow } from '../../services/proformaInvoiceService';

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

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    custom: vi.fn(),
  },
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/proforma-invoices',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    <select id={id} aria-label="Supplier" value={value} onChange={(e) => onChange?.(e.target.value)}>
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const hasPermission = vi.fn((_slug: string) => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
}));

vi.mock('../../hooks/useFulfilment', () => ({
  useFulfilmentSuppliers: () => ({
    data: [{ value: 'sup-1', label: 'Kailu Hardware Factory' }],
  }),
}));

// The dialogs are exercised in their own test files; stub them here so this suite only
// asserts what the list itself renders.
vi.mock('./ProformaUploadDialog', () => ({
  ProformaUploadDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="upload-dialog" /> : null,
}));

const state = {
  data: undefined as { data: ProformaInvoiceListRow[]; total: number } | undefined,
  isLoading: false,
  deleteInvoice: vi.fn(),
  convertInvoices: vi.fn(),
  bulkDeleteInvoices: vi.fn(),
};

vi.mock('../../hooks/useProformaInvoices', () => ({
  useProformaInvoices: () => ({ data: state.data, isLoading: state.isLoading }),
  useDeleteProformaInvoice: () => ({ mutateAsync: state.deleteInvoice }),
  useConvertProformaInvoicesToDraftShipment: () => ({
    mutateAsync: state.convertInvoices,
    isPending: false,
  }),
  useBulkDeleteProformaInvoices: () => ({
    mutateAsync: state.bulkDeleteInvoices,
    isPending: false,
  }),
}));

import { ProformaInvoicesView } from './ProformaInvoicesView';

function invoiceRow(over: Partial<ProformaInvoiceListRow> = {}): ProformaInvoiceListRow {
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
    line_count: 5,
    source_ref: null,
    block_index: 0,
    uploaded_by: 'Ms Tee',
    created_at: '2026-08-01T02:00:00',
    updated_at: '2026-08-01T02:00:00',
    ...over,
  };
}

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProformaInvoicesView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  state.data = { data: [], total: 0 };
  state.isLoading = false;
  state.deleteInvoice = vi.fn().mockResolvedValue(undefined);
  state.convertInvoices = vi.fn().mockResolvedValue({
    shipment_id: 'ship-1',
    shipment_number: 'SHIP-DRAFT-1',
    shipment_status: 'draft',
    supplier_id: null,
    lines_created: 1,
    lines_skipped: 0,
    invoices: [],
    unmatched: [],
  });
  state.bulkDeleteInvoices = vi.fn().mockResolvedValue({ deleted: 0, blocked: [] });
  hasPermission.mockReturnValue(true);
});

describe('ProformaInvoicesView - loading / empty / error / data states', () => {
  it('shows nothing has been read yet, with no supplier filter applied', () => {
    state.data = { data: [], total: 0 };
    renderView();

    expect(screen.getByText('No proforma invoice read yet.')).toBeInTheDocument();
  });

  it('names the supplier once a filter narrows the empty result to none', () => {
    state.data = { data: [], total: 0 };
    renderView();

    fireEvent.change(screen.getByLabelText('Supplier'), { target: { value: 'sup-1' } });

    expect(
      screen.getByText('No proforma invoice on file for this supplier.'),
    ).toBeInTheDocument();
  });

  it('renders every row once loaded', () => {
    state.data = { data: [invoiceRow(), invoiceRow({ id: 'pi-2', pi_number: 'PI-2026-002' })], total: 2 };
    renderView();

    expect(screen.getByText('PI-2026-001')).toBeInTheDocument();
    expect(screen.getByText('PI-2026-002')).toBeInTheDocument();
    expect(screen.getAllByText('Kailu Hardware Factory').length).toBeGreaterThan(0);
  });

  it('a failed read falls back to the empty state rather than crashing', () => {
    // No isError branch in this view - a failed fetch leaves `data` undefined, same as a
    // fetch that has not resolved yet, and the grid still renders without throwing.
    state.data = undefined;
    state.isLoading = false;
    renderView();

    expect(screen.getByText('No proforma invoice read yet.')).toBeInTheDocument();
  });
});

describe('ProformaInvoicesView - the Upload button gate', () => {
  it('shows Upload when the caller holds scm.proforma_invoice.upload', () => {
    // A non-empty result so only the toolbar's own Upload button is on screen - the empty
    // state renders a SECOND one, which is its own test below.
    hasPermission.mockReturnValue(true);
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    expect(screen.getByRole('button', { name: /upload proforma invoice/i })).toBeInTheDocument();
  });

  it('hides Upload entirely without the permission, not just disables it', () => {
    hasPermission.mockReturnValue(false);
    renderView();

    expect(screen.queryByRole('button', { name: /upload proforma invoice/i })).not.toBeInTheDocument();
  });

  it('the empty-state Upload button is gated the same way', () => {
    hasPermission.mockReturnValue(false);
    state.data = { data: [], total: 0 };
    renderView();

    expect(screen.queryByRole('button', { name: /upload proforma invoice/i })).not.toBeInTheDocument();
  });
});

describe('ProformaInvoicesView - delete', () => {
  it('uses the standard confirm copy, never a browser confirm()', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    fireEvent.click(screen.getByRole('button', { name: /delete/i }));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Confirm delete')).toBeInTheDocument();
    expect(within(dialog).getByText(/this action cannot be undone/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/PI-2026-001/)).toBeInTheDocument();
  });

  it('deletes only after the dialog is confirmed', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    fireEvent.click(screen.getByRole('button', { name: /delete/i }));
    expect(state.deleteInvoice).not.toHaveBeenCalled();

    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(state.deleteInvoice).toHaveBeenCalledWith('pi-1'));
  });
});
