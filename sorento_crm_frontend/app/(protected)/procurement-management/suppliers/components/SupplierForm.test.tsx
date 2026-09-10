/**
 * SupplierForm - the Country field (S2, `PLAN-local-supplier-oi-routing.md`, AC-1.10): a
 * clearable `SearchableSelect` fed by the countries select endpoint, showing the NAME,
 * storing the id.
 *
 * `SearchableSelect` is stubbed to a plain native `<select>` (the same technique
 * `page.defaultUom.test.tsx` uses) so picking a country is a deterministic `fireEvent.change`
 * rather than a Radix popover interaction jsdom cannot drive; `useCountrySelectQuery` and the
 * supplier mutation hooks are mocked at their module boundary.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

const countrySelectData = vi.fn();
vi.mock(
  '@/app/(protected)/master-data-management/shared/hooks/use-country-select-query',
  () => ({
    useCountrySelectQuery: () => ({ data: countrySelectData() }),
  }),
);

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    clearable,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
    clearable?: boolean;
  }) => (
    <div>
      <select
        aria-label={placeholder ?? 'select'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">-- none --</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {clearable && value ? (
        <button type="button" aria-label="Clear country" onClick={() => onChange('')}>
          Clear
        </button>
      ) : null}
    </div>
  ),
}));

const mutateAsync = vi.fn().mockResolvedValue({ id: 'sup-1' });
vi.mock('../hooks/useSuppliers', () => ({
  useSupplier: () => ({ data: undefined, isLoading: false }),
  useCreateSupplier: () => ({ mutateAsync, isPending: false }),
  useUpdateSupplier: () => ({ mutateAsync, isPending: false }),
}));

import SupplierForm from './SupplierForm';

const MY = { id: 'aaaaaaaa-0000-4000-8000-000000000001', code: 'MY', name: 'Malaysia' };
const CN = { id: 'aaaaaaaa-0000-4000-8000-000000000002', code: 'CN', name: 'China' };

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SupplierForm />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mutateAsync.mockResolvedValue({ id: 'sup-1' });
  countrySelectData.mockReturnValue([MY, CN]);
});

describe('SupplierForm: Country', () => {
  it('shows country names, not ids, as the select options', () => {
    renderForm();

    const select = screen.getByLabelText('Search country...') as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.textContent);
    expect(labels).toEqual(expect.arrayContaining(['Malaysia', 'China']));
    // The id is legitimately the option's VALUE (addressing) - what must never appear is a
    // UUID as the VISIBLE label text a person reads.
    expect(labels.some((label) => /[0-9a-f-]{8,}/i.test(label ?? ''))).toBe(false);
  });

  it('submits the selected country as country_id', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText(/supplier code/i), { target: { value: 'ZZTSUP1' } });
    fireEvent.change(screen.getByLabelText(/supplier name/i), { target: { value: 'Zzt Supplier' } });
    fireEvent.change(screen.getByLabelText('Search country...'), {
      target: { value: MY.id },
    });

    fireEvent.click(screen.getByRole('button', { name: /create supplier/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ country_id: MY.id }),
      ),
    );
  });

  it('is clearable: clearing the country submits country_id null', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText(/supplier code/i), { target: { value: 'ZZTSUP2' } });
    fireEvent.change(screen.getByLabelText(/supplier name/i), { target: { value: 'Zzt Supplier' } });
    fireEvent.change(screen.getByLabelText('Search country...'), {
      target: { value: MY.id },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Clear country' }));

    fireEvent.click(screen.getByRole('button', { name: /create supplier/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ country_id: null }),
      ),
    );
  });
});
