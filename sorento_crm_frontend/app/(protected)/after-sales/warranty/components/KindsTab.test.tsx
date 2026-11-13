/**
 * AFTER-SALES-P2 red tests (UAC F3, C kinds): the Kinds tab of Warranty Configuration.
 *
 * Module the coder builds: `./KindsTab` named export `KindsTab`, no props. Reads `../hooks/useWarrantyConfig`:
 *   useKinds(params: grid params + { has_no_rule?: boolean }) -> { data: { data: Kind[], pagination }, isLoading, isError, isFetching, refetch }
 *     Kind = { id, code, name, sort_order, is_active, rule_count, term_count, created_at, updated_at }
 *   useKindRuleCounts() -> { data: { without: number, total: number } | undefined }   (the pill's N and M)
 *   useCreateKind() / useUpdateKind() -> { mutateAsync, isPending }
 * Columns: Kind, Code, Rules, Terms, Active. The amber pill reads "N of M kinds have no rule"; clicking it re-queries
 * useKinds with has_no_rule: true (click again to clear). Right-click: Edit, Archive, Delete; Archive and Delete are
 * deferred countdowns (actionKeys matching /archive/ and /delete/); Delete is offered only for an unused kind
 * (rule_count 0 and term_count 0). One "Create" button; it opens `./KindFormDialog`.
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
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => true }));
/** One `run` per actionKey, so a test can tell Archive from Delete. */
const runs: Record<string, ReturnType<typeof vi.fn>> = {};
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: { actionKey: string }) => {
    runs[input.actionKey] ??= vi.fn();
    return { run: runs[input.actionKey], targetId: null, isPending: false, countdown: null };
  },
  useRowPending: () => () => false,
}));

const useKinds = vi.fn();
const { mut } = vi.hoisted(() => ({ mut: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock('../hooks/useWarrantyConfig', () => ({
  useKinds: (...a: unknown[]) => useKinds(...a),
  useKindRuleCounts: () => ({ data: { without: 29, total: 31 } }),
  useCreateKind: mut,
  useUpdateKind: mut,
}));
vi.mock('./KindFormDialog', () => ({
  KindFormDialog: ({ open, kind }: { open: boolean; kind?: { name: string } | null }) =>
    open ? <div role="dialog">Kind form {kind ? `edit ${kind.name}` : 'create'}</div> : null,
}));

import { KindsTab } from './KindsTab';

const kind = (over: Record<string, unknown>) => ({
  id: 'k-1', code: 'WATER_CLOSET', name: 'Water Closet', sort_order: 1, is_active: true,
  rule_count: 0, term_count: 3, created_at: '2026-01-01T00:00:00', updated_at: null, ...over,
});
const list = (rows: unknown[]) =>
  useKinds.mockReturnValue({
    data: { data: rows, pagination: { total: rows.length, page: 1, limit: 10 } },
    isLoading: false, isError: false, isFetching: false, refetch: vi.fn(),
  });
const renderTab = () => render(<QueryClientProvider client={new QueryClient()}><KindsTab /></QueryClientProvider>);
const menuLabels = async () => within(await screen.findByRole('menu')).getAllByRole('menuitem').map((i) => (i.textContent || '').trim());

beforeEach(() => { vi.clearAllMocks(); Object.keys(runs).forEach((k) => delete runs[k]); list([kind({}), kind({ id: 'k-2', name: 'Mirror Cabinet', code: 'MIRROR_CABINET', rule_count: 1, term_count: 0 })]); });

describe('KindsTab', () => {
  it('has the five columns and one Create button', () => {
    renderTab();
    const heads = screen.getAllByRole('columnheader').map((h) => (h.textContent || '').trim()).filter(Boolean);
    expect(heads).toEqual(['Kind', 'Code', 'Rules', 'Terms', 'Active']);
    expect(screen.getAllByRole('button', { name: /^Create/ })).toHaveLength(1);
  });

  it('shows the amber count pill with N of M', () => {
    renderTab();
    expect(screen.getByText('29 of 31 kinds have no rule')).toBeInTheDocument();
  });

  it('clicking the pill filters the grid to kinds with no rule, clicking again clears it', () => {
    renderTab();
    expect(useKinds).toHaveBeenLastCalledWith(expect.not.objectContaining({ has_no_rule: true }));
    fireEvent.click(screen.getByText('29 of 31 kinds have no rule'));
    expect(useKinds).toHaveBeenLastCalledWith(expect.objectContaining({ has_no_rule: true }));
    fireEvent.click(screen.getByText('29 of 31 kinds have no rule'));
    expect(useKinds).toHaveBeenLastCalledWith(expect.not.objectContaining({ has_no_rule: true }));
  });

  it('shows the kind, its code and counts, with an Active pill', () => {
    renderTab();
    const row = screen.getByText('Water Closet').closest('tr')!;
    expect(within(row).getByText('WATER_CLOSET')).toBeInTheDocument();
    expect(within(row).getByText('Active').closest('[data-slot="badge"]')).not.toBeNull();
  });

  it('right-click on an unused kind offers Edit, Archive and Delete', async () => {
    list([kind({ rule_count: 0, term_count: 0 })]);
    renderTab();
    fireEvent.contextMenu(screen.getByText('Water Closet'));
    expect(await menuLabels()).toEqual(['Edit', 'Archive', 'Delete']);
  });

  it('a kind in use cannot be deleted: Edit and Archive only', async () => {
    renderTab();
    fireEvent.contextMenu(screen.getByText('Water Closet'));
    expect(await menuLabels()).toEqual(['Edit', 'Archive']);
  });

  it('Archive and Delete are deferred countdowns with no confirm dialog', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    list([kind({ id: 'k-9', rule_count: 0, term_count: 0 })]);
    renderTab();
    fireEvent.contextMenu(screen.getByText('Water Closet'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Archive' }));
    const archiveKey = Object.keys(runs).find((k) => /archive/.test(k))!;
    expect(runs[archiveKey]).toHaveBeenCalledWith(expect.objectContaining({ id: 'k-9' }));
    fireEvent.contextMenu(screen.getByText('Water Closet'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    const deleteKey = Object.keys(runs).find((k) => /delete/.test(k))!;
    expect(runs[deleteKey]).toHaveBeenCalledWith(expect.objectContaining({ id: 'k-9' }));
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('empty state is a heading and a hint with no button inside it', () => {
    list([]);
    renderTab();
    const heading = screen.getByRole('heading', { name: /no (warranty )?kinds/i });
    expect(within(heading.parentElement as HTMLElement).queryByRole('button')).toBeNull();
  });
});
