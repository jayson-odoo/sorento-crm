/**
 * PORTAL-P4-REQUESTS S2 (P4-22, P4-23, P4-26): the Complaint list for a LIMITED user (holds `.view_own`,
 * not `.view`) and an unchanged staff user (control). Scaffolding copied from ComplaintsList.rowActions.test.tsx
 * and the S1 StockInquiriesList.requestScope.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
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
vi.mock('../../complaint-root-causes/hooks/useComplaintRootCauses', () => ({
  useComplaintRootCausesSelect: () => ({ data: [] }),
}));
vi.mock('../../complaint-resolutions/hooks/useComplaintResolutions', () => ({
  useComplaintResolutionsSelect: () => ({ data: [] }),
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

const LIMITED = ['complaint_management.complaints.view_own', 'complaint_management.complaints.add'];
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

describe('Complaint list, limited user', () => {
  it('shows Create Complaint (holds .add)', async () => {
    renderList(LIMITED);
    expect(await screen.findByText('CMP-0001')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Create Complaint/ }).length).toBeGreaterThan(0);
  });

  it('hides Create when .add is not held', async () => {
    renderList(['complaint_management.complaints.view_own']);
    expect(await screen.findByText('CMP-0001')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create Complaint/ })).toBeNull();
  });

  it('offers no bulk Delete after selecting a row', async () => {
    renderList(LIMITED);
    await screen.findByText('CMP-0001');
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Select row' })[0]);
    expect(screen.queryByRole('button', { name: /^Delete$/ })).toBeNull();
  });

  it('the row menu carries neither Delete nor Download PDF', async () => {
    renderList(LIMITED);
    await screen.findByText('CMP-0001');
    const trigger = screen.queryByRole('button', { name: 'complaint actions' });
    if (trigger) {
      trigger.focus();
      fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
      const menu = await screen.findByRole('menu');
      const labels = within(menu).queryAllByRole('menuitem').map((i) => (i.textContent ?? '').trim());
      expect(labels).not.toContain('Delete');
      expect(labels).not.toContain('Download PDF');
    }
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Download PDF' })).toBeNull();
  });

  it('the status filter offers Draft', async () => {
    renderList(LIMITED, 'submitted'); // the row itself must not be the thing that says "Draft"
    await screen.findByText('CMP-0001');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /^filters/i }));
    await user.click(await screen.findByText('All statuses'));
    expect(await screen.findByText(APPEALED_LABEL)).toBeInTheDocument(); // the option list is open (#1952: resubmitted reads Appealed)
    expect(screen.getByText('Draft')).toBeInTheDocument();
  });
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
  it.each([['limited', LIMITED], ['staff', STAFF]])('%s: each header is a sort button', async (_n, slugs) => {
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
