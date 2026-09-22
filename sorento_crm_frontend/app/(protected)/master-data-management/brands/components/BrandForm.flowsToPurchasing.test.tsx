/**
 * AC-14/AC-15 (PLAN-brand-flows-to-purchasing.md) - the brand create/edit form gets one
 * `Switch` labelled exactly "Flows to purchasing", on by default for a new brand, and it
 * round-trips `flows_to_purchasing: false` on submit after a toggle.
 *
 * RED for Phase 2: `BrandForm` renders no such switch yet, and `BrandFormData` / the
 * submit payload carry no `flows_to_purchasing` field - every assertion below fails
 * against TODAY's code.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, back: vi.fn() }),
}));

const createMutateAsync = vi.fn().mockResolvedValue({});
const updateMutateAsync = vi.fn().mockResolvedValue({});
vi.mock('../hooks/useBrands', () => ({
  useCreateBrand: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateBrand: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useBrand: () => ({ data: undefined, isLoading: false }),
}));

vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));

import BrandForm from './BrandForm';

beforeEach(() => vi.clearAllMocks());

function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText(/Brand Code/i), { target: { value: 'ZZTX-001' } });
  fireEvent.change(screen.getByLabelText(/Brand Name/i), { target: { value: 'ZZT Test Brand' } });
}

describe('BrandForm - Flows to purchasing switch (AC-14)', () => {
  it('renders on by default for a new brand, with no description text', () => {
    render(<BrandForm />);

    const toggle = screen.getByLabelText('Flows to purchasing');
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('AC-15: round-trips flows_to_purchasing: false into the create payload after a toggle', async () => {
    render(<BrandForm />);
    fillRequiredFields();

    fireEvent.click(screen.getByLabelText('Flows to purchasing'));
    fireEvent.click(screen.getByRole('button', { name: /Create Brand/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.flows_to_purchasing).toBe(false);
  });
});
