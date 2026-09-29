/**
 * UploadPriceListDialog `onUploaded` (#1288 round 5): the Products page opens this same
 * dialog and reloads its list once an upload is accepted. The callback runs only on
 * success, and the dialog still opens the new set exactly as it does from Purchasing.
 * Real hooks, mocked at the service boundary (same setup as the uploadToast suite).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

// The system SearchableSelect, reduced to a labelled text field that reports the typed
// value, so the suite can pick a supplier and a currency without a popover.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    placeholder,
    id,
  }: {
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
    id?: string;
  }) => (
    <input aria-label={placeholder ?? 'select'} id={id} value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

vi.mock('../../suppliers/services/supplierService', () => ({
  searchSuppliersForSelect: vi.fn(async () => []),
}));

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock('@/lib/toast', () => ({
  toast: { error: (...args: unknown[]) => toastError(...args), success: vi.fn() },
}));

const uploadCostPriceFile = vi.fn();
vi.mock('../services/costPriceService', () => ({
  OpenSetExistsError: class OpenSetExistsError extends Error {
    open_set: { id: string; code: string };
    constructor(open_set: { id: string; code: string }) {
      super(`${open_set.code} is still open for this supplier.`);
      this.open_set = open_set;
    }
  },
  uploadCostPriceFile: (...args: unknown[]) => uploadCostPriceFile(...args),
  probeCostPriceFile: vi.fn(async () => ({
    file_name: 'list.xlsx',
    file_date: null,
    sheets: [],
    total_rows: 0,
    suggested_supplier: null,
    currency: { code: null, source: null },
  })),
}));

import { UploadPriceListDialog } from './UploadPriceListDialog';

beforeEach(() => vi.clearAllMocks());

async function submit(onUploaded: () => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <UploadPriceListDialog open onOpenChange={() => {}} onUploaded={onUploaded} />
    </QueryClientProvider>,
  );
  const file = new File(['data'], 'list.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  fireEvent.change(screen.getByLabelText('Supplier cost list file'), { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText('Search suppliers'), { target: { value: 'sup-1' } });
  fireEvent.change(screen.getByLabelText('Select a currency'), { target: { value: 'CNY' } });
  fireEvent.click(await screen.findByRole('button', { name: 'Upload' }));
}

describe('onUploaded', () => {
  it('runs once on a successful upload, and the new set still opens', async () => {
    uploadCostPriceFile.mockResolvedValue({ id: 'set-1' });
    const onUploaded = vi.fn();
    await submit(onUploaded);
    await waitFor(() => expect(push).toHaveBeenCalledWith('/procurement-management/cost-price-uploads/set-1'));
    expect(onUploaded).toHaveBeenCalledTimes(1);
  });

  it('does not run when the upload fails', async () => {
    uploadCostPriceFile.mockRejectedValue(new Error('Failed to upload the price list'));
    const onUploaded = vi.fn();
    await submit(onUploaded);
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(onUploaded).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });
});
