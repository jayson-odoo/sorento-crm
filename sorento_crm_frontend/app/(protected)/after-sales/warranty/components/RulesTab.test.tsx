/**
 * AFTER-SALES-P2 red tests (UAC F3, C rules): the Rules tab of Warranty Configuration.
 *
 * Module the coder builds: `./RulesTab` named export `RulesTab`, no props. Reads `../hooks/useWarrantyConfig`:
 *   useRules(params: grid params + { kind_id?: string[] }) -> { data: { data: Rule[], pagination }, isLoading, isError, isFetching, refetch }
 *     Rule = { id, kind_id, kind_code, kind_name, match_type, match_value, priority, created_at, updated_at }
 *   useKindOptions() -> { data: { id, name }[] }       (the Kind multi-select filter)
 *   useCreateRule() / useUpdateRule() -> { mutateAsync, isPending }
 * Columns: Kind, Match (series -> "Series", model_list -> "Model list"...), Value, Priority. Toolbar buttons:
 * "Test a product" (opens `./RuleTesterDialog`) and ONE "Create" (opens `./RuleFormDialog`). Right-click: Edit and Delete
 * (deferred countdown, actionKey matching /delete/, no confirm).
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

const useRules = vi.fn();
const mut = () => ({ mutateAsync: vi.fn(), isPending: false });
vi.mock('../hooks/useWarrantyConfig', () => ({
  useRules: (...a: unknown[]) => useRules(...a),
  useKindOptions: () => ({ data: [{ id: 'k-1', name: 'Bathroom Furniture' }, { id: 'k-2', name: 'Mirror Cabinet' }] }),
  useCreateRule: mut,
  useUpdateRule: mut,
}));
vi.mock('./RuleTesterDialog', () => ({ RuleTesterDialog: ({ open }: { open: boolean }) => (open ? <div role="dialog">Rule tester</div> : null) }));
vi.mock('./RuleFormDialog', () => ({ RuleFormDialog: ({ open, rule }: { open: boolean; rule?: unknown }) => (open ? <div role="dialog">Rule form {rule ? 'edit' : 'create'}</div> : null) }));

import { RulesTab } from './RulesTab';

const RULE = { id: 'r-1', kind_id: 'k-1', kind_code: 'BF', kind_name: 'Bathroom Furniture', match_type: 'series', match_value: 'Demo Series A', priority: 0, created_at: '2026-01-01T00:00:00', updated_at: null };
const rows = (r: unknown[]) =>
  useRules.mockReturnValue({ data: { data: r, pagination: { total: r.length, page: 1, limit: 50 } }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() });
const renderTab = () => render(<QueryClientProvider client={new QueryClient()}><RulesTab /></QueryClientProvider>);

beforeEach(() => { vi.clearAllMocks(); Object.keys(runs).forEach((k) => delete runs[k]); rows([RULE]); });

describe('RulesTab', () => {
  it('has the four columns and plain-word match types', () => {
    renderTab();
    const heads = screen.getAllByRole('columnheader').map((h) => (h.textContent || '').trim()).filter(Boolean);
    expect(heads).toEqual(['Kind', 'Match', 'Value', 'Priority']);
    const row = screen.getByText('Bathroom Furniture').closest('tr')!;
    expect(within(row).getByText('Series')).toBeInTheDocument();
    expect(within(row).getByText('Demo Series A')).toBeInTheDocument();
  });

  it('starts with an empty Kind filter', () => {
    renderTab();
    expect(useRules).toHaveBeenCalledWith(expect.objectContaining({ kind_id: [] }));
  });

  it('has one Create button plus Test a product', () => {
    renderTab();
    expect(screen.getAllByRole('button', { name: /^Create/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Test a product' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Rule tester');
  });

  it('right-click offers Edit and Delete; Delete is a deferred countdown', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderTab();
    fireEvent.contextMenu(screen.getByText('Bathroom Furniture'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getAllByRole('menuitem').map((i) => (i.textContent || '').trim())).toEqual(['Edit', 'Delete']);
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }));
    const key = Object.keys(runs).find((k) => /delete/.test(k))!;
    expect(runs[key]).toHaveBeenCalledWith(expect.objectContaining({ id: 'r-1' }));
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('empty state is a heading and a hint with no button inside it', () => {
    rows([]);
    renderTab();
    const heading = screen.getByRole('heading', { name: /no (warranty )?rules/i });
    expect(within(heading.parentElement as HTMLElement).queryByRole('button')).toBeNull();
  });
});
