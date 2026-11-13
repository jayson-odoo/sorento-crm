/**
 * AFTER-SALES-P2 review round (items 7, 8): KindsTab.
 * 7. An archived kind's right-click menu offers "Restore" (not Archive), which PATCHes is_active true through
 *    useUpdateKind().mutateAsync({ id, values: { is_active: true } }).
 * 8. Write controls are admin-only (`useEffectiveIsSuperadmin` from `@/hooks/useEffectiveIsSuperadmin`): a non-admin sees
 *    the list read-only, no Create button and no Edit, Archive, Restore or Delete menu items; an admin sees them.
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

const useKinds = vi.fn();
const update = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false };
vi.mock('../hooks/useWarrantyConfig', () => ({
  useKinds: (...a: unknown[]) => useKinds(...a),
  useKindRuleCounts: () => ({ data: { without: 29, total: 31 } }),
  useCreateKind: mut,
  useUpdateKind: () => update,
}));
vi.mock('./KindFormDialog', () => ({ KindFormDialog: () => null }));

import { KindsTab } from './KindsTab';

const kind = (over: Record<string, unknown>) => ({
  id: 'k-1', code: 'WATER_CLOSET', name: 'Water Closet', sort_order: 1, is_active: true,
  rule_count: 0, term_count: 0, created_at: '2026-01-01T00:00:00', updated_at: null, ...over,
});
const list = (rows: unknown[]) =>
  useKinds.mockReturnValue({ data: { data: rows, pagination: { total: rows.length, page: 1, limit: 50 } }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() });

beforeEach(() => { vi.clearAllMocks(); isAdmin = true; Object.keys(runs).forEach((k) => delete runs[k]); list([kind({})]); });

describe('KindsTab review round', () => {
  it('an archived kind offers Restore instead of Archive, and Restore PATCHes is_active true', async () => {
    list([kind({ id: 'k-9', is_active: false })]);
    wrap(<KindsTab />);
    fireEvent.contextMenu(screen.getByText('Water Closet'));
    const labels = await menuLabels();
    expect(labels).toContain('Restore');
    expect(labels).not.toContain('Archive');
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Restore' }));
    expect(update.mutateAsync).toHaveBeenCalledWith({ id: 'k-9', values: { is_active: true } });
  });

  it('an active kind does not offer Restore', async () => {
    wrap(<KindsTab />);
    fireEvent.contextMenu(screen.getByText('Water Closet'));
    expect(await menuLabels()).not.toContain('Restore');
  });

  it('a non-admin sees no Create button and no write menu items', async () => {
    isAdmin = false;
    wrap(<KindsTab />);
    expect(screen.queryByRole('button', { name: /^Create/ })).toBeNull();
    fireEvent.contextMenu(screen.getByText('Water Closet'));
    const items = await noMenuItems();
    for (const label of ['Edit', 'Archive', 'Restore', 'Delete']) expect(items).not.toContain(label);
  });

  it('an admin sees Create and the write menu items', async () => {
    wrap(<KindsTab />);
    expect(screen.getAllByRole('button', { name: /^Create/ })).toHaveLength(1);
    fireEvent.contextMenu(screen.getByText('Water Closet'));
    expect(await menuLabels()).toEqual(expect.arrayContaining(['Edit', 'Archive', 'Delete']));
  });
});
