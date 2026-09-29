/**
 * UploadPriceListDialog (#1305 reviewer pass, Lane A FE rows, Nit 7): "Leave both dates
 * empty for a price that always applies." is a feature explanation, not a label or a field
 * name - the cursor rule bars it from the UI itself. It moved to
 * `documentation/user-guides/procurement/cost-price-from-supplier.md`.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

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

vi.mock('../hooks/useCostPriceChangeSets', () => ({
  OpenSetExistsError: class OpenSetExistsError extends Error {},
  useProbeCostPriceFile: () => ({ mutate: vi.fn(), isPending: false, data: undefined, error: null }),
  useUploadCostPriceFile: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { UploadPriceListDialog } from './UploadPriceListDialog';

describe('Nit 7: no feature explanation inside the UI', () => {
  it('renders no "Leave both dates empty" sentence', () => {
    render(<UploadPriceListDialog open onOpenChange={() => {}} />);

    expect(screen.queryByText(/Leave both dates empty for a price that always applies/)).not.toBeInTheDocument();
  });
});

describe('Round 6 R5: cost, never price (owner, 28 Sep 2026)', () => {
  it('titles the dialog Upload cost list and names the file a cost list', () => {
    render(<UploadPriceListDialog open onOpenChange={() => {}} />);

    expect(screen.getByRole('heading', { name: 'Upload cost list' })).toBeInTheDocument();
    expect(screen.getByLabelText('Supplier cost list file')).toBeInTheDocument();
    expect(screen.queryByText(/price/i)).not.toBeInTheDocument();
  });
});
