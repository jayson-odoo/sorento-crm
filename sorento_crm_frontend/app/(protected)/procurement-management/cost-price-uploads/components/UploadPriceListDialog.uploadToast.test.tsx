/**
 * UploadPriceListDialog (#1305 reviewer pass, Lane A FE rows, Nit 5 second half): an upload
 * failure toasted TWICE - once from `useUploadCostPriceFile`'s own `onError` and once from
 * this component's own catch block on the same rejected promise.
 *
 * Unlike `UploadPriceListDialog.test.tsx`, the REAL hooks are used here (mocked only at the
 * service boundary) so the mutation's own `onError` toast actually fires - that is the
 * second call the fix has to remove.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    placeholder,
    id,
    options,
  }: {
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
    id?: string;
    options?: { value: string; label: string }[];
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" />
      <option value="sup-1">A Supplier</option>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
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

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UploadPriceListDialog open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

describe('Nit 5: an upload failure toasts exactly once', () => {
  it('calls toast.error exactly once when the upload rejects with a generic error', async () => {
    uploadCostPriceFile.mockRejectedValue(new Error('Failed to upload the price list'));
    renderDialog();

    const file = new File(['data'], 'list.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    fireEvent.change(screen.getByLabelText('Supplier cost list file'), { target: { files: [file] } });

    fireEvent.change(screen.getByLabelText('Search suppliers'), { target: { value: 'sup-1' } });
    fireEvent.change(screen.getByLabelText('Select a currency'), { target: { value: 'CNY' } });

    fireEvent.click(await screen.findByRole('button', { name: 'Upload' }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError).toHaveBeenCalledTimes(1);
  });
});
