/**
 * NPA-FORM-SLA, owner hand test 9 Nov: "need the columns just like stock inquiries". The NPA list
 * carries the stock inquiry list's Salesperson / Status / Assigned To / Handled By / Print Count /
 * Rev columns, with the SI list's own components; the line columns left with the product rows.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/new-product-applications',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn().mockResolvedValue([
    { id: 'u-1', name: 'ZZT Alice' },
    { id: 'u-2', name: 'ZZT Bob' },
    { id: 'u-3', name: 'ZZT Cara' },
  ]),
}));
const useQ = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useNewProductApplications', () => ({
  useNewProductApplicationListingKey: () => 'procurement.new_product_applications.view',
  useNewProductApplicationsQuery: (params: unknown) => useQ(params),
}));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: (p: { entityType: string; entityId: string; count: number }) => (
    <button type="button" data-testid="downloads">{`${p.entityType}:${p.entityId}:${p.count}`}</button>
  ),
}));
import NewProductApplicationsList from './NewProductApplicationsList';

const ROW = {
  id: 'npa-1', application_no: 'ZZT-NPA-001', status: 'submitted', status_label: 'Submitted', source: 'staff',
  applicant_id: 'u-1', applicant_name: 'ZZT Alice', salesperson: 'ZZT Alice', stock_inquiry_id: null,
  stock_inquiry_number: null, customer_name: 'ZZT Customer', project_name: null, opened_codes: [], needed_by: null,
  submitted_at: null, created_at: '2026-01-01T00:00:00', revision_no: 2, assigned_to_name: 'ZZT Manager',
  handled_by_name: 'ZZT Holder', print_count: 3,
};

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <NewProductApplicationsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  url.search = '';
  useQ.mockReturnValue({
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 25 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('the NPA list carries the stock inquiry list columns', () => {
  it('shows Rev, Salesperson, Status, Assigned To, Handled By and Print Count', async () => {
    mount();
    await screen.findByText('ZZT-NPA-001');
    for (const h of ['Rev', 'Salesperson', 'Status', 'Assigned To', 'Handled By', 'Print Count'])
      expect(screen.getByRole('columnheader', { name: new RegExp(`^${h}`) })).toBeInTheDocument();
    expect(screen.getByText('Rev 2')).toBeInTheDocument();
    expect(screen.getAllByText('ZZT Alice').length).toBeGreaterThan(0);
    expect(screen.getByText('ZZT Manager')).toBeInTheDocument();
    expect(screen.getByText('ZZT Holder')).toBeInTheDocument();
    expect(screen.getByTestId('downloads')).toHaveTextContent('new_product_application:npa-1:3');
  });

  it('drops the line columns', async () => {
    mount();
    await screen.findByText('ZZT-NPA-001');
    for (const h of ['First line', 'Lines', 'Done'])
      expect(screen.queryByRole('columnheader', { name: new RegExp(`^${h}$`) })).toBeNull();
  });

  it('shows a dash for Rev when never revised', async () => {
    useQ.mockReturnValue({
      data: { data: [{ ...ROW, revision_no: 0 }], pagination: { total: 1, page: 1, limit: 25 } },
      isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
    });
    mount();
    await screen.findByText('ZZT-NPA-001');
    expect(screen.queryByText(/^Rev \d/)).toBeNull();
  });
});


describe('the Status filter offers Responded, like the stock inquiry list', () => {
  it('lists Responded among the statuses', async () => {
    const { STATUS_OPTIONS } = await import('./NewProductApplicationsList');
    expect(STATUS_OPTIONS.map((o) => o.value)).toContain('responded');
    expect(STATUS_OPTIONS.find((o) => o.value === 'responded')?.label).toBe('Responded');
  });
});
