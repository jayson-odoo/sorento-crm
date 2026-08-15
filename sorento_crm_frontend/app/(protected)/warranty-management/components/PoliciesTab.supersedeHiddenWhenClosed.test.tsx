/**
 * `PoliciesTab` - Phase 3 review, AC-P26 finding 2 (grid row actions half).
 *
 * AC-P21 [BE] refuses Supersede outright whenever the incumbent already has an
 * `effective_to` - there is no date that can be entered to make it succeed.
 * The row actions render the Supersede icon button unconditionally, so a
 * closed policy still opens a live dialog with an enabled Publish button that
 * is guaranteed to 422.
 *
 * Ruling: when `effective_to` is set, the Supersede action is not rendered at
 * all (hidden, not disabled) - this repo's house rule forbids in-UI feature
 * explanations, and a closed policy already shows its own end date and
 * lifecycle badge. Both branches are asserted so this cannot pass by the
 * action simply never rendering for anyone.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
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
  hooks.useCreatePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useUpdatePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useSupersedePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useDeletePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
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

function rowFor(version: string): HTMLElement {
  const row = screen.getByText(version).closest('tr');
  if (!row) throw new Error(`No <tr> found for version "${version}"`);
  return row;
}

describe('PoliciesTab - AC-P21/AC-P26 finding 2: Supersede is not offered on an already-closed policy', () => {
  it('a CLOSED policy (effective_to set) does not render a Supersede action in its row', () => {
    mockList([policy({ id: 'pol-closed', version: 'v14', effective_to: '2025-12-31' })]);
    renderTab();

    expect(
      within(rowFor('v14')).queryByRole('button', { name: /Supersede policy/i }),
    ).not.toBeInTheDocument();
  });

  it('an OPEN ENDED policy (positive control) still renders a Supersede action in its row', () => {
    mockList([policy({ id: 'pol-open', version: 'v15', effective_to: null })]);
    renderTab();

    expect(
      within(rowFor('v15')).getByRole('button', { name: /Supersede policy/i }),
    ).toBeInTheDocument();
  });

  it('a mixed grid: the closed row hides it while the open row beside it still offers it', () => {
    mockList([
      policy({ id: 'pol-closed', version: 'v14', effective_to: '2025-12-31' }),
      policy({ id: 'pol-open', version: 'v16', effective_to: null }),
    ]);
    renderTab();

    expect(
      within(rowFor('v14')).queryByRole('button', { name: /Supersede policy/i }),
    ).not.toBeInTheDocument();
    expect(
      within(rowFor('v16')).getByRole('button', { name: /Supersede policy/i }),
    ).toBeInTheDocument();
  });
});
