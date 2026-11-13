/**
 * AFTER-SALES-P2 review round: the Status and Terms columns sort on the server like the others. Clicking a header sends
 * the sort to the policies list request (`usePolicies` params.sorting): Status as id `status`, Terms as id `term_count`
 * (the backend sort key), first ascending, then descending.
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
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/warranty',
  useSearchParams: () => new URLSearchParams(window.location.search),
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
let isAdmin = true;
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => isAdmin }));
const runs: Record<string, ReturnType<typeof vi.fn>> = {};
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: { actionKey: string }) => {
    runs[input.actionKey] ??= vi.fn();
    return { run: runs[input.actionKey], targetId: null, isPending: false, countdown: null };
  },
  useRowPending: () => () => false,
}));
const { mut } = vi.hoisted(() => ({ mut: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
const menuLabels = async () => within(await screen.findByRole('menu')).getAllByRole('menuitem').map((i) => (i.textContent || '').trim());
const noMenuItems = async () => { await Promise.resolve(); return screen.queryAllByRole('menuitem').map((i) => (i.textContent || '').trim()); };
const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

const usePolicies = vi.fn();
vi.mock('../hooks/useWarrantyConfig', () => ({
  usePolicies: (...a: unknown[]) => usePolicies(...a),
  useCreatePolicy: mut, useUpdatePolicy: mut, useSupersedePolicy: mut,
}));
vi.mock('./PolicyFormDialog', () => ({ PolicyFormDialog: () => null }));
vi.mock('./SupersedeDialog', () => ({ SupersedeDialog: () => null }));

import { PoliciesTab } from './PoliciesTab';

const POLICY = { id: 'p-1', version: 'v15', effective_from: '2000-01-01', effective_to: null, policy_text: null, term_count: 41, created_at: '2000-01-01T00:00:00', updated_at: null };
beforeEach(() => {
  vi.clearAllMocks(); isAdmin = true;
  window.history.replaceState(null, '', '/after-sales/warranty');
  usePolicies.mockReturnValue({ data: { data: [POLICY], pagination: { total: 1, page: 1, limit: 50 } }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() });
});

const lastSorting = () => usePolicies.mock.calls[usePolicies.mock.calls.length - 1][0].sorting;
const header = (name: string) => within(screen.getByRole('columnheader', { name: new RegExp(name) })).getByRole('button', { name });

describe('PoliciesTab server-side sort on Status and Terms', () => {
  it.each([['Status', 'status'], ['Terms', 'term_count']])('clicking %s sends sort %s ascending, then descending', (title, id) => {
    wrap(<PoliciesTab />);
    fireEvent.click(header(title));
    expect(lastSorting()).toEqual([{ id, desc: false }]);
    fireEvent.click(header(title));
    expect(lastSorting()).toEqual([{ id, desc: true }]);
  });
});
