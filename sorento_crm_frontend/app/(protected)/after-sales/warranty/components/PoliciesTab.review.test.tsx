/**
 * AFTER-SALES-P2 review round (items 8, 9): PoliciesTab.
 * 8. Write controls are admin-only (`useEffectiveIsSuperadmin`): a non-admin sees no Create button and no Edit,
 *    Supersede or Delete menu items; an admin sees them.
 * 9. Supersede is not offered on a closed policy (one with an effective_to); it is on an open-ended one.
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

const policy = (over: Record<string, unknown>) => ({
  id: 'p-1', version: 'v15', effective_from: '2000-01-01', effective_to: null, policy_text: null, term_count: 41,
  created_at: '2000-01-01T00:00:00', updated_at: null, ...over,
});
const list = (rows: unknown[]) =>
  usePolicies.mockReturnValue({ data: { data: rows, pagination: { total: rows.length, page: 1, limit: 50 } }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() });

beforeEach(() => { vi.clearAllMocks(); isAdmin = true; Object.keys(runs).forEach((k) => delete runs[k]); list([policy({})]); });

describe('PoliciesTab review round', () => {
  it('Supersede is offered on an open-ended policy', async () => {
    wrap(<PoliciesTab />);
    fireEvent.contextMenu(screen.getByText('v15'));
    expect(await menuLabels()).toEqual(['Edit', 'Supersede', 'Delete']);
  });

  it('Supersede is not offered on a closed policy', async () => {
    list([policy({ effective_to: '2020-12-31' })]);
    wrap(<PoliciesTab />);
    fireEvent.contextMenu(screen.getByText('v15'));
    const labels = await menuLabels();
    expect(labels).not.toContain('Supersede');
    expect(labels).toEqual(expect.arrayContaining(['Edit', 'Delete']));
  });

  it('a non-admin sees no Create button and no write menu items', async () => {
    isAdmin = false;
    wrap(<PoliciesTab />);
    expect(screen.queryByRole('button', { name: /^Create/ })).toBeNull();
    fireEvent.contextMenu(screen.getByText('v15'));
    const items = await noMenuItems();
    for (const label of ['Edit', 'Supersede', 'Delete']) expect(items).not.toContain(label);
  });

  it('an admin sees one Create button', () => {
    wrap(<PoliciesTab />);
    expect(screen.getAllByRole('button', { name: /^Create/ })).toHaveLength(1);
  });
});
