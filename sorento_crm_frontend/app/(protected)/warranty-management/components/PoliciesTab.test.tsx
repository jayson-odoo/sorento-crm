/**
 * `PoliciesTab` — S7b Phase 2c gate.
 *
 * Group 1 item 3, policy half (AC-P13): deleting a Policy cascades its Terms,
 * so the confirmation names how many Terms go with it. Both branches (has
 * terms / has none) are asserted.
 *
 * Group 2 item 11: the grid must not offer a sort the backend silently
 * ignores. The backend's sort whitelist is exactly
 * `{version, effective_from, effective_to, created_at}`. `term_count` is
 * currently sortable and the click does nothing — EXPECTED TO FAIL.
 * `lifecycle` and `source_document` are already (correctly) `enableSorting:
 * false` and serve as the negative control that proves the detector works.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/warranty-management',
}));

vi.mock('@/app/providers/CompanyProvider', () => ({
  useCompany: () => ({ activeCompany: { id: 'company-1', name: 'Sorento' } }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const hooks = vi.hoisted(() => ({
  usePolicies: vi.fn(),
  useCreatePolicy: vi.fn(),
  useUpdatePolicy: vi.fn(),
  useSupersedePolicy: vi.fn(),
  useDeletePolicy: vi.fn(),
}));
vi.mock('../hooks/useWarrantyConfig', () => hooks);

import { PoliciesTab } from './PoliciesTab';
import type { WarrantyPolicyRow } from '../types/warranty-config.types';

function policy(over: Partial<WarrantyPolicyRow>): WarrantyPolicyRow {
  return {
    id: 'pol-1',
    version: 'v15',
    effective_from: '2000-01-01',
    effective_to: null,
    policy_text: null,
    source_attachment_name: null,
    term_count: 0,
    created_at: '2000-01-01T00:00:00',
    updated_at: null,
    ...over,
  };
}

const deleteMutate = vi.fn().mockResolvedValue(undefined);

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PoliciesTab />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(hooks).forEach((f) => f.mockReset());
  deleteMutate.mockClear();
  hooks.useCreatePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useUpdatePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useSupersedePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useDeletePolicy.mockReturnValue({ mutateAsync: deleteMutate, isPending: false });
});

function mockList(rows: WarrantyPolicyRow[]) {
  hooks.usePolicies.mockReturnValue({
    data: { data: rows, pagination: { total: rows.length, page: 1, limit: 10 }, empty: rows.length === 0 },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
  });
}

describe('PoliciesTab — AC-P13: deleting a Policy names how many Terms cascade with it', () => {
  it('a Policy with terms names the count and says they go with it', async () => {
    mockList([policy({ id: 'pol-terms', version: 'v15', term_count: 4 })]);
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: /Delete policy/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('4')).toBeInTheDocument();
    expect(within(dialog).getByText(/terms/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/published under it/i)).toBeInTheDocument();
  });

  it('a Policy with no terms states plainly that it has none', async () => {
    const clean = policy({ id: 'pol-clean', version: 'v16', term_count: 0 });
    mockList([clean]);
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: /Delete policy/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/It has no terms under it/i)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: /^Delete$/i }));
    await vi.waitFor(() => expect(deleteMutate).toHaveBeenCalledWith('pol-clean'));
  });
});

describe('PoliciesTab — sort whitelist: no column offers a sort the backend silently ignores', () => {
  it('Version, Effective from and Effective to (the whitelist) render as clickable sort buttons', () => {
    mockList([policy({})]);
    renderTab();

    for (const label of ['Version', 'Effective from', 'Effective to']) {
      expect(headerHasSortAffordance(label)).toBe(true);
    }
  });

  it('Terms is NOT in the backend sort whitelist and must not render as a sort button', () => {
    mockList([policy({})]);
    renderTab();

    expect(headerHasSortAffordance('Terms')).toBe(false);
  });

  it('Status and Source document (already correctly excluded) stay excluded — the negative control', () => {
    mockList([policy({})]);
    renderTab();

    expect(headerHasSortAffordance('Status')).toBe(false);
    expect(headerHasSortAffordance('Source document')).toBe(false);
  });
});

/**
 * Every `<th>` in this grid renders as a `<button>` regardless of
 * sortability (column drag/resize wraps it too) — so "is it inside a
 * button" is not a reliable signal. `DataGridColumnHeader` only renders the
 * up/down chevron sort icon when `column.getCanSort()` is true, so that icon
 * is the real tell.
 */
function headerHasSortAffordance(label: string): boolean {
  const th = screen.getByText(label).closest('th');
  if (!th) throw new Error(`No <th> found for column header "${label}"`);
  return !!th.querySelector(
    'svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down',
  );
}
