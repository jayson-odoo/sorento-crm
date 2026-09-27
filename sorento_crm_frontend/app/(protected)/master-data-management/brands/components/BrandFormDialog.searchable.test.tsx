/**
 * Fix round 3, D4 - `BrandsList` mounts `BrandFormDialog` for Create/Edit, not
 * `BrandForm` (see `BrandFormDialog.flowsToPurchasing.test.tsx`'s own note on
 * why `BrandForm` alone is not enough cover). AC-S0.4 wants "Customers can ask
 * for this brand" on THIS dialog, default on, off for a placeholder brand like
 * OTHERS or NO LOGO.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const createMutateAsync = vi.fn().mockResolvedValue({});
const updateMutateAsync = vi.fn().mockResolvedValue({});
const useBrandMock = vi.fn(() => ({ data: undefined, isLoading: false }));
vi.mock('../hooks/useBrands', () => ({
  useCreateBrand: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateBrand: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useBrand: (id: string | null) => useBrandMock(id),
}));

vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));

import BrandFormDialog from './BrandFormDialog';

beforeEach(() => {
  vi.clearAllMocks();
  useBrandMock.mockReturnValue({ data: undefined, isLoading: false });
});

function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText(/Brand Code/i), { target: { value: 'ZZTX-001' } });
  fireEvent.change(screen.getByLabelText(/Brand Name/i), { target: { value: 'ZZT Test Brand' } });
}

describe('BrandFormDialog - Customers can ask for this brand (AC-S0.4, D4)', () => {
  it('renders on by default for a new brand', () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);

    const toggle = screen.getByLabelText('Customers can ask for this brand');
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('round-trips is_searchable: false into the create payload after a toggle', async () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);
    fillRequiredFields();

    fireEvent.click(screen.getByLabelText('Customers can ask for this brand'));
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.is_searchable).toBe(false);
  });

  it('reflects the stored value on edit: a placeholder brand loads with the switch off, and an untouched submit sends false', async () => {
    useBrandMock.mockReturnValue({
      data: {
        id: 'brand-1',
        brand_code: 'OTHERS',
        brand_name: 'OTHERS',
        description: null,
        is_active: true,
        access_levels: [],
        flows_to_purchasing: true,
        is_searchable: false,
      },
      isLoading: false,
    });

    render(<BrandFormDialog open onOpenChange={() => {}} brandId="brand-1" />);

    const toggle = await screen.findByLabelText('Customers can ask for this brand');
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'false'));

    fireEvent.click(screen.getByRole('button', { name: /^Update$/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const [{ data: payload }] = updateMutateAsync.mock.calls[0];
    expect(payload.is_searchable).toBe(false);
  });

  it('a brand with no is_searchable on record yet defaults the switch on (never blank/off by accident)', async () => {
    useBrandMock.mockReturnValue({
      data: {
        id: 'brand-2',
        brand_code: 'SORENTO',
        brand_name: 'SORENTO',
        description: null,
        is_active: true,
        access_levels: [],
        flows_to_purchasing: true,
      },
      isLoading: false,
    });

    render(<BrandFormDialog open onOpenChange={() => {}} brandId="brand-2" />);

    const toggle = await screen.findByLabelText('Customers can ask for this brand');
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
  });
});
