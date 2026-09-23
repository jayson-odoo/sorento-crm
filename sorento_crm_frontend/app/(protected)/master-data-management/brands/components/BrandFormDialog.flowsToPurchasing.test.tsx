/**
 * AC-14/AC-15 (PLAN-brand-flows-to-purchasing.md) - the SAME assertions as
 * `BrandForm.flowsToPurchasing.test.tsx`, run against `BrandFormDialog` instead: it is
 * the component `BrandsList` actually mounts for create/edit (S3, review fix round, 23
 * Sep 2026) - `BrandForm` is a dedicated-page variant nothing on the Brands screen
 * renders, so a defect in `BrandFormDialog`'s own copy of this switch/reset logic
 * would ship unnoticed if only `BrandForm` were covered.
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

describe('BrandFormDialog - Flows to purchasing switch (AC-14)', () => {
  it('renders on by default for a new brand', () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);

    const toggle = screen.getByLabelText('Flows to purchasing');
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('AC-15: round-trips flows_to_purchasing: false into the create payload after a toggle', async () => {
    render(<BrandFormDialog open onOpenChange={() => {}} />);
    fillRequiredFields();

    fireEvent.click(screen.getByLabelText('Flows to purchasing'));
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.flows_to_purchasing).toBe(false);
  });

  it('reflects the stored value on edit: a blocked brand loads with the switch off, and an untouched submit sends false', async () => {
    useBrandMock.mockReturnValue({
      data: {
        id: 'brand-1',
        brand_code: 'ZZTX-001',
        brand_name: 'ZZT Blocked Brand',
        description: null,
        is_active: true,
        access_levels: [],
        flows_to_purchasing: false,
      },
      isLoading: false,
    });

    render(<BrandFormDialog open onOpenChange={() => {}} brandId="brand-1" />);

    const toggle = await screen.findByLabelText('Flows to purchasing');
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'false'));

    fireEvent.click(screen.getByRole('button', { name: /^Update$/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const [{ data: payload }] = updateMutateAsync.mock.calls[0];
    expect(payload.flows_to_purchasing).toBe(false);
  });
});
