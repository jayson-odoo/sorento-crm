/**
 * W5 (owner hand test round 2 on PR #833): the "Chatbot default brand" switch on the
 * create/edit dialog the Brands list mounts.
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

describe('BrandFormDialog - Chatbot default brand switch (W5)', () => {
  it('renders off by default for a new brand', () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);

    expect(screen.getByLabelText('Chatbot default brand')).toHaveAttribute('aria-checked', 'false');
  });

  it('round-trips is_chatbot_default: true into the create payload after a toggle', async () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);
    fillRequiredFields();

    fireEvent.click(screen.getByLabelText('Chatbot default brand'));
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.is_chatbot_default).toBe(true);
  });

  it('reflects the stored value on edit and an untouched submit keeps it', async () => {
    useBrandMock.mockReturnValue({
      data: {
        id: 'brand-1',
        brand_code: 'SRT',
        brand_name: 'Sorento',
        description: null,
        is_active: true,
        access_levels: [],
        flows_to_purchasing: true,
        is_chatbot_default: true,
      },
      isLoading: false,
    });

    render(<BrandFormDialog open onOpenChange={() => {}} brandId="brand-1" />);

    const toggle = await screen.findByLabelText('Chatbot default brand');
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));

    fireEvent.click(screen.getByRole('button', { name: /^Update$/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const [{ data: payload }] = updateMutateAsync.mock.calls[0];
    expect(payload.is_chatbot_default).toBe(true);
  });
});
