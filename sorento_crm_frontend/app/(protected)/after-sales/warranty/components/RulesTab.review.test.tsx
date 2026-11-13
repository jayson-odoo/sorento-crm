/**
 * AFTER-SALES-P2 review round (item 8): RulesTab. Write controls are admin-only (`useEffectiveIsSuperadmin`): a non-admin
 * sees no Create button and no Edit or Delete menu items (the rule tester stays: it only reads); an admin sees them.
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

const useRules = vi.fn();
vi.mock('../hooks/useWarrantyConfig', () => ({
  useRules: (...a: unknown[]) => useRules(...a),
  useKindOptions: () => ({ data: [{ id: 'k-1', name: 'Bathroom Furniture' }] }),
  useCreateRule: mut, useUpdateRule: mut,
}));
vi.mock('./RuleFormDialog', () => ({ RuleFormDialog: () => null }));
vi.mock('./RuleTesterDialog', () => ({ RuleTesterDialog: () => null }));

import { RulesTab } from './RulesTab';

const RULE = { id: 'r-1', kind_id: 'k-1', kind_code: 'BF', kind_name: 'Bathroom Furniture', match_type: 'series', match_value: 'Demo Series A', priority: 0, created_at: '2026-01-01T00:00:00', updated_at: null };

beforeEach(() => {
  vi.clearAllMocks(); isAdmin = true; Object.keys(runs).forEach((k) => delete runs[k]);
  useRules.mockReturnValue({ data: { data: [RULE], pagination: { total: 1, page: 1, limit: 50 } }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() });
});

describe('RulesTab review round', () => {
  it('a non-admin sees no Create button and no write menu items', async () => {
    isAdmin = false;
    wrap(<RulesTab />);
    expect(screen.queryByRole('button', { name: /^Create/ })).toBeNull();
    fireEvent.contextMenu(screen.getByText('Bathroom Furniture'));
    const items = await noMenuItems();
    for (const label of ['Edit', 'Delete']) expect(items).not.toContain(label);
  });

  it('an admin sees one Create button and Edit and Delete', async () => {
    wrap(<RulesTab />);
    expect(screen.getAllByRole('button', { name: /^Create/ })).toHaveLength(1);
    fireEvent.contextMenu(screen.getByText('Bathroom Furniture'));
    expect(await menuLabels()).toEqual(expect.arrayContaining(['Edit', 'Delete']));
  });
});
