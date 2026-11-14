/**
 * AFTER-SALES-P2 red tests (UAC F2): the Warranty column and filter on the Service Jobs list.
 *
 * Extends `./ServiceJobsList` (P1). Rows now carry `warranty_summary`:
 * 'covered' | 'partly_covered' | 'not_covered' | 'unknown' | null. The column header is "Warranty", last in the
 * grid, sortable (server sort key `warranty_summary`), and `useServiceJobsList` receives
 * `warranty_summary: string[]` from a multi-select filter labelled "Warranty".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/service-jobs',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));

const useList = vi.fn();
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobs', () => ({
  useServiceJobsList: (...a: unknown[]) => useList(...a),
  useServiceJobActions: () => ({ confirm: noop, assign: noop, transition: noop }),
  useTechniciansSelect: () => ({ data: [] }),
  useServiceJobMutations: () => ({ create: noop, update: noop }),
}));

import ServiceJobsList from './ServiceJobsList';

const job = (n: number, summary: string | null) => ({
  id: `j-${n}`, job_number: `SV26/11-000${n}`, complaint_id: null, complaint_number: null, customer_name: `Customer ${n}`,
  city: 'Ipoh', status: 'proposed', status_label: 'Proposed', technician_id: null, technician_name: null,
  scheduled_from: null, scheduled_to: null, warranty_summary: summary,
});
const ROWS = [job(1, 'covered'), job(2, 'partly_covered'), job(3, 'not_covered'), job(4, 'unknown'), job(5, null)];

beforeEach(() => {
  vi.clearAllMocks();
  useList.mockReturnValue({
    data: { data: ROWS, pagination: { total: 5, page: 1, limit: 50 } },
    isLoading: false, isFetching: false, refetch: vi.fn(),
  });
});

function renderList() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ServiceJobsList />
    </QueryClientProvider>,
  );
}
const pillIn = (n: number) => within(screen.getByText(`SV26/11-000${n}`).closest('tr')!).queryByText(/Covered|Partly covered|Not covered|Unknown/);

describe('ServiceJobsList warranty column', () => {
  it('Warranty is the last column header', async () => {
    renderList();
    await screen.findByText('SV26/11-0001');
    const heads = screen.getAllByRole('columnheader').map((h) => (h.textContent || '').trim()).filter(Boolean);
    expect(heads.at(-1)).toBe('Warranty');
  });

  it('shows a pill per job: Covered, Partly covered, Not covered, Unknown', async () => {
    renderList();
    await screen.findByText('SV26/11-0001');
    expect(pillIn(1)?.textContent).toBe('Covered');
    expect(pillIn(2)?.textContent).toBe('Partly covered');
    expect(pillIn(3)?.textContent).toBe('Not covered');
    expect(pillIn(4)?.textContent).toBe('Unknown');
    for (const n of [1, 2, 3, 4]) expect(pillIn(n)!.closest('[data-slot="badge"]')).not.toBeNull();
  });

  it('a job without products shows a dash, not a pill', async () => {
    renderList();
    await screen.findByText('SV26/11-0005');
    expect(pillIn(5)).toBeNull();
    const row = screen.getByText('SV26/11-0005').closest('tr')!;
    const lastCell = Array.from(row.querySelectorAll('td')).at(-1)!;
    expect(lastCell.textContent!.trim()).toBe('-');
  });

  it('is a server-sortable column and the list starts with an empty warranty filter', async () => {
    renderList();
    await screen.findByText('SV26/11-0001');
    const th = screen.getByText('Warranty', { selector: 'th *, th' }).closest('th')!;
    expect(th.querySelector('svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down')).not.toBeNull();
    expect(useList).toHaveBeenCalledWith(expect.objectContaining({ warranty_summary: [] }));
  });
});
