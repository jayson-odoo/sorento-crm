/**
 * AFTER-SALES-P1 red tests (UAC D2): the Service Jobs list.
 *
 * Contract: `./ServiceJobsList` default export, no props. It reads `useServiceJobsList(params)`
 * from `../hooks/useServiceJobs` -> { data: { data: ServiceJob[]; pagination }, isLoading, isFetching, refetch }
 * and the job's moves from `useServiceJobActions()`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/complaint-management/service-jobs',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));

const rows = vi.fn();
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobs', () => ({
  useServiceJobsList: () => rows(),
  useServiceJobActions: () => ({ confirm: noop, assign: noop, transition: noop }),
  useTechniciansSelect: () => ({ data: [] }),
}));

import ServiceJobsList from './ServiceJobsList';

const JOB = {
  id: 'j-1', job_number: 'SV26/11-0001', complaint_id: 'c-1', complaint_number: 'CMP-0001',
  customer_name: 'Ms Lim Trading', city: 'Subang Jaya', status: 'confirmed', status_label: 'Confirmed',
  technician_id: 't-1', technician_name: 'Ali', scheduled_from: '2026-11-20T02:00:00', scheduled_to: null,
};

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <ServiceJobsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  rows.mockReturnValue({
    data: { data: [JOB], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false, isFetching: false, refetch: vi.fn(),
  });
});

describe('ServiceJobsList (D2)', () => {
  it('renders one line per job with the seven columns', async () => {
    renderList();
    expect(await screen.findByText('SV26/11-0001')).toBeInTheDocument();
    for (const t of ['CMP-0001', 'Ms Lim Trading', 'Subang Jaya', 'Ali']) {
      expect(screen.getByText(t)).toBeInTheDocument();
    }
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
    expect(screen.getByText(/20\/11\/2026/)).toBeInTheDocument();
  });

  it('has no Create button (a job is raised from its complaint)', async () => {
    renderList();
    await screen.findByText('SV26/11-0001');
    expect(screen.queryByRole('button', { name: /create|new|add|raise/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /create|new|add|raise/i })).toBeNull();
  });

  it('has no icon buttons on rows', async () => {
    renderList();
    await screen.findByText('SV26/11-0001');
    const row = screen.getByText('SV26/11-0001').closest('tr')!;
    expect(within(row).queryAllByRole('button')).toHaveLength(0);
  });

  it('opens the job page when the row is clicked', async () => {
    renderList();
    const cell = await screen.findByText('SV26/11-0001');
    const link = cell.closest('a');
    if (link) {
      expect((link.getAttribute('href') ?? '').split('?')[0]).toBe('/complaint-management/service-jobs/j-1');
    } else {
      fireEvent.click(cell);
      expect(String(push.mock.calls[0]?.[0]).split('?')[0]).toBe('/complaint-management/service-jobs/j-1');
    }
  });

  it('right-click offers Open complaint and the moves the status allows', async () => {
    renderList();
    const cell = await screen.findByText('SV26/11-0001');
    fireEvent.contextMenu(cell);
    const menu = await screen.findByRole('menu');
    const labels = within(menu).getAllByRole('menuitem').map((i) => (i.textContent || '').trim());
    expect(labels).toContain('Open complaint');
    // confirmed with a technician: main step On the way, plus the secondary moves
    expect(labels).toEqual(expect.arrayContaining(['On the way', 'Customer rejected the visit', 'Cancel']));
    expect(labels).not.toContain('Verify');
  });

  it('shows an empty state with no rows', async () => {
    rows.mockReturnValue({
      data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
      isLoading: false, isFetching: false, refetch: vi.fn(),
    });
    renderList();
    expect(await screen.findByText(/no service jobs/i)).toBeInTheDocument();
  });
});
