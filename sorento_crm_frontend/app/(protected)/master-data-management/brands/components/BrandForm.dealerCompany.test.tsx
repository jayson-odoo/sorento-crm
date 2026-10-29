/**
 * BULK-CONTACT-ACCESS U21: the brand record page form (BrandForm, not only the dialog) carries the
 * clearable "Dealer group" select and submits dealer_company_id (null when cleared).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }));

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
vi.mock('@/app/(protected)/system-management/companies/services/companyService', () => ({
  getCompaniesSelect: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    selectedOption?: { value: string; label: string };
    'aria-label'?: string;
  }) => (
    <div>
      <span data-testid={`value-${props['aria-label']}`}>{props.selectedOption?.label ?? props.value}</span>
      <button type="button" onClick={() => props.onChange('')}>{`Clear ${props['aria-label']}`}</button>
    </div>
  ),
}));

import BrandForm from './BrandForm';

const stored = {
  id: 'brand-1', brand_code: 'MOCHA', brand_name: 'Mocha', is_active: true, access_levels: [],
  flows_to_purchasing: true, dealer_company_id: 'company-mch', dealer_company_name: 'Mocha Sdn Bhd',
};

beforeEach(() => {
  vi.clearAllMocks();
  useBrandMock.mockReturnValue({ data: stored, isLoading: false });
});

describe('BrandForm - Dealer group', () => {
  it('shows the Dealer group field with the stored company name', async () => {
    render(<BrandForm brandId="brand-1" />);
    expect(await screen.findByText('Dealer group')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('value-Dealer group')).toHaveTextContent('Mocha Sdn Bhd'));
  });

  it('an untouched update sends the stored dealer_company_id', async () => {
    render(<BrandForm brandId="brand-1" />);
    await screen.findByText('Dealer group');
    fireEvent.click(screen.getByRole('button', { name: /Update Brand/i }));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const [{ data }] = updateMutateAsync.mock.calls[0];
    expect(data.dealer_company_id).toBe('company-mch');
  });

  it('clearing the field sends dealer_company_id null, not an empty string', async () => {
    render(<BrandForm brandId="brand-1" />);
    await screen.findByText('Dealer group');
    fireEvent.click(screen.getByRole('button', { name: 'Clear Dealer group' }));
    fireEvent.click(screen.getByRole('button', { name: /Update Brand/i }));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const [{ data }] = updateMutateAsync.mock.calls[0];
    expect(data).toHaveProperty('dealer_company_id', null);
  });
});
