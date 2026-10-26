/**
 * BULK-CONTACT-ACCESS (owner ruling 26 Oct 15:20): `dealer_company_id` on the brand form. The
 * company whose dealers get this brand from the access-sheet upload; empty = a project brand.
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

describe('BrandFormDialog - dealer company', () => {
  it('an untouched edit submit keeps the stored dealer_company_id', async () => {
    useBrandMock.mockReturnValue({
      data: {
        id: 'brand-1', brand_code: 'MOCHA', brand_name: 'Mocha', description: null, is_active: true,
        access_levels: [], flows_to_purchasing: true, chatbot_weight: 0,
        dealer_company_id: 'company-mch', dealer_company_name: 'Mocha Sdn Bhd',
      },
      isLoading: false,
    });
    render(<BrandFormDialog open onOpenChange={() => {}} brandId="brand-1" />);
    await screen.findByLabelText(/Brand Name/i);
    fireEvent.click(screen.getByRole('button', { name: /^Update$/i }));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const [{ data: payload }] = updateMutateAsync.mock.calls[0];
    expect(payload.dealer_company_id).toBe('company-mch');
  });

  it('a new brand with no dealer company sends null, never an empty string', async () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByLabelText(/Brand Code/i), { target: { value: 'ZZTX-002' } });
    fireEvent.change(screen.getByLabelText(/Brand Name/i), { target: { value: 'ZZT Project Brand' } });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload).toHaveProperty('dealer_company_id', null);
  });
});
