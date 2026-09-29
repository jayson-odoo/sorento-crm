/**
 * Customer Branches list (#1356): read only, the AutoCount branch table.
 *
 * Pinned: the stored columns render; a matched customer links to its detail page; an AccNo with
 * no CRM customer reads "Not in CRM"; no id is shown; no Add / Import / Delete offer exists; an
 * empty table shows the empty state.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Branch } from '../types/branch.types';

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
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/order-management/branches',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

const ROWS: Branch[] = [
  {
    id: 'b1-uuid-0000',
    source_book: 'SRT',
    acc_no: '300-K0012',
    branch_code: 'KL01',
    branch_name: 'Kepong Showroom',
    last_synced_at: '2026-09-29T06:00:00',
    customer_id: 'cust-uuid-1',
    customer_name: 'Kedai Elektrik Maju',
  },
  {
    id: 'b2-uuid-0000',
    source_book: 'SRT',
    acc_no: '300-S0391',
    branch_code: 'HQ',
    branch_name: 'Head Office',
    last_synced_at: '2026-09-28T06:00:00',
    customer_id: null,
    customer_name: null,
  },
];

const getBranches = vi.fn();
vi.mock('../services/branchService', () => ({
  getBranches: (...args: unknown[]) => getBranches(...args),
  getBranchBooks: () => Promise.resolve(['SRT']),
}));

import BranchesList from './BranchesList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <BranchesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getBranches.mockReset();
});

describe('BranchesList', () => {
  it('renders the stored columns, newest sync first by default', async () => {
    getBranches.mockResolvedValue({ data: ROWS, pagination: { page: 1, limit: 50, total: 2 } });
    renderList();
    await waitFor(() => expect(screen.getByText('Kepong Showroom')).toBeInTheDocument());
    for (const header of ['Customer Code', 'Customer Name', 'Branch Code', 'Branch Name', 'Book', 'Last Synced']) {
      expect(screen.getAllByText(header).length).toBeGreaterThan(0);
    }
    expect(screen.getByText('KL01')).toBeInTheDocument();
    expect(screen.getByText('300-K0012')).toBeInTheDocument();
    expect(getBranches.mock.calls[0][0].sorting).toEqual([{ id: 'last_synced_at', desc: true }]);
  });

  it('links a matched customer and marks an unmatched AccNo, never showing an id', async () => {
    getBranches.mockResolvedValue({ data: ROWS, pagination: { page: 1, limit: 50, total: 2 } });
    const { container } = renderList();
    await waitFor(() => expect(screen.getByText('Kedai Elektrik Maju')).toBeInTheDocument());
    expect(screen.getByText('Kedai Elektrik Maju').closest('a')?.getAttribute('href')).toBe(
      '/order-management/customers/cust-uuid-1',
    );
    const hq = screen.getByText('Head Office').closest('tr') as HTMLElement;
    expect(hq.textContent).toContain('Not in CRM');
    expect(container.textContent).not.toContain('uuid');
  });

  it('offers no Add, Import or Delete', async () => {
    getBranches.mockResolvedValue({ data: ROWS, pagination: { page: 1, limit: 50, total: 2 } });
    renderList();
    await waitFor(() => expect(screen.getByText('Kepong Showroom')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /add|create|import|delete/i })).toBeNull();
  });

  it('shows the empty state when there are no branches', async () => {
    getBranches.mockResolvedValue({ data: [], pagination: { page: 1, limit: 50, total: 0 } });
    renderList();
    await waitFor(() => expect(screen.getByText('No branches yet')).toBeInTheDocument());
  });
});
