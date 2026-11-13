/** R6-2: "Open related complaint" in the row right-click menu and the job page gear, for a viewer of complaints. */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within, waitFor, cleanup } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/after-sales/service-jobs',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: (slug: string) => granted.has(slug) }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => null, RecordNavigation: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => null }));

const JOB = {
  id: 'j-1', job_number: 'SV26/11-0001', complaint_id: 'c-1', complaint_number: 'CMP-0001', customer_name: 'Ms Lim',
  contact_name: null, contact_phone: null, city: 'Ipoh', problem: null, status: 'proposed', status_label: 'Proposed',
  technician_id: null, technician_name: null, scheduled_from: null, scheduled_to: null, customer_agreed_by: null,
};
let current: Record<string, unknown> = JOB;
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobs', () => ({
  useServiceJobsList: () => ({
    data: { data: [current], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false, isFetching: false, refetch: vi.fn(),
  }),
  useServiceJob: () => ({ data: current, isLoading: false }),
  useServiceJobActions: () => ({ confirm: noop, assign: noop, transition: noop }),
  useServiceJobMutations: () => ({ create: noop, update: noop }),
  useTechniciansSelect: () => ({ data: [] }),
}));

import ServiceJobsList from './ServiceJobsList';
import ServiceJobDetail from './ServiceJobDetail';

const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

async function rowMenu() {
  render(<QueryClientProvider client={client()}><ServiceJobsList /></QueryClientProvider>);
  fireEvent.contextMenu(await screen.findByText('SV26/11-0001'));
  const menu = await screen.findByRole('menu');
  return within(menu).getAllByRole('menuitem').map((i) => (i.textContent || '').trim());
}

async function gearItems() {
  render(<QueryClientProvider client={client()}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
  const gear = screen.getByRole('button', { name: 'Service job actions' });
  fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
  fireEvent.click(gear);
  await waitFor(() => expect(gear.getAttribute('aria-expanded')).toBe('true'));
  return screen.findAllByRole('menuitem');
}

beforeEach(() => {
  cleanup();
  current = JOB;
  granted = new Set(['after_sales.service_jobs.dispatch', 'complaint_management.complaints.view']);
});

describe('Open related complaint', () => {
  it('is in the row right-click menu', async () => {
    expect(await rowMenu()).toContain('Open related complaint');
  });

  it('is in the job page gear, linking to the complaint', async () => {
    const items = await gearItems();
    const item = items.find((i) => (i.textContent || '').trim() === 'Open related complaint');
    expect(item).toBeTruthy();
    expect(item!.closest('a') ?? item!.querySelector('a')).toHaveAttribute('href', '/complaint-management/complaints/c-1');
  });

  it('is absent without complaint view', async () => {
    granted = new Set(['after_sales.service_jobs.dispatch']);
    expect(await rowMenu()).not.toContain('Open related complaint');
  });

  it('is absent when the job has no related complaint', async () => {
    current = { ...JOB, complaint_id: null, complaint_number: null };
    expect(await rowMenu()).not.toContain('Open related complaint');
  });
});
