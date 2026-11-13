/**
 * AFTER-SALES-P2 red tests (owner standing rule: "the page and its filters are in the address bar").
 *
 * `/after-sales/warranty` (`./WarrantyConfigView`): the active tab (`?tab=`, via useUrlTab, already so) AND each
 * tab's search, sort, filters and page live in the URL query, written and restored the way P1's ServiceJobsList does it:
 * `useListStateFromUrl` reads `page`, `limit`, `sort`, `dir`, `query` plus the tab's filter keys (`is_active`,
 * `kind_id`, `has_no_rule` ...) with `parseDetailSearch`, and an effect writes them back with `window.history.replaceState`
 * (`../../service-jobs/lib/listUrl.ts` is the reference). A tab's state does not leak into another tab's list.
 * Hook params asserted are the ones the tabs already pass (`usePolicies`, `useKinds`, `useRules`).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));

const usePolicies = vi.fn();
const useKinds = vi.fn();
const useRules = vi.fn();
const { mut } = vi.hoisted(() => ({ mut: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock('../hooks/useWarrantyConfig', () => ({
  usePolicies: (...a: unknown[]) => usePolicies(...a),
  useKinds: (...a: unknown[]) => useKinds(...a),
  useRules: (...a: unknown[]) => useRules(...a),
  useKindRuleCounts: () => ({ data: { without: 29, total: 31 } }),
  useKindOptions: () => ({ data: [{ id: 'k-1', name: 'Bathroom Furniture' }, { id: 'k-2', name: 'Mirror Cabinet' }] }),
  useCreatePolicy: mut, useUpdatePolicy: mut, useSupersedePolicy: mut, useCreateKind: mut, useUpdateKind: mut,
  useCreateRule: mut, useUpdateRule: mut,
}));
vi.mock('./PolicyFormDialog', () => ({ PolicyFormDialog: () => null }));
vi.mock('./SupersedeDialog', () => ({ SupersedeDialog: () => null }));
vi.mock('./KindFormDialog', () => ({ KindFormDialog: () => null }));
vi.mock('./RuleFormDialog', () => ({ RuleFormDialog: () => null }));
vi.mock('./RuleTesterDialog', () => ({ RuleTesterDialog: () => null }));

import WarrantyConfigView from './WarrantyConfigView';

const page = (rows: unknown[]) => ({
  data: { data: rows, pagination: { total: rows.length, page: 1, limit: 50 } },
  isLoading: false, isError: false, isFetching: false, refetch: vi.fn(),
});
const POLICY = { id: 'p-1', version: 'v15', effective_from: '2000-01-01', effective_to: null, policy_text: null, term_count: 41, created_at: '2000-01-01T00:00:00', updated_at: null };
const KIND = { id: 'k-1', code: 'WATER_CLOSET', name: 'Water Closet', sort_order: 1, is_active: true, rule_count: 0, term_count: 3, created_at: '2026-01-01T00:00:00', updated_at: null };
const RULE = { id: 'r-1', kind_id: 'k-1', kind_code: 'BF', kind_name: 'Bathroom Furniture', match_type: 'series', match_value: 'Demo Series A', priority: 0, created_at: '2026-01-01T00:00:00', updated_at: null };

const TABS = [
  { tab: 'policies', hook: usePolicies, placeholder: 'Search policies...' },
  { tab: 'kinds', hook: useKinds, placeholder: 'Search kinds...' },
  { tab: 'rules', hook: useRules, placeholder: 'Search rules...' },
] as const;

function mount() {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}><WarrantyConfigView /></QueryClientProvider>);
}
const last = (hook: ReturnType<typeof vi.fn>) => hook.mock.calls[hook.mock.calls.length - 1][0];

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/after-sales/warranty');
  usePolicies.mockReturnValue(page([POLICY]));
  useKinds.mockReturnValue(page([KIND]));
  useRules.mockReturnValue(page([RULE]));
});

describe('Warranty Configuration keeps its page and filters in the address bar', () => {
  it.each(TABS)('$tab: a typed search is written to the URL and survives a reload', async ({ tab, hook, placeholder }) => {
    window.history.replaceState(null, '', `/after-sales/warranty?tab=${tab}`);
    const first = mount();
    fireEvent.change(screen.getByPlaceholderText(placeholder), { target: { value: 'wc' } });
    await waitFor(() => expect(last(hook)).toMatchObject({ searchQuery: 'wc' }));
    await waitFor(() => expect(new URLSearchParams(window.location.search).get('query')).toBe('wc'));
    expect(new URLSearchParams(window.location.search).get('tab')).toBe(tab);

    first.unmount();
    hook.mockClear();
    mount();
    expect((screen.getByPlaceholderText(placeholder) as HTMLInputElement).value).toBe('wc');
    expect(hook.mock.calls[0][0]).toMatchObject({ searchQuery: 'wc' });
  });

  it('policies: page, size, sort and search come back from the URL', () => {
    window.history.replaceState(null, '', '/after-sales/warranty?page=3&limit=25&sort=version&dir=asc&query=v1');
    mount();
    expect(usePolicies.mock.calls[0][0]).toMatchObject({
      pageIndex: 2, pageSize: 25, sorting: [{ id: 'version', desc: false }], searchQuery: 'v1',
    });
  });

  it('kinds: page, sort, search and the status filter come back from the URL', () => {
    window.history.replaceState(null, '', '/after-sales/warranty?tab=kinds&page=2&limit=25&sort=code&dir=desc&query=wc&is_active=false');
    mount();
    expect(useKinds.mock.calls[0][0]).toMatchObject({
      pageIndex: 1, pageSize: 25, sorting: [{ id: 'code', desc: true }], searchQuery: 'wc', is_active: ['false'],
    });
  });

  it('rules: the multi-select kind filter and the sort come back from the URL', () => {
    window.history.replaceState(null, '', '/after-sales/warranty?tab=rules&kind_id=k-1,k-2&sort=priority&dir=desc');
    mount();
    expect(useRules.mock.calls[0][0]).toMatchObject({ kind_id: ['k-1', 'k-2'], sorting: [{ id: 'priority', desc: true }] });
  });

  it('kinds: the "no rule" pill filter is written to the URL and survives a reload', async () => {
    window.history.replaceState(null, '', '/after-sales/warranty?tab=kinds');
    const first = mount();
    fireEvent.click(screen.getByText('29 of 31 kinds have no rule'));
    await waitFor(() => expect(window.location.search).toContain('has_no_rule'));
    first.unmount();
    useKinds.mockClear();
    mount();
    expect(useKinds.mock.calls[0][0]).toMatchObject({ has_no_rule: true });
  });

  it('a tab keeps the user on it from the URL, and switching writes the new tab', () => {
    window.history.replaceState(null, '', '/after-sales/warranty?tab=kinds');
    mount();
    expect(screen.getByRole('tab', { name: 'Kinds' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Rules' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Rules' }));
    expect(new URLSearchParams(window.location.search).get('tab')).toBe('rules');
  });

  it("one tab's search does not leak into the next tab's list or the URL", async () => {
    window.history.replaceState(null, '', '/after-sales/warranty?tab=kinds');
    mount();
    fireEvent.change(screen.getByPlaceholderText('Search kinds...'), { target: { value: 'wc' } });
    await waitFor(() => expect(new URLSearchParams(window.location.search).get('query')).toBe('wc'));
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Rules' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Rules' }));
    await waitFor(() => expect(screen.getByPlaceholderText('Search rules...')).toBeInTheDocument());
    expect((screen.getByPlaceholderText('Search rules...') as HTMLInputElement).value).toBe('');
    expect(new URLSearchParams(window.location.search).get('query')).toBeNull();
  });
});
