/**
 * SPARE-PART-ORDER-REQUEST review round 2, red-first (Phase 2).
 *
 * R2 (review M2, owner standing rule "every column header sorts, server-side"): the
 *    Requested by and Total headers sort; a click sends `sort=requested_by_name` /
 *    `sort=total` with `dir=asc`, a second click `dir=desc` (the backend half is
 *    tests/test_spare_part_request_review2.py R2).
 * R7 (review S4) one status vocabulary: the list's pill for a raised (and a done) request
 *    reads "Approved", the word the record header and its General card use too. GUARD here
 *    (the list already uses sparePartRequestStatusLabel); the record half is red.
 *
 * Asserted at the HTTP seam (`apiFetch`) with the real hooks and service.
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

const listParams = () =>
  calls
    .filter((u) => u === LIST || u.startsWith(`${LIST}?`))
    .map((u) => new URLSearchParams(u.split('?')[1] ?? ''));

/** The sort button DataGridColumnHeader draws only for a sortable column. */
const sortButton = (title: string) =>
  screen
    .getAllByRole('columnheader')
    .flatMap((h) => Array.from(h.querySelectorAll('button')))
    .find((b) => b.textContent?.trim() === title) ?? null;

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  rows = [row({})];
});

describe('R2 (M2): Requested by and Total sort on the server', () => {
  it.each([
    ['Requested by', 'requested_by_name'],
    ['Total', 'total'],
  ])('the %s header sorts, asc then desc, through the list GET', async (title, key) => {
    mount();
    await screen.findByText('OI-2611-0009');
    const button = sortButton(title);
    expect(button, `the ${title} header is a sort button`).not.toBeNull();

    fireEvent.click(button!);
    await waitFor(() =>
      expect(
        listParams().some((p) => p.get('sort') === key && p.get('dir') === 'asc'),
        `a list GET with sort=${key}&dir=asc after clicking ${title}`,
      ).toBe(true),
    );
    fireEvent.click(sortButton(title)!);
    await waitFor(() =>
      expect(
        listParams().some((p) => p.get('sort') === key && p.get('dir') === 'desc'),
        `a list GET with sort=${key}&dir=desc after the second click`,
      ).toBe(true),
    );
  });

  it('every column header of the list sorts (a click sends its sort key)', async () => {
    const keys: Record<string, string> = {
      Number: 'inquiry_no',
      Status: 'state',
      'Requested by': 'requested_by_name',
      'Delivery date': 'needed_by', // C5.1 relabel (SPARE-PART-OR-B C, lead sign-off)
      Lines: 'line_count',
      Total: 'total',
      Submitted: 'submitted_at',
    };
    mount();
    await screen.findByText('OI-2611-0009');
    const missing: string[] = [];
    for (const [title, key] of Object.entries(keys)) {
      const button = sortButton(title);
      if (!button) {
        missing.push(title);
        continue;
      }
      fireEvent.click(button);
      try {
        await waitFor(() => expect(listParams().some((p) => p.get('sort') === key)).toBe(true), {
          timeout: 500,
        });
      } catch {
        missing.push(title);
      }
    }
    expect(missing, `headers that do not sort: ${missing.join(', ')}`).toEqual([]);
  });
});

describe('R7 (S4): the list says "Approved" for a raised or done request', () => {
  it.each(['raised', 'actioned'])('a %s row reads Approved', async (state) => {
    rows = [row({ state })];
    mount();
    await screen.findByText('OI-2611-0009');
    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.queryByText('Raised')).toBeNull();
    expect(screen.queryByText('Done')).toBeNull();
  });
});
