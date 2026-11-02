/**
 * CABANA-NO-SELLING-PRICE: the "Promotions carry no selling price" switch on the
 * brand create/edit modal round-trips `no_promo_selling_price`.
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

const LABEL = 'Promotions carry no selling price';

beforeEach(() => {
  vi.clearAllMocks();
  useBrandMock.mockReturnValue({ data: undefined, isLoading: false });
});

describe('BrandFormDialog - Promotions carry no selling price', () => {
  it('is off by default and a toggle sends true on create', async () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByLabelText(/Brand Code/i), { target: { value: 'ZZTX-002' } });
    fireEvent.change(screen.getByLabelText(/Brand Name/i), { target: { value: 'ZZT Brand' } });

    const toggle = screen.getByLabelText(LABEL);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].no_promo_selling_price).toBe(true);
  });

  it('loads a flagged brand with the switch on and keeps it on an untouched update', async () => {
    useBrandMock.mockReturnValue({
      data: {
        id: 'brand-1',
        brand_code: 'CABANA',
        brand_name: 'Cabana',
        description: null,
        is_active: true,
        access_levels: [],
        flows_to_purchasing: true,
        no_promo_selling_price: true,
      },
      isLoading: false,
    });
    render(<BrandFormDialog open onOpenChange={() => {}} brandId="brand-1" />);

    const toggle = await screen.findByLabelText(LABEL);
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
    fireEvent.click(screen.getByRole('button', { name: /^Update$/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    expect(updateMutateAsync.mock.calls[0][0].data.no_promo_selling_price).toBe(true);
  });
});
