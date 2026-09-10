/**
 * CountryList - the Master Data Countries DataGrid (S1, `PLAN-local-supplier-oi-routing.md`,
 * AC-1.8): search, Add, row-click-to-edit, and a deferred (no confirm dialog) Delete per the
 * CRUD standard.
 *
 * `useCountries` (data) and `@/hooks/useDeferredRowAction` (the delete parking mechanism,
 * which has its own suite - `hooks/useDeferredRowAction.test.tsx` - covering the countdown
 * and Cancel machinery itself) are mocked at their module boundary; `CountryFormDialog` is
 * stubbed to a marker so this file asserts CountryList's OWN wiring - which country it opens
 * the modal with, and what it hands the deferred action - not the form's internals
 * (`CountryFormDialog` has no test file of its own yet; AC-1.9 covers its validation via the
 * shared `CountrySchema` directly).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const useCountries = vi.fn();
vi.mock('../hooks/useCountries', () => ({
  useCountries: (...args: unknown[]) => useCountries(...args),
}));

const run = vi.fn();
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run, targetId: null, isPending: false }),
  useRowPending: () => () => false,
}));

vi.mock('./CountryFormDialog', () => ({
  default: ({ open, country }: { open: boolean; country: { name: string } | null }) =>
    open ? (
      <div data-testid="country-form-dialog">
        {country ? `Editing ${country.name}` : 'Adding'}
      </div>
    ) : null,
}));

import CountryList from './CountryList';

const ROWS = [
  { id: 'c-my', code: 'MY', name: 'Malaysia', is_active: true, created_at: '', updated_at: '' },
  { id: 'c-sg', code: 'SG', name: 'Singapore', is_active: false, created_at: '', updated_at: '' },
];

function mockData(data = ROWS) {
  useCountries.mockReturnValue({
    data: { data, pagination: { total: data.length, page: 1 }, empty: data.length === 0 },
    isLoading: false,
    isPlaceholderData: false,
    isFetching: false,
    refetch: vi.fn(),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockData();
});

describe('CountryList', () => {
  it('lists the seeded countries', () => {
    render(<CountryList />);

    expect(screen.getByText('Malaysia')).toBeInTheDocument();
    expect(screen.getByText('Singapore')).toBeInTheDocument();
    expect(screen.getByText('MY')).toBeInTheDocument();
  });

  it('searches by typing into the list search box', async () => {
    render(<CountryList />);

    fireEvent.change(screen.getByPlaceholderText('Search countries...'), {
      target: { value: 'mala' },
    });

    await waitFor(() => {
      const lastCall = useCountries.mock.calls.at(-1)?.[0];
      expect(lastCall?.searchQuery).toBe('mala');
    });
  });

  it('opens the edit modal with the clicked row', () => {
    render(<CountryList />);

    fireEvent.click(screen.getByText('Singapore'));

    expect(screen.getByTestId('country-form-dialog')).toHaveTextContent('Editing Singapore');
  });

  it('opens the add modal from the Add Country button, with no country', () => {
    render(<CountryList />);

    fireEvent.click(screen.getByRole('button', { name: /add country/i }));

    expect(screen.getByTestId('country-form-dialog')).toHaveTextContent('Adding');
  });

  it('deletes with no confirm dialog - the button parks a deferred action directly', () => {
    render(<CountryList />);

    fireEvent.click(screen.getByRole('button', { name: 'Delete Singapore' }));

    expect(run).toHaveBeenCalledWith({ id: 'c-sg', subject: 'Singapore' });
    // The CRUD standard: never a confirm() / AlertDialog gate in front of it.
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('renders an empty state with a next-step Add action when there are no rows', () => {
    mockData([]);
    render(<CountryList />);

    expect(screen.getByText(/no countries yet/i)).toBeInTheDocument();
  });
});
