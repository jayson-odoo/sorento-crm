/**
 * SpecVerificationList — the worklist screen (PR 3).
 *
 * The service layer is mocked; the real hooks (`useSpecVerification`) and the real
 * shared `DataGrid` run, so the cache-patch behaviour (AC-D.22: acted row updates in
 * place, no re-sort) is exercised for real, not reimplemented in the test.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  push: vi.fn(),
  replace: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  usePathname: () => '/master-data-management/spec-verification',
  useSearchParams: () => nav.params,
}));

const getSpecVerificationWorklist = vi.fn();
const getSpecVerificationClassOptions = vi.fn();
const verifySpecBulk = vi.fn();
const unverifySpecBulk = vi.fn();

vi.mock('../services/specVerificationService', () => ({
  getSpecVerificationWorklist: (...a: unknown[]) => getSpecVerificationWorklist(...a),
  getSpecVerificationClassOptions: (...a: unknown[]) => getSpecVerificationClassOptions(...a),
  verifySpecBulk: (...a: unknown[]) => verifySpecBulk(...a),
  unverifySpecBulk: (...a: unknown[]) => unverifySpecBulk(...a),
}));

import SpecVerificationList from './SpecVerificationList';
import type { SpecVerificationRow, VerificationState } from '../types/specVerification.types';

function row(
  code: string,
  state: VerificationState,
  overrides: Partial<SpecVerificationRow> = {},
): SpecVerificationRow {
  return {
    product_id: `id-${code}`,
    product_code: code,
    product_name: `Product ${code}`,
    class_label: 'Kitchen Sink',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 3, applicable: 8 },
    open_exceptions: 0,
    values_hash: `hash-${code}`,
    verification: {
      state,
      verified_by_name: state === 'verified' ? 'Jay Odoo' : null,
      verified_at: state === 'verified' ? '2026-08-01T09:00:00' : null,
      invalidated_at: null,
      invalidated_reason: null,
      invalidated_by_name: null,
      invalidated_diff: null,
    },
    ...overrides,
  };
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SpecVerificationList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.params = new URLSearchParams();
  getSpecVerificationClassOptions.mockResolvedValue(['Kitchen Sink', 'Bath Basin']);
});

afterEach(() => cleanup());

describe('loading state', () => {
  it('shows the progress-line skeleton and a disabled search box while the worklist loads', () => {
    getSpecVerificationWorklist.mockReturnValue(new Promise(() => {})); // never resolves
    renderList();

    expect(screen.queryByTestId('verification-progress')?.textContent ?? '').not.toContain(
      'Verified',
    );
    expect(screen.getByPlaceholderText('Search code or name')).toBeDisabled();
  });
});

describe('error state', () => {
  it('renders the failure message with a Retry action', async () => {
    getSpecVerificationWorklist.mockRejectedValue(new Error('Failed to load the verification worklist'));
    renderList();

    await waitFor(() =>
      expect(screen.getByText('Failed to load the verification worklist.')).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('empty state', () => {
  it('offers "Go to products" when no filters are active', async () => {
    getSpecVerificationWorklist.mockResolvedValue({
      data: [],
      pagination: { total: 0, page: 1, limit: 25 },
      summary: { total: 0, verified: 0, needs_reverify: 0, unverified: 0 },
    });
    renderList();

    await waitFor(() => expect(screen.getByText('Nothing to review here.')).toBeInTheDocument());
    expect(
      screen.getByText('No product code is waiting for verification.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to products' })).toBeInTheDocument();
  });

  it('offers "Clear filters" instead when a filter is active from the URL', async () => {
    nav.params = new URLSearchParams({ query: 'nonexistent-code' });
    getSpecVerificationWorklist.mockResolvedValue({
      data: [],
      pagination: { total: 0, page: 1, limit: 25 },
      summary: { total: 0, verified: 0, needs_reverify: 0, unverified: 0 },
    });
    renderList();

    await waitFor(() =>
      expect(screen.getByText('No product code matches these filters.')).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });
});

describe('data state', () => {
  const ROWS = [
    row('WC100', 'needs_reverify'),
    row('WC200', 'unverified'),
    row('WC300', 'verified'),
  ];

  function mockWorklist(data = ROWS) {
    getSpecVerificationWorklist.mockResolvedValue({
      data,
      pagination: { total: data.length, page: 1, limit: 25 },
      summary: { total: 4812, verified: 3000, needs_reverify: 1000, unverified: 812 },
    });
  }

  it('renders all three verification pills and the progress line', async () => {
    mockWorklist();
    renderList();

    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());
    expect(screen.getByText('Needs re-verify')).toBeInTheDocument();
    expect(screen.getByText('Unverified')).toBeInTheDocument();
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByTestId('verification-progress').textContent).toContain(
      'Verified 3,000 of 4,812 live codes',
    );
  });

  it('the needs-re-verify tooltip reads the diff entries as values, never [object Object]', async () => {
    // The wire shape of `invalidated_diff.changed`: each side is the stored ENTRY
    // (`{ value, unit? }`), or null when the key was absent on that side.
    mockWorklist([
      row('WC100', 'needs_reverify', {
        verification: {
          state: 'needs_reverify',
          verified_by_name: 'Jay Odoo',
          verified_at: '2026-08-01T09:00:00',
          invalidated_at: '2026-08-10T10:00:00',
          invalidated_reason: 'values_changed',
          invalidated_by_name: null,
          invalidated_diff: {
            changed: [
              { spec_key: 'material', was: { value: 'glass' }, now: { value: 'ceramic' } },
              { spec_key: 'dim_height', was: { value: 770, unit: 'mm' }, now: null },
            ],
          },
        },
      }),
    ]);
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const title = screen.getByText('Needs re-verify').getAttribute('title') ?? '';
    expect(title).not.toContain('[object Object]');
    expect(title).toContain('2 changed');
    expect(title).toContain('Material: Glass to Ceramic');
    expect(title).toContain('Height: 770 mm to nothing');
  });

  it('the per-row action follows the row state: Verify on unverified/needs_reverify, Unverify on verified', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const rowWC100 = screen.getByText('WC100').closest('tr') as HTMLElement;
    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    const rowWC300 = screen.getByText('WC300').closest('tr') as HTMLElement;

    expect(within(rowWC100).getByRole('button', { name: 'Verify' })).toBeInTheDocument();
    expect(within(rowWC200).getByRole('button', { name: 'Verify' })).toBeInTheDocument();
    expect(within(rowWC300).getByRole('button', { name: 'Unverify' })).toBeInTheDocument();
  });

  it('clicking a row navigates to the product Specifications tab, not a new detail route', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    fireEvent.click(screen.getByText('WC100'));

    expect(nav.push).toHaveBeenCalledWith(
      '/master-data-management/products/id-WC100?tab=specifications',
    );
  });

  it('the row action does not itself navigate (stops propagation)', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC200')).toBeInTheDocument());
    verifySpecBulk.mockResolvedValue({
      results: [{ product_code: 'WC200', outcome: 'verified', verification: row('WC200', 'verified').verification, values_hash: 'hash-WC200-v2' }],
      counts: { verified: 1, skipped: 0 },
    });

    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC200).getByRole('button', { name: 'Verify' }));

    await waitFor(() => expect(verifySpecBulk).toHaveBeenCalled());
    expect(nav.push).not.toHaveBeenCalled();
  });

  it('a per-row Verify is a bulk of one: it calls verify-bulk with exactly that code and its rendered hash', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC200')).toBeInTheDocument());
    verifySpecBulk.mockResolvedValue({
      results: [{ product_code: 'WC200', outcome: 'verified', verification: row('WC200', 'verified').verification, values_hash: 'hash-WC200-v2' }],
      counts: { verified: 1, skipped: 0 },
    });

    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC200).getByRole('button', { name: 'Verify' }));

    await waitFor(() =>
      expect(verifySpecBulk).toHaveBeenCalledWith([{ product_code: 'WC200', values_hash: 'hash-WC200' }]),
    );
    // No confirmation dialog for the per-row action.
    expect(screen.queryByText('Confirm verify')).not.toBeInTheDocument();
  });

  it('select-all is page-scoped: no cross-page "select all matching" banner ever renders', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }));

    expect(screen.getByText('3 selected')).toBeInTheDocument();
    expect(screen.queryByText(/select all .* records/i)).not.toBeInTheDocument();
  });

  it('selecting rows shows both bulk actions in the strip', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const rowWC100 = screen.getByText('WC100').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC100).getByRole('checkbox', { name: 'Select row' }));

    expect(screen.getByRole('button', { name: /Verify selected/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Unverify selected/ })).toBeInTheDocument();
  });

  it('confirmation copy states the selected count', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }));
    fireEvent.click(screen.getByRole('button', { name: /Verify selected/ }));

    await waitFor(() => expect(screen.getByText('Confirm verify')).toBeInTheDocument());
    expect(screen.getByText(/Verify 3 product code\(s\)\?/)).toBeInTheDocument();
  });

  it('a mixed bulk verify: acted row flips pill in place, skipped row (open exceptions) stays selected', async () => {
    const rowsWithException = [
      row('WC200', 'unverified'),
      row('WC400', 'unverified', { open_exceptions: 1 }),
    ];
    mockWorklist(rowsWithException);
    renderList();
    await waitFor(() => expect(screen.getByText('WC200')).toBeInTheDocument());

    verifySpecBulk.mockResolvedValue({
      results: [
        {
          product_code: 'WC200',
          outcome: 'verified',
          verification: row('WC200', 'verified').verification,
          values_hash: 'hash-WC200-v2',
        },
        { product_code: 'WC400', outcome: 'exceptions_open' },
      ],
      counts: { verified: 1, skipped: 1 },
    });

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }));
    fireEvent.click(screen.getByRole('button', { name: /Verify selected/ }));
    await waitFor(() => expect(screen.getByText('Confirm verify')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => expect(verifySpecBulk).toHaveBeenCalled());

    // Acted row flips to Unverify (now verified), in the SAME table position.
    await waitFor(() => {
      const codes = screen.getAllByRole('cell').length; // sanity: table still rendered
      expect(codes).toBeGreaterThan(0);
    });
    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    const rowWC400 = screen.getByText('WC400').closest('tr') as HTMLElement;
    await waitFor(() =>
      expect(within(rowWC200).getByRole('button', { name: 'Unverify' })).toBeInTheDocument(),
    );

    // Row order in the DOM is unchanged: WC200 still precedes WC400.
    const allRows = screen.getAllByText(/^WC(200|400)$/).map((el) => el.textContent);
    expect(allRows).toEqual(['WC200', 'WC400']);

    // The skipped row's own checkbox is still checked.
    expect(within(rowWC400).getByRole('checkbox', { name: 'Select row' })).toBeChecked();
    // The acted row's checkbox was released.
    expect(within(rowWC200).getByRole('checkbox', { name: 'Select row' })).not.toBeChecked();
  });
});
