/**
 * UploadPriceListDialog (#1305 reviewer pass, Lane A FE rows).
 *
 * Nit 4: the dropzone accepted `.xls` even though the server only reads `.xlsx` - a `.xls`
 * drop looked accepted client-side and then failed on the server round trip. The FE now
 * accepts `.xlsx` only, so `.xls` is refused at the dropzone.
 *
 * Nit 5 (first half): a probe failure was silent - `probe.error` reached the component but
 * nothing rendered it, so a bad file just sat there with the spinner gone and no message.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ placeholder }: { placeholder?: string }) => (
    <div data-testid="searchable-select-stub">{placeholder}</div>
  ),
}));

vi.mock('../../suppliers/services/supplierService', () => ({
  searchSuppliersForSelect: vi.fn(async () => []),
}));

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock('@/lib/toast', () => ({
  toast: { error: (...args: unknown[]) => toastError(...args), success: vi.fn() },
}));

const probeMutate = vi.fn();
const uploadMutateAsync = vi.fn();
let probeState: { isPending: boolean; data: unknown; error: Error | null } = {
  isPending: false,
  data: undefined,
  error: null,
};
vi.mock('../hooks/useCostPriceChangeSets', () => ({
  OpenSetExistsError: class OpenSetExistsError extends Error {
    open_set: { id: string; code: string };
    constructor(open_set: { id: string; code: string }) {
      super(`${open_set.code} is still open for this supplier.`);
      this.open_set = open_set;
    }
  },
  useProbeCostPriceFile: () => ({ mutate: probeMutate, isPending: probeState.isPending, data: probeState.data, error: probeState.error }),
  useUploadCostPriceFile: () => ({ mutateAsync: uploadMutateAsync, isPending: false }),
}));

import { UploadPriceListDialog } from './UploadPriceListDialog';

beforeEach(() => {
  vi.clearAllMocks();
  probeState = { isPending: false, data: undefined, error: null };
});

function renderDialog() {
  return render(<UploadPriceListDialog open onOpenChange={() => {}} />);
}

describe('Nit 4: the dropzone accepts .xlsx only', () => {
  it('refuses a .xls file client-side and never probes it', () => {
    renderDialog();
    const input = screen.getByLabelText('Supplier cost list file') as HTMLInputElement;
    const file = new File(['data'], 'price-list.xls', { type: 'application/vnd.ms-excel' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(probeMutate).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledWith('price-list.xls is not an Excel file');
  });
});

describe('Nit 5: a probe failure renders its error message', () => {
  it('shows the extracted error text when probe.error is set', () => {
    probeState = { isPending: false, data: undefined, error: new Error('Could not read this file') };
    renderDialog();

    expect(screen.getByText('Could not read this file')).toBeInTheDocument();
  });
});
