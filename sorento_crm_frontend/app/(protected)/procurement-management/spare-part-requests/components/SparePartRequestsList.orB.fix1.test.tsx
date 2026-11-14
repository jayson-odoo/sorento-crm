/**
 * SPARE-PART-OR-B fix round 1, red-first. Item 9d: the OR list's status pill reads the open
 * revision (Draft / Pending approval / Rejected, U4.6) while one is open, else the header
 * state ("Approved" once raised). NAMED CONTRACT CHOICE: the list row carries
 * `revision_state` and `effective_state` (backend fix round 1, F6).
 * Harness copied from `SparePartRequestsList.review2.sparePart.test.tsx`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
  IntersectionObserverStub;
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

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/spare-part-requests',
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  useParams: () => ({}),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
  usePermissions: () => ({
    permissionSet: new Set(['procurement.spare_part_requests.create']),
    permissions: ['procurement.spare_part_requests.create'],
    isLoading: false,
    isError: false,
  }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn().mockResolvedValue([]),
  getUsersSelect: vi.fn().mockResolvedValue([]),
}));

const LIST = '/api/v1/project-sales/spare-part-requests';
const row = (over: Record<string, unknown>) => ({
  id: 'spr-1',
  inquiry_no: 'OI-2611-0009',
  state: 'pending_approval',
  requested_by: 'u-1',
  requested_by_name: 'ZZT Alice',
  needed_by: '2026-12-15',
  line_count: 2,
  total: '300',
  currency: 'MYR',
  submitted_at: '2026-11-13T02:00:00',
  ...over,
});
let rows = [row({})];

const calls: string[] = [];
const ok = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const apiFetch = vi.fn(async (url: string) => {
  calls.push(url);
  if (url === LIST || url.startsWith(`${LIST}?`))
    return ok({ data: rows, pagination: { total: rows.length, page: 1, limit: 25 } });
  return ok(url.includes('select') ? { data: [] } : {});
});
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string, RequestInit?]) => apiFetch(a[0]),
}));

import { SparePartRequestsList } from './SparePartRequestsList';

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestsList />
    </QueryClientProvider>,
  );
}


function statusCell(): HTMLElement {
  const headers = screen.getAllByRole('columnheader');
  const index = headers.findIndex((h) => (h.textContent ?? '').trim() === 'Status');
  expect(index, 'a Status column').toBeGreaterThanOrEqual(0);
  const dataRow = screen.getAllByRole('row').find((r) => r.querySelectorAll('td').length > 0)!;
  return dataRow.querySelectorAll('td')[index] as HTMLElement;
}

describe('item 9d: the OR list pill reads the open revision', () => {
  beforeEach(() => {
    cleanup();
    calls.length = 0;
  });

  it.each([
    ['draft', 'Draft'],
    ['pending_approval', 'Pending approval'],
    ['rejected', 'Rejected'],
  ])('revision_state %s reads %s', async (revision, label) => {
    rows = [row({ state: 'raised', revision_state: revision, effective_state: revision, oi_no: 'OI-2611-0001' })];
    mount();
    await screen.findByText('ZZT Alice', {}, { timeout: 5000 });
    await waitFor(() => expect(statusCell()).toHaveTextContent(label));
    expect(statusCell()).not.toHaveTextContent('Approved');
  });

  it('no revision open: Approved', async () => {
    rows = [row({ state: 'raised', revision_state: null, effective_state: 'raised', oi_no: 'OI-2611-0001' })];
    mount();
    await screen.findByText('ZZT Alice', {}, { timeout: 5000 });
    await waitFor(() => expect(statusCell()).toHaveTextContent('Approved'));
  });
});
