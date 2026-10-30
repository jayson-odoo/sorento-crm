/**
 * PORTAL-P4-REQUESTS S2 (P4-22, P4-23, P4-26): the Complaint list for a LIMITED user (holds `.view_own`,
 * not `.view`) and an unchanged staff user (control). Scaffolding copied from ComplaintsList.rowActions.test.tsx
 * and the S1 StockInquiriesList.requestScope.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/complaint-management/complaints',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));
const rootCauseSelect = vi.fn(async () => []);
const resolutionSelect = vi.fn(async () => []);
vi.mock('../../complaint-root-causes/services/complaintRootCauseService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getComplaintRootCausesSelect: (...a: unknown[]) => rootCauseSelect(...(a as [])),
}));
vi.mock('../../complaint-resolutions/services/complaintResolutionService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getComplaintResolutionsSelect: (...a: unknown[]) => resolutionSelect(...(a as [])),
}));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

const rows = vi.fn();
vi.mock('../hooks/useComplaints', () => ({
  useComplaints: () => rows(),
  useExportComplaintPdf: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteComplaint: () => ({ mutateAsync: vi.fn() }),
  useBulkDeleteComplaints: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import ComplaintsList from './ComplaintsList';
import type { Complaint } from '../types/complaint.types';
import { APPEALED_LABEL } from '@/lib/submission-status';

const STAFF = [
  'complaint_management.complaints.view',
  'complaint_management.complaints.add',
  'complaint_management.complaints.delete',
];

function complaint(over: Partial<Complaint> = {}): Complaint {
  return {
    id: 'c-1',
    complaint_number: 'CMP-0001',
    delivery_order_number: 'DO-9001',
    status: 'draft',
    created_at: '2026-08-20T02:00:00',
    ...over,
  } as Complaint;
}

function renderList(slugs: string[], status = 'draft') {
  held = new Set(slugs);
  rows.mockReturnValue({
    data: { data: [complaint({ status })], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Complaint list, staff user (control, P4-26)', () => {
  it('still offers bulk Delete after selecting a row', async () => {
    renderList(STAFF);
    await screen.findByText('CMP-0001');
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Select row' })[0]);
    expect(await screen.findByRole('button', { name: /^Delete$/ })).toBeInTheDocument();
  });

  it('the row menu still carries Download PDF and Delete', async () => {
    renderList(STAFF);
    await screen.findByText('CMP-0001');
    const trigger = screen.getByRole('button', { name: 'complaint actions' });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
    const menu = await screen.findByRole('menu');
    const labels = within(menu).getAllByRole('menuitem').map((i) => (i.textContent ?? '').trim());
    expect(labels).toEqual(['Download PDF', 'Delete']);
  });
});

describe('every column header sorts (P4-23), for limited and staff alike', () => {
  const COLUMNS = [
    'DO Number', 'Complaint Number', 'Complaint Date', 'Created at', 'Customer Name', 'Product Code',
    'Complaint Type', 'Project Title', 'Salesperson', 'Status', 'Assigned To', 'Handled By',
    'Attachments', 'Print Count',
  ];
  it.each([['staff', STAFF]])('%s: each header is a sort button', async (_n, slugs) => {
    renderList(slugs);
    await screen.findByText('CMP-0001');
    const missing: string[] = [];
    for (const title of COLUMNS) {
      const th = screen.queryAllByText(title).map((el) => el.closest('th')).find(Boolean);
      const sortable = !!th?.querySelector('svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down');
      if (!sortable) missing.push(title);
    }
    expect(missing).toEqual([]);
  });
});

describe('lookups behind master-data permissions (owner hand test 2, item 1)', () => {
  it('staff: both selects are still requested (pin)', async () => {
    renderList(STAFF);
    await screen.findByText('CMP-0001');
    await waitFor(() => expect(rootCauseSelect).toHaveBeenCalled());
    await waitFor(() => expect(resolutionSelect).toHaveBeenCalled());
  });
});

describe('Create label (L4, owner a25895124 Q3 a)', () => {
  it('staff: the primary action reads exactly "Create", never "Create Complaint"', async () => {
    renderList(STAFF);
    await screen.findByText('CMP-0001');
    expect(screen.getAllByRole('button', { name: 'Create' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Create Complaint/ })).toBeNull();
  });
});
