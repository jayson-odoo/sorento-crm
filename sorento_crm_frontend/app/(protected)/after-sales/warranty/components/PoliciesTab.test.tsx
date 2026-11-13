/**
 * AFTER-SALES-P2 red tests (UAC F3, C, P1): the Policies tab of Warranty Configuration.
 *
 * Module the coder builds: `./PoliciesTab` named export `PoliciesTab`, no props. A DataGrid, one toolbar row,
 * ONE "Create" button. Reads `../hooks/useWarrantyConfig` (new file):
 *   usePolicies(params) -> { data: { data: Policy[], pagination }, isLoading, isError, isFetching, refetch }
 *     Policy = { id, version, effective_from, effective_to, policy_text, term_count, created_at, updated_at }
 *   useCreatePolicy() / useUpdatePolicy() -> { mutateAsync, isPending }
 * Columns: Version, In force from, In force to, Status (pill In force / Scheduled / Superseded), Terms.
 * Right-click: Edit, Supersede, Delete. Delete is the deferred countdown (useDeferredRowAction, actionKey matching
 * /delete/), never confirm() or an AlertDialog. Rows link to `/after-sales/warranty/policies/{id}`.
 * Edit opens `./PolicyFormDialog`; Supersede opens `./SupersedeDialog`.
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
/** One `run` per actionKey, so a test can tell Archive from Delete. */
const runs: Record<string, ReturnType<typeof vi.fn>> = {};
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: { actionKey: string }) => {
    runs[input.actionKey] ??= vi.fn();
    return { run: runs[input.actionKey], targetId: null, isPending: false, countdown: null };
  },
  useRowPending: () => () => false,
}));

const usePolicies = vi.fn();
const mut = () => ({ mutateAsync: vi.fn(), isPending: false });
vi.mock('../hooks/useWarrantyConfig', () => ({
  usePolicies: (...a: unknown[]) => usePolicies(...a),
  useCreatePolicy: mut,
  useUpdatePolicy: mut,
  useSupersedePolicy: mut,
}));
vi.mock('./PolicyFormDialog', () => ({
  PolicyFormDialog: ({ open, policy }: { open: boolean; policy?: { version: string } | null }) =>
    open ? <div role="dialog">Policy form {policy ? `edit ${policy.version}` : 'create'}</div> : null,
}));
vi.mock('./SupersedeDialog', () => ({
  SupersedeDialog: ({ open, policy }: { open: boolean; policy: { version: string } }) =>
    open ? <div role="dialog">Supersede {policy.version}</div> : null,
}));

import { PoliciesTab } from './PoliciesTab';

const POLICY = {
  id: '3f2b8c1e-aaaa-4bbb-8ccc-123456789abc', version: 'v15', effective_from: '2000-01-01', effective_to: null,
  policy_text: null, term_count: 41, created_at: '2000-01-01T00:00:00', updated_at: null,
};
const list = (rows: unknown[]) =>
  usePolicies.mockReturnValue({
    data: { data: rows, pagination: { total: rows.length, page: 1, limit: 50 } },
    isLoading: false, isError: false, isFetching: false, refetch: vi.fn(),
  });
const renderTab = () => render(<QueryClientProvider client={new QueryClient()}><PoliciesTab /></QueryClientProvider>);

beforeEach(() => { vi.clearAllMocks(); Object.keys(runs).forEach((k) => delete runs[k]); list([POLICY]); });

describe('PoliciesTab', () => {
  it('has the five columns in the agreed order', () => {
    renderTab();
    const heads = screen.getAllByRole('columnheader').map((h) => (h.textContent || '').trim()).filter(Boolean);
    expect(heads).toEqual(['Version', 'In force from', 'In force to', 'Status', 'Terms']);
  });

  it('shows dates as dd/mm/yyyy, a dash for no end, the status pill and the term count', () => {
    renderTab();
    const row = screen.getByText('v15').closest('tr')!;
    expect(within(row).getByText('01/01/2000')).toBeInTheDocument();
    expect(within(row).getByText('-')).toBeInTheDocument();
    expect(within(row).getByText('In force').closest('[data-slot="badge"]')).not.toBeNull();
    expect(within(row).getByText('41')).toBeInTheDocument();
  });

  it('renders no UUID', () => {
    const { container } = renderTab();
    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it('has exactly one Create button, which opens the create dialog', () => {
    renderTab();
    expect(screen.getAllByRole('button', { name: /^Create/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('create');
  });

  it('right-click offers Edit, Supersede and Delete', async () => {
    renderTab();
    fireEvent.contextMenu(screen.getByText('v15'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getAllByRole('menuitem').map((i) => (i.textContent || '').trim())).toEqual(['Edit', 'Supersede', 'Delete']);
  });

  it('Supersede opens the supersede dialog for that policy', async () => {
    renderTab();
    fireEvent.contextMenu(screen.getByText('v15'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Supersede' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Supersede v15');
  });

  it('Delete is the deferred countdown with no confirm dialog', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderTab();
    fireEvent.contextMenu(screen.getByText('v15'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    const key = Object.keys(runs).find((k) => /delete/.test(k));
    expect(key).toBeDefined();
    expect(runs[key!]).toHaveBeenCalledWith(expect.objectContaining({ id: POLICY.id }));
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('the row opens the policy page', () => {
    renderTab();
    const link = screen.getByText('v15').closest('a');
    expect(link?.getAttribute('href')?.split('?')[0]).toBe(`/after-sales/warranty/policies/${POLICY.id}`);
  });

  it('empty state is a heading and a hint with no button inside it', () => {
    list([]);
    renderTab();
    const heading = screen.getByRole('heading', { name: /no (warranty )?policies/i });
    expect(within(heading.parentElement as HTMLElement).queryByRole('button')).toBeNull();
  });
});
